import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import AccountInput, create_app

ORIGIN = {"Origin": "http://localhost"}


def current(client):
    return client.get("/config").json()["session_id"]


def change(client, method, path, **body):
    return client.request(method, path, json={"session_id": current(client), **body})


@pytest.mark.parametrize(
    "value",
    [
        " @hello.world ",
        "https://www.tiktok.com/@hello.world/live?x=1",
        "https://tiktok.com/@hello.world/",
    ],
)
def test_account_input(value):
    assert AccountInput(session_id="test", username=value).username == "hello.world"


def test_account_lifecycle_settings_and_stale_requests():
    async def run(source):
        source.status("connected", "test")
        await asyncio.Event().wait()

    config = Settings(_env_file=None, comment_source="mock", comment_history_size=19)
    app = create_app(config)
    with (
        patch("app.sources.tiktok.TikTokSource.run", run),
        TestClient(app, base_url="http://localhost") as client,
    ):
        idle = current(client)
        for username in [
            "",
            "@@a",
            "https://evil.test/@a",
            "https://www.tiktok.com.evil.test/@a",
            "foo/bar",
        ]:
            assert change(client, "POST", "/account", username=username).status_code == 422
        assert current(client) == idle
        assert client.post("/account", json={"source": "mock"}).status_code == 422
        assert change(client, "POST", "/account", source="mock").status_code == 200
        monitor = app.state.monitor
        initial_source = monitor.source_task
        before = client.get("/config").json()
        for invalid in [
            {"comment_history_size": 0},
            {"comment_queue_size": 10001},
            {"mock_interval_seconds": 0},
            {"log_level": "invalid"},
            {"host": "0.0.0.0"},
        ]:
            assert change(client, "PATCH", "/config", settings=invalid).status_code == 422
            assert client.get("/config").json() == before
            assert monitor.source_task is initial_source
        assert (
            change(
                client, "PATCH", "/config", settings={"tiktok_reconnect_min_seconds": 4}
            ).status_code
            == 409
        )
        assert (
            change(client, "POST", "/account", source="tiktok", username="other").status_code == 409
        )
        with client.websocket_connect("ws://localhost/ws", headers=ORIGIN) as socket:
            socket.receive_json()
            response = change(
                client,
                "PATCH",
                "/config",
                settings={
                    "comment_history_size": 7,
                    "comment_queue_size": 20,
                    "mock_interval_seconds": 0.01,
                },
            )
            assert response.status_code == 200
            boundary = response.json()
            assert boundary["session_id"] != before["session_id"]
            while (event := socket.receive_json()).get("session_id") != boundary["session_id"]:
                pass
            assert event["comment_history_size"] == 7
            while (event := socket.receive_json())["type"] != "comment":
                pass
            assert event["comment"].startswith("[데모 #")
            socket.close()
            while socket.receive()["type"] != "websocket.close":
                pass
        assert initial_source.done()
        assert client.get("/health").json()["queue"]["capacity"] == 20
        assert client.post("/refresh", json={"session_id": before["session_id"]}).status_code == 409
        assert change(client, "POST", "/refresh").status_code == 200
        assert client.get("/config").json()["comment_history_size"] == 7
        draft = current(client)
        assert change(client, "DELETE", "/account").json()["state"] == "idle"
        assert (
            client.patch(
                "/config", json={"session_id": draft, "settings": {"comment_history_size": 3}}
            ).status_code
            == 409
        )
        assert client.get("/health").json()["source"]["state"] == "idle"
        assert change(client, "POST", "/refresh").status_code == 409
        assert (
            change(client, "POST", "/account", source="tiktok", username="@first").status_code
            == 200
        )
        assert (
            change(client, "PATCH", "/config", settings={"mock_interval_seconds": 1}).status_code
            == 409
        )
        assert (
            change(
                client, "PATCH", "/config", settings={"tiktok_reconnect_min_seconds": 40}
            ).status_code
            == 422
        )
        assert (
            change(
                client,
                "PATCH",
                "/config",
                settings={"tiktok_reconnect_min_seconds": 40, "tiktok_reconnect_max_seconds": 60},
            ).status_code
            == 200
        )
        assert change(client, "POST", "/refresh").json()["username"] == "first"
        assert change(client, "DELETE", "/account").json()["username"] is None
        assert monitor.source_task is None
        assert monitor.consumer_task is None
    with TestClient(create_app(config), base_url="http://localhost") as client:
        assert client.get("/config").json()["comment_history_size"] == 19


def test_http_and_websocket_origin_checks():
    app = create_app(Settings(_env_file=None))
    with TestClient(app, base_url="http://localhost") as client:
        sid = current(client)
        for headers in [
            {"Origin": "https://evil.test"},
            {"Origin": "null"},
            {"Sec-Fetch-Site": "cross-site"},
            {"Origin": "http://localhost:9999"},
        ]:
            assert (
                client.post(
                    "/account", json={"session_id": sid, "source": "mock"}, headers=headers
                ).status_code
                == 403
            )
        assert client.get("/health", headers={"Host": "evil.test"}).status_code == 400
        for origin in [None, "null", "https://evil.test", "http://localhost:9999"]:
            with pytest.raises(Exception) as error:
                with client.websocket_connect(
                    "ws://localhost/ws", headers={"Origin": origin} if origin else {}
                ):
                    pytest.fail("cross-origin socket accepted")
            assert getattr(error.value, "code", None) == 1008
        with client.websocket_connect("ws://localhost/ws", headers=ORIGIN) as socket:
            assert socket.receive_json()["state"] == "idle"
            socket.send_bytes(b"not a command")
            assert socket.receive()["type"] == "websocket.close"
        assert current(client) == sid
