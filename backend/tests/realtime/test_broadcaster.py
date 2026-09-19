import asyncio
from datetime import datetime

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.realtime.broadcaster import WebSocketBroadcaster, enqueue_event
from app.schemas.events import Comment, Status, User


def test_mock_websocket_and_disconnect():
    app = create_app(Settings(_env_file=None, comment_source="mock", mock_interval_seconds=0.01))
    with TestClient(app, base_url="http://localhost") as client:
        sid = client.get("/config").json()["session_id"]
        assert (
            client.post("/account", json={"source": "mock", "session_id": sid}).status_code == 200
        )
        with client.websocket_connect(
            "ws://localhost/ws", headers={"Origin": "http://localhost"}
        ) as socket:
            assert socket.receive_json()["type"] == "status"
            while (payload := socket.receive_json())["type"] != "comment":
                pass
            assert datetime.fromisoformat(payload["received_at"].replace("Z", "+00:00")).tzinfo
            assert payload["comment"]
            assert client.get("/health").json()["websocket_connections"] == 1
            socket.close()
            while socket.receive()["type"] != "websocket.close":
                pass
        assert client.get("/health").json()["websocket_connections"] == 0


def test_queue_drops_oldest() -> None:
    queue: asyncio.Queue[Comment] = asyncio.Queue(2)
    for body in ["one", "two", "three"]:
        enqueue_event(queue, Comment(user=User(nickname="n", unique_id="u"), comment=body))
    assert queue.qsize() == 2
    assert queue.get_nowait().comment == "two"
    assert queue.get_nowait().comment == "three"


class Socket:
    def __init__(self, *, broken=False, slow=False):
        self.broken = broken
        self.slow = slow
        self.messages = []
        self.accepts = 0
        self.closed = False

    async def accept(self):
        self.accepts += 1

    async def send_json(self, value):
        if self.broken:
            raise RuntimeError("disconnected")
        if self.slow:
            await asyncio.Event().wait()
        self.messages.append(value)

    async def close(self, code):
        self.closed = True


async def test_broken_and_slow_peers_do_not_block_healthy_peer() -> None:
    manager = WebSocketBroadcaster(
        Status(source="mock", state="connected", message="ok"), send_timeout=0.03
    )
    healthy, broken, slow = Socket(), Socket(broken=True), Socket(slow=True)
    for socket in [healthy, broken, slow, healthy]:
        await manager.connect(socket)
    for body in ["one", "two", "three"]:
        manager.broadcast(Comment(user=User(nickname="n", unique_id="u"), comment=body))
    await asyncio.sleep(0.08)
    assert healthy.accepts == 1
    assert [m["comment"] for m in healthy.messages if m["type"] == "comment"] == [
        "one",
        "two",
        "three",
    ]
    assert list(manager.clients) == [healthy]
    assert broken.closed and slow.closed
    await manager.close()
    assert not manager.clients


async def test_peer_queue_overflow_disconnects_only_slow_client() -> None:
    manager = WebSocketBroadcaster(
        Status(source="mock", state="connected", message="ok"), capacity=1
    )
    slow = Socket(slow=True)
    await manager.connect(slow)
    message = Comment(user=User(nickname="n", unique_id="u"), comment="x")
    manager.broadcast(message)
    manager.broadcast(message)
    await asyncio.sleep(0.01)
    assert not manager.clients
    assert slow.closed


async def test_burst_keeps_fast_peer_order_and_disconnects_only_slow_peer():
    manager = WebSocketBroadcaster(Status(source="mock", state="connected", message="ok"))
    fast, slow = Socket(), Socket(slow=True)
    await manager.connect(fast)
    await manager.connect(slow)
    queue = asyncio.Queue(500)
    for number in range(500):
        enqueue_event(queue, Comment(user=User(nickname="n", unique_id="u"), comment=str(number)))
    consumer = asyncio.create_task(manager.consume(queue))
    try:
        await asyncio.wait_for(queue.join(), 1)
        await asyncio.sleep(0.02)
        assert not fast.closed
        assert slow.closed
        assert [m["comment"] for m in fast.messages if m["type"] == "comment"] == [
            str(i) for i in range(500)
        ]
    finally:
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)
        await manager.close()


async def test_session_boundary_and_peer_limit():
    manager = WebSocketBroadcaster(
        Status(source="mock", state="idle", message="old"), max_clients=1
    )
    fast, rejected = Socket(), Socket()
    assert await manager.connect(fast)
    assert await manager.connect(fast)  # Duplicate registration reuses the accepted peer.
    assert not await manager.connect(rejected)
    assert rejected.closed
    old = manager.status.session_id
    manager.broadcast(Comment(user=User(nickname="n", unique_id="u"), comment="old"))
    status = Status(source="mock", state="connecting", message="new")
    manager.begin_session(status)
    manager.update_status("error", "stale", old)
    await asyncio.sleep(0.01)
    assert manager.status == status
    assert all(m.get("comment") != "old" for m in fast.messages)
    assert fast.messages[-1]["session_id"] == status.session_id
    await manager.close()


async def test_concurrent_handshakes_respect_connection_limit():
    manager = WebSocketBroadcaster(Status(source="mock", state="idle", message="ok"), max_clients=1)
    accepting, release = asyncio.Event(), asyncio.Event()

    class Pending(Socket):
        async def accept(self):
            accepting.set()
            await release.wait()

    first, second = Pending(), Socket()
    opening = asyncio.create_task(manager.connect(first))
    await accepting.wait()
    assert not await manager.connect(second)
    assert second.closed and second.accepts == 0
    release.set()
    assert await opening
    assert manager.accepting == 0
    await manager.close()
