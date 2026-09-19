import asyncio
import json
import socket

import httpx
import pytest
import uvicorn
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from app.config import Settings
from app.main import create_app
from app.schemas.events import Comment, User


async def test_real_http_websocket_burst_conflicts_and_shutdown():
    app = create_app(Settings(_env_file=None, mock_interval_seconds=3600, comment_queue_size=1000))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.setblocking(False)
    base = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", ws="websockets-sansio"))
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(3):
            while not server.started:
                await asyncio.sleep(0.001)
        async with httpx.AsyncClient(base_url=base) as client:
            with pytest.raises(InvalidStatus) as denied:
                async with connect(f"ws://127.0.0.1:{port}/ws", origin="https://evil.test"):
                    pytest.fail("cross-origin accepted")
            assert denied.value.response.status_code == 403
            assert (await client.get("/health", headers={"Host": "evil.test"})).status_code == 400
            async with (
                connect(f"ws://127.0.0.1:{port}/ws", origin=base) as first,
                connect(f"ws://127.0.0.1:{port}/ws", origin=base) as second,
            ):
                idle = json.loads(await first.recv())
                assert json.loads(await second.recv()) == idle
                started = await client.post(
                    "/account",
                    json={
                        "session_id": idle["session_id"],
                        "source": "mock",
                    },
                    headers={"Origin": base},
                )
                assert started.status_code == 200
                for peer in (first, second):
                    async with asyncio.timeout(2):
                        while json.loads(await peer.recv())["type"] != "comment":
                            pass
                for number in range(500):
                    app.state.monitor.sink.publish(
                        Comment(
                            user=User(nickname="n", unique_id="u"),
                            comment=str(number),
                        )
                    )
                for peer in (first, second):
                    async with asyncio.timeout(3):
                        received = [json.loads(await peer.recv())["comment"] for _ in range(500)]
                    assert received == [str(i) for i in range(500)]
                sid = started.json()["session_id"]
                responses = await asyncio.gather(
                    *[
                        client.post("/refresh", json={"session_id": sid}, headers={"Origin": base})
                        for _ in range(2)
                    ]
                )
                assert sorted(response.status_code for response in responses) == [200, 409]
            assert (await client.get("/health")).status_code == 200
    finally:
        server.should_exit = True
        await asyncio.wait_for(serving, timeout=3)
        listener.close()
    assert not app.state.monitor.broadcaster.tasks
    assert not app.state.monitor.commands
