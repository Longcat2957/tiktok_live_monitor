from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def test_health_static_and_config(tmp_path: Path):
    config = Settings(_env_file=None, static_dir=tmp_path, comment_history_size=17)
    with TestClient(create_app(config), base_url="http://localhost") as client:
        assert client.get("/").status_code == 404
        assert client.get("/health").json()["source"]["state"] == "idle"
        assert client.get("/config").json()["comment_history_size"] == 17
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
        {"comment_source": "invalid"},
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
            monitor.change("start", monitor.manager.status.session_id, source="mock")
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
