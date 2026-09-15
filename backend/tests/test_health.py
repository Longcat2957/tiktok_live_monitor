from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def test_health_and_config(tmp_path: Path) -> None:
    config = Settings(
        _env_file=None, comment_source="mock", static_dir=tmp_path, comment_history_size=17
    )
    with TestClient(create_app(config)) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["source"]["source"] == "mock"
        assert body["source"]["state"] == "connected"
        assert body["websocket_connections"] == 0
        assert body["queue"]["capacity"] == 500
        assert client.get("/config").json() == {"comment_history_size": 17}
        assert client.get("/").status_code == 404


def test_static_does_not_shadow_api_or_websocket(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>monitor test</html>")
    app = create_app(Settings(_env_file=None, comment_source="mock", static_dir=tmp_path))
    with TestClient(app) as client:
        assert "monitor test" in client.get("/").text
        assert client.get("/health").status_code == 200
        with client.websocket_connect("/ws") as socket:
            assert socket.receive_json()["type"] == "status"


@pytest.mark.parametrize(
    "values",
    [
        {"comment_queue_size": 0},
        {"comment_history_size": 0},
        {"comment_source": "invalid"},
        {"tiktok_username": "https://www.tiktok.com/@foo"},
        {"log_level": "invalid"},
        {"tiktok_reconnect_min_seconds": 40, "tiktok_reconnect_max_seconds": 2},
        {"comment_source": "tiktok", "tiktok_username": ""},
    ],
)
def test_invalid_settings(values: dict) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **({"comment_source": "mock"} | values))


def test_username_normalized() -> None:
    assert (
        Settings(_env_file=None, tiktok_username=" @hello.world ").tiktok_username == "hello.world"
    )
