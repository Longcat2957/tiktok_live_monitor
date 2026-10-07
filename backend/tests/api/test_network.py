import asyncio
import json
import socket
import sqlite3
from contextlib import asynccontextmanager
from threading import Event
from unittest.mock import patch

import httpx
import pytest
import uvicorn
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from app.config import Settings
from app.main import create_app
from app.schemas.events import Comment, User
from app.services.archive import BATCH_SIZE, CAPACITY


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
                        received = []
                        while len(received) < 500:
                            event = json.loads(await peer.recv())
                            if event["type"] == "comment":
                                received.append(event["comment"])
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


class ControlledStream:
    def __init__(self, sink):
        self.sink = sink

    async def run(self):
        self.sink.status("connected", "controlled mock")
        await asyncio.Event().wait()


async def eventually(predicate, timeout=5):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.002)


@asynccontextmanager
async def running_monitor(monkeypatch):
    app = create_app(Settings(_env_file=None, comment_queue_size=5000))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.setblocking(False)
    base = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", ws="websockets-sansio"))
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        await eventually(lambda: server.started)
        monitor = app.state.monitor
        monkeypatch.setattr(monitor, "_make_stream", lambda sink: ControlledStream(sink))
        async with httpx.AsyncClient(base_url=base, headers={"Origin": base}, timeout=3) as client:
            sid = (await client.get("/config")).json()["session_id"]
            started = await client.post("/account", json={"session_id": sid, "source": "mock"})
            assert started.status_code == 200
            await eventually(lambda: monitor.sink is not None and monitor.sink.active)
            yield monitor, client, base
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(serving, timeout=10)
        finally:
            listener.close()
    assert not app.state.monitor.broadcaster.tasks
    assert app.state.monitor.archive.get_health().queued == 0
    assert app.state.monitor.archive._executor is None


async def receive_comments(socket, count):
    ids = []
    async with asyncio.timeout(15):
        while len(ids) < count:
            message = json.loads(await socket.recv())
            if message["type"] == "comment":
                ids.append(message["id"])
    return ids


async def test_storage_stall_overflow_slow_peer_and_session_change_keep_real_ws_alive(monkeypatch):
    release, writing = Event(), Event()
    async with running_monitor(monkeypatch) as (monitor, client, base):
        endpoint = base.replace("http:", "ws:") + "/ws"
        async with connect(endpoint, origin=base) as slow:
            await slow.recv()
            slow_endpoint = next(iter(monitor.broadcaster.clients))
            original_send = slow_endpoint.send_json

            async def stalled_send(message):
                if message["type"] == "comment":
                    await asyncio.Event().wait()
                await original_send(message)

            with patch.object(slow_endpoint, "send_json", stalled_send):
                async with connect(endpoint, origin=base) as fast:
                    await fast.recv()
                    await asyncio.wait_for(monitor.archive._queue.join(), 3)
                    original_write = monitor.archive._write

                    def blocked_write(batch):
                        writing.set()
                        assert release.wait(15), "Test must release the SQLite writer"
                        return original_write(batch)

                    monkeypatch.setattr(monitor.archive, "_write", blocked_write)
                    total = CAPACITY + BATCH_SIZE + 400
                    received = asyncio.create_task(receive_comments(fast, total))
                    old_sink = monitor.sink
                    try:
                        for index in range(total):
                            old_sink.publish(
                                Comment(
                                    id=f"before-{index}",
                                    user=User(nickname="n", unique_id="u"),
                                    comment="x" * 512,
                                )
                            )
                            if index % 10 == 0:
                                await asyncio.sleep(0.001)
                        assert await asyncio.to_thread(writing.wait, 2)
                        assert await received == [f"before-{index}" for index in range(total)]
                        health = await asyncio.wait_for(client.get("/health"), 3)
                        assert health.status_code == 200
                        storage = health.json()["storage"]
                        assert 0 < storage["queued"] <= CAPACITY + BATCH_SIZE
                        assert storage["dropped"] > 0
                        assert monitor.broadcaster.dropped_comments == 0
                        assert monitor.broadcaster.slow_disconnects == 1
                        assert len(monitor.broadcaster.clients) == 1
                        changed = await client.post(
                            "/refresh", json={"session_id": old_sink.session_id}
                        )
                        assert changed.status_code == 200
                        await eventually(
                            lambda: monitor.sink is not old_sink and monitor.sink.active
                        )
                        new_sink = monitor.sink
                        release.set()
                        await asyncio.wait_for(monitor.archive._queue.join(), 5)
                        new_received = asyncio.create_task(receive_comments(fast, 40))
                        old_sink.publish(
                            Comment(
                                id="stale", user=User(nickname="n", unique_id="u"), comment="old"
                            )
                        )
                        for index in range(40):
                            new_sink.publish(
                                Comment(
                                    id=f"after-{index}",
                                    user=User(nickname="n", unique_id="u"),
                                    comment="new",
                                )
                            )
                            await asyncio.sleep(0)
                        assert await new_received == [f"after-{index}" for index in range(40)]
                        await asyncio.wait_for(monitor.archive._queue.join(), 3)
                        with sqlite3.connect(monitor.config.archive_path) as database:
                            rows = database.execute(
                                "SELECT event_id, session_id FROM comments ORDER BY id"
                            ).fetchall()
                        before = [row for row in rows if row[0].startswith("before-")]
                        assert 0 < len(before) < total
                        assert [row[0] for row in before] == [
                            f"before-{index}" for index in range(len(before))
                        ]
                        assert all(row[1] == old_sink.session_id for row in before)
                        assert rows[len(before) :] == [
                            (f"after-{index}", new_sink.session_id) for index in range(40)
                        ]
                        assert monitor.archive.get_health().saved_comments == len(rows)
                    finally:
                        release.set()
                        received.cancel()
                        await asyncio.gather(received, return_exceptions=True)


async def test_connected_silence_is_observable_without_false_disconnect_and_can_resume(monkeypatch):
    monkeypatch.setattr("app.services.monitor.DIAGNOSTICS_INTERVAL_SECONDS", 0.02)
    async with running_monitor(monkeypatch) as (monitor, client, base):
        async with connect(base.replace("http:", "ws:") + "/ws", origin=base) as peer:
            await peer.recv()
            sink = monitor.sink
            sink.upstream_message()
            sink.publish(Comment(id="first", user=User(nickname="n", unique_id="u"), comment="one"))
            assert await receive_comments(peer, 1) == ["first"]
            first_sent_at = monitor.broadcaster.last_comment_sent_at
            for _ in range(5):
                sink.upstream_message()
                await asyncio.sleep(0.025)
            assert monitor.stream_task is not None and not monitor.stream_task.done()
            assert (await client.get("/health")).status_code == 200
            assert monitor.broadcaster.status.state == "connected"
            assert monitor.broadcaster.last_comment_sent_at == first_sent_at
            assert monitor.recoveries == 0 and len(monitor.broadcaster.clients) == 1
            # Real periodic snapshots commit while the connected source delivers no comments.
            await asyncio.wait_for(monitor.archive._queue.join(), 3)
            with sqlite3.connect(monitor.config.archive_path) as database:
                snapshots = [
                    json.loads(row[0])
                    for row in database.execute(
                        "SELECT details FROM diagnostics WHERE event='pipeline_snapshot' ORDER BY id"
                    )
                ]
            quiet = [snapshot for snapshot in snapshots if snapshot.get("upstream_messages") == 6]
            assert quiet and quiet[-1]["received_comments"] == 1
            assert quiet[-1]["last_comment_received_id"] == "first"
            assert quiet[-1]["last_comment_sent_id"] == "first"
            sink.publish(
                Comment(id="resumed", user=User(nickname="n", unique_id="u"), comment="two")
            )
            assert await receive_comments(peer, 1) == ["resumed"]
            await asyncio.wait_for(monitor.archive._queue.join(), 3)
            with sqlite3.connect(monitor.config.archive_path) as database:
                assert database.execute("SELECT event_id FROM comments ORDER BY id").fetchall() == [
                    ("first",),
                    ("resumed",),
                ]
