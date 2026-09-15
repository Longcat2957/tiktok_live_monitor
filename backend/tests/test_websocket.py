import asyncio
from datetime import datetime

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import Comment, Status, User
from app.websocket import WebSocketManager, enqueue_comment


def test_mock_websocket_and_disconnect() -> None:
    app = create_app(Settings(_env_file=None, comment_source="mock", mock_interval_seconds=0.01))
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as socket:
            assert socket.receive_json()["type"] == "status"
            payload = socket.receive_json()
            assert payload["type"] == "comment"
            assert payload["id"]
            assert datetime.fromisoformat(payload["received_at"].replace("Z", "+00:00")).tzinfo
            assert set(payload["user"]) == {"nickname", "unique_id"}
            assert payload["comment"]
            assert client.get("/health").json()["websocket_connections"] == 1
        assert client.get("/health").json()["websocket_connections"] == 0


def test_queue_drops_oldest() -> None:
    queue: asyncio.Queue[Comment] = asyncio.Queue(2)
    for body in ["one", "two", "three"]:
        enqueue_comment(queue, Comment(user=User(nickname="n", unique_id="u"), comment=body))
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
    manager = WebSocketManager(
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
    manager = WebSocketManager(Status(source="mock", state="connected", message="ok"), capacity=1)
    slow = Socket(slow=True)
    await manager.connect(slow)
    message = Comment(user=User(nickname="n", unique_id="u"), comment="x")
    manager.broadcast(message)
    manager.broadcast(message)
    await asyncio.sleep(0.01)
    assert not manager.clients
    assert slow.closed
