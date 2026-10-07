import asyncio
import json
from datetime import datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.realtime.broadcaster import WebSocketBroadcaster, enqueue_event
from app.schemas.events import Activity, Comment, Status, User
from app.services.gift_images import GiftImageCache


def test_mock_websocket_and_disconnect():
    app = create_app(Settings(_env_file=None, mock_interval_seconds=0.01))
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

    async def send_text(self, value):
        if self.broken:
            raise RuntimeError("disconnected")
        if self.slow:
            await asyncio.Event().wait()
        self.messages.append(json.loads(value))

    async def close(self, code):
        self.closed = True


async def test_broadcast_serializes_once_for_two_peers_and_preserves_wire_order(monkeypatch):
    manager = WebSocketBroadcaster(Status(source="mock", state="connected", message="ok"))
    first, second = Socket(), Socket()
    serialized = []
    original = Comment.model_dump_json

    def encode(message, *args, **kwargs):
        serialized.append(message)
        return original(message, *args, **kwargs)

    for model in (Comment, Status):
        monkeypatch.setattr(model, "model_dump_json", encode)
    try:
        await manager.connect(first)
        await manager.connect(second)
        assert serialized == [manager.status, manager.status]  # Initial snapshot per connection.
        serialized.clear()
        user = User(nickname="한글 👋", unique_id="u")
        comments = [Comment(user=user, comment=body) for body in ("<script>\n댓글", "다음 댓글")]
        manager.broadcast(comments[0])
        manager.update_status("connected", "changed", manager.status.session_id)
        manager.broadcast(comments[1])
        expected = [comments[0], manager.status, comments[1]]
        await asyncio.wait_for(
            asyncio.gather(*(peer.queue.join() for peer in manager.clients.values())), timeout=1
        )
        assert serialized == expected  # Encoding is independent of the number of peers.
        assert first.messages == second.messages
        assert first.messages[1:] == [message.model_dump(mode="json") for message in expected]
        assert manager.sent_comments == 4 and manager.last_comment_sent_id == comments[1].id
    finally:
        await manager.close()
    assert not manager.clients and not manager.tasks


async def test_broken_and_slow_peers_do_not_block_healthy_peer() -> None:
    archive = MagicMock()
    manager = WebSocketBroadcaster(
        Status(source="mock", state="connected", message="ok"), send_timeout=0.03, archive=archive
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
    assert manager.sent_comments == 3
    assert manager.last_comment_sent_id == healthy.messages[-1]["id"]
    assert datetime.fromisoformat(manager.last_comment_sent_at).tzinfo is not None
    assert {call.args[0] for call in archive.diagnostic.call_args_list} >= {
        "websocket_connected",
        "websocket_disconnected",
        "websocket_send_failed",
        "websocket_send_timeout",
    }
    await manager.close()
    assert not manager.clients


async def test_gift_url_is_registered_without_fetch_and_feed_order_is_preserved() -> None:
    cache = GiftImageCache()
    manager = WebSocketBroadcaster(
        Status(source="mock", state="connected", message="ok"), gift_images=cache
    )
    socket = Socket()
    await manager.connect(socket)
    user = User(nickname="n", unique_id="u")
    manager.broadcast(
        Activity(
            user=user,
            kind="gift",
            gift_name="Rose",
            gift_image_url="https://p16.tiktokcdn.com/gift.png?token=private",
        )
    )
    manager.broadcast(Comment(user=user, comment="after"))
    await asyncio.sleep(0)
    assert [message["type"] for message in socket.messages] == ["status", "activity", "comment"]
    assert socket.messages[1]["gift_image_url"].startswith("/gift-images/")
    assert "token" not in socket.messages[1]["gift_image_url"]
    for image_url in ("/demo-gift-rose.webp", "/untrusted.webp"):
        manager.broadcast(Activity(user=user, kind="gift", gift_image_url=image_url))
    await asyncio.sleep(0)
    assert socket.messages[-2]["gift_image_url"] == "/demo-gift-rose.webp"
    assert socket.messages[-1]["gift_image_url"] is None
    manager.begin_session(Status(source="tiktok", state="connected", message="ok"))
    manager.broadcast(Activity(user=user, kind="gift", gift_image_url="/demo-gift-rose.webp"))
    await asyncio.sleep(0)
    assert socket.messages[-1]["gift_image_url"] is None
    assert cache.client is None
    await manager.close()
    await cache.close()


async def test_peer_queue_overflow_disconnects_only_slow_client() -> None:
    archive = MagicMock()
    manager = WebSocketBroadcaster(
        Status(source="mock", state="connected", message="ok"), capacity=1, archive=archive
    )
    slow = Socket(slow=True)
    await manager.connect(slow)
    message = Comment(user=User(nickname="n", unique_id="u"), comment="x")
    manager.broadcast(message)
    manager.broadcast(message)
    await asyncio.sleep(0.01)
    assert not manager.clients
    assert slow.closed
    assert any(call.args[0] == "websocket_queue_full" for call in archive.diagnostic.call_args_list)


async def test_inflight_send_failure_keeps_its_session_and_omits_exception_text(caplog):
    archive = MagicMock()
    status = Status(source="mock", state="connected", message="")
    manager = WebSocketBroadcaster(status, archive=archive)
    sending, release = asyncio.Event(), asyncio.Event()

    class Failing(Socket):
        async def send_text(self, _value):
            sending.set()
            await release.wait()
            raise RuntimeError("private comment payload and token")

    socket = Failing()
    await manager.connect(socket)
    await sending.wait()
    manager.begin_session(Status(source="mock", state="idle", message=""))
    release.set()
    await asyncio.gather(*manager.tasks)
    calls = archive.diagnostic.call_args_list
    failure = next(call for call in calls if call.args[0] == "websocket_send_failed")
    assert failure.args[1].session_id == status.session_id
    assert failure.kwargs["details"]["error_type"] == "RuntimeError"
    assert " in send_text" in failure.kwargs["details"]["location"]
    assert "private comment payload" not in str(calls) + caplog.text
    assert manager.sent_comments == 0
    assert not manager.clients


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
