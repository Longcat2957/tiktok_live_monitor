from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import get_monitor
from app.config import Settings
from app.main import create_app
from app.schemas.health import HealthResponse
from app.schemas.settings import SettingsResponse
from app.services.monitor import MonitorService


def test_health_static_and_config(tmp_path: Path):
    config = Settings(_env_file=None, static_dir=tmp_path, comment_history_size=17)
    with TestClient(create_app(config), base_url="http://localhost") as client:
        assert client.get("/").status_code == 404
        health = client.get("/health").json()
        settings = client.get("/config").json()
        assert HealthResponse.model_validate(health).model_dump(mode="json") == health
        assert SettingsResponse.model_validate(settings).model_dump(mode="json") == settings
        assert health["source"]["state"] == "idle"
        assert settings["comment_history_size"] == 17
        paths = client.get("/openapi.json").json()["paths"]
        for path, response_name in (("/health", "HealthResponse"), ("/config", "SettingsResponse")):
            schema = paths[path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
            assert schema == {"$ref": f"#/components/schemas/{response_name}"}
        unavailable = paths["/health"]["get"]["responses"]["503"]
        assert unavailable["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/HealthResponse"
        }
    (tmp_path / "index.html").write_text("<html>monitor test</html>")
    app = create_app(config)
    with TestClient(app, base_url="http://localhost") as client:
        assert "monitor test" in client.get("/").text
        assert client.get("/health").status_code == 200
        app.state.monitor.fault = "shutdown_timeout"
        assert client.get("/health").status_code == 503
        assert client.get("/health").json()["status"] == "error"
        app.state.monitor.fault = None
        with client.websocket_connect(
            "ws://localhost/ws", headers={"Origin": "http://localhost"}
        ) as socket:
            assert socket.receive_json()["type"] == "status"
            socket.close()
            while socket.receive()["type"] != "websocket.close":
                pass


@pytest.mark.parametrize(
    "values",
    [
        {"comment_queue_size": 0},
        {"comment_history_size": 0},
        {"log_level": "invalid"},
        {"tiktok_reconnect_min_seconds": 40, "tiktok_reconnect_max_seconds": 2},
    ],
)
def test_invalid_settings(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


async def test_health_exposes_accepted_commands_until_they_finish():
    import asyncio

    import httpx

    app = create_app(Settings(_env_file=None))
    async with app.router.lifespan_context(app):
        monitor = app.state.monitor
        await monitor.lock.acquire()
        command = asyncio.create_task(
            monitor.start(monitor.broadcaster.status.session_id, source="mock")
        )
        try:
            await asyncio.sleep(0)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost"
            ) as client:
                assert (await client.get("/health")).json()["pending_commands"] == 1
                monitor.lock.release()
                await command
                assert (await client.get("/health")).json()["pending_commands"] == 0
        finally:
            if monitor.lock.locked():
                monitor.lock.release()
            await command


def test_monitor_dependency_override_is_shared_by_http_and_websocket():
    app = create_app(Settings(_env_file=None))
    replacement = MonitorService(Settings(_env_file=None, comment_history_size=23))
    app.dependency_overrides[get_monitor] = lambda: replacement
    with TestClient(app, base_url="http://localhost") as client:
        assert replacement is not app.state.monitor
        config = client.get("/config").json()
        assert config == replacement.get_settings().model_dump(mode="json")
        assert client.get("/health").json() == replacement.get_health().model_dump(mode="json")
        with client.websocket_connect(
            "ws://localhost/ws", headers={"Origin": "http://localhost"}
        ) as socket:
            status = socket.receive_json()
            assert status["session_id"] == config["session_id"]
            assert status["comment_history_size"] == 23
            assert client.get("/health").json()["websocket_connections"] == 1
            assert not app.state.monitor.broadcaster.clients
            socket.close()
            while socket.receive()["type"] != "websocket.close":
                pass
        assert client.get("/health").json()["websocket_connections"] == 0
    assert not replacement.broadcaster.tasks


def test_settings_validation_is_422_but_internal_validation_error_is_500():
    app = create_app(Settings(_env_file=None))
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
        sid = client.get("/config").json()["session_id"]
        started = client.post("/account", json={"session_id": sid, "source": "mock"})
        assert started.status_code == 200
        invalid = client.patch(
            "/config",
            json={
                "session_id": started.json()["session_id"],
                "settings": {"comment_queue_size": 0},
            },
        )
        assert invalid.status_code == 422
        assert invalid.json() == {"detail": "설정값의 허용 범위를 확인해주세요."}
        with patch.object(app.state.monitor, "get_health", side_effect=lambda: HealthResponse()):
            assert client.get("/health").status_code == 500
