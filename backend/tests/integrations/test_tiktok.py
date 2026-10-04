import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from TikTokLive.client.errors import UserOfflineError
from TikTokLive.events import CommentEvent

from app.config import Settings
from app.integrations import tiktok
from app.integrations.tiktok import TikTokStream, parse_comment
from app.realtime.broadcaster import WebSocketBroadcaster
from app.schemas.events import Status
from app.services.event_sink import EventSink


def test_installed_tiktoklive_event_api() -> None:
    event = CommentEvent.from_dict(
        {"user": {"nickname": "민수", "displayId": "minsu123"}, "content": "안녕하세요 💚"}
    )
    payload = parse_comment(event)
    assert payload is not None
    assert payload.comment == "안녕하세요 💚"
    assert payload.user.nickname == "민수"
    assert payload.user.unique_id == "minsu123"


def test_comment_extraction_preserves_text() -> None:
    payload = parse_comment(
        SimpleNamespace(
            user=SimpleNamespace(nickname="민수", unique_id="minsu"), comment=" hello\n💚 "
        )
    )
    assert payload.comment == " hello\n💚 "
    assert payload.user.nickname == "민수"
    assert parse_comment(SimpleNamespace(comment=" ")) is None
    assert parse_comment(SimpleNamespace(user=None, comment="hello")) is None


async def test_offline_backoff_and_cancellation_cleanup() -> None:
    manager = WebSocketBroadcaster(Status(source="tiktok", state="connecting", message="test"))
    settings = Settings(
        _env_file=None,
        tiktok_reconnect_min_seconds=0.01,
        tiktok_reconnect_max_seconds=0.02,
    )
    source = TikTokStream(EventSink(asyncio.Queue(10), manager), settings, "test")
    fake = MagicMock()
    fake.start = AsyncMock(side_effect=UserOfflineError())
    fake.disconnect = AsyncMock()
    fake.web.close = AsyncMock()
    with patch("app.integrations.tiktok.TikTokLiveClient", return_value=fake):
        task = asyncio.create_task(source.run())
        await asyncio.sleep(0.065)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert manager.status.state == "waiting"
    assert 2 <= fake.start.await_count <= 6
    assert source.delay == 0.02
    assert fake.disconnect.await_count == fake.start.await_count
    assert fake.web.close.await_count == fake.start.await_count


async def test_connected_cancellation_closes_resources() -> None:
    manager = WebSocketBroadcaster(Status(source="tiktok", state="connecting", message="test"))
    source = TikTokStream(EventSink(asyncio.Queue(10), manager), Settings(_env_file=None), "test")
    connection = asyncio.create_task(asyncio.Event().wait())
    fake = MagicMock()
    fake.start = AsyncMock(return_value=connection)

    async def disconnect():
        connection.cancel()

    fake.disconnect = AsyncMock(side_effect=disconnect)
    fake.web.close = AsyncMock()
    with patch("app.integrations.tiktok.TikTokLiveClient", return_value=fake):
        task = asyncio.create_task(source.run())
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert connection.done()
    fake.web.close.assert_awaited_once()
    fake.start.assert_awaited_once_with(
        fetch_gift_info=False, fetch_room_info=False, process_connect_events=False
    )


async def test_cancel_during_disconnect_does_not_reconnect():
    manager = WebSocketBroadcaster(Status(source="tiktok", state="connecting", message="test"))
    source = TikTokStream(
        EventSink(asyncio.Queue(10), manager),
        Settings(_env_file=None, tiktok_reconnect_min_seconds=0.001),
        "test",
    )
    cleaning = asyncio.Event()
    fake = MagicMock()
    fake.start = AsyncMock(side_effect=UserOfflineError())

    async def disconnect():
        cleaning.set()
        await asyncio.Event().wait()

    fake.disconnect = AsyncMock(side_effect=disconnect)
    fake.web.close = AsyncMock()
    with patch("app.integrations.tiktok.TikTokLiveClient", return_value=fake):
        task = asyncio.create_task(source.run())
        await asyncio.wait_for(cleaning.wait(), 1)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=1)
        assert task in done and task.cancelled()
    assert fake.start.await_count == 1
    fake.web.close.assert_awaited_once()
    fake.remove_all_listeners.assert_called_once()


def test_comment_limits_and_no_payload_logging(caplog):
    event = SimpleNamespace(
        user=SimpleNamespace(nickname="n", unique_id="u"), comment="secret" * 2000
    )
    assert parse_comment(event) is None
    assert "secret" not in caplog.text


def test_invalid_event_warnings_are_bounded(monkeypatch, caplog):
    monkeypatch.setitem(tiktok._invalid_events, "comment", 0)
    event = SimpleNamespace(user=None, comment="private event payload")
    for _ in range(9):
        assert parse_comment(event) is None
    warnings = [record.message for record in caplog.records if "invalid comment" in record.message]
    assert [int(message.split(": ")[1].split()[0]) for message in warnings] == [1, 2, 4, 8]
    assert "private event payload" not in caplog.text


async def test_unexpected_adapter_error_logs_location_without_payload(caplog):
    manager = WebSocketBroadcaster(Status(source="tiktok", state="idle", message="test"))
    source = TikTokStream(
        EventSink(asyncio.Queue(10), manager),
        Settings(_env_file=None, tiktok_reconnect_min_seconds=300, tiktok_reconnect_max_seconds=300),
        "test",
    )
    fake = MagicMock()

    async def failing_start(**_kwargs):
        raise RuntimeError("private event payload")

    fake.start = AsyncMock(side_effect=failing_start)
    fake.disconnect = AsyncMock()
    fake.web.close = AsyncMock()
    with patch("app.integrations.tiktok.TikTokLiveClient", return_value=fake):
        task = asyncio.create_task(source.run())
        try:
            async with asyncio.timeout(1):
                while "Unexpected TikTok adapter failure" not in caplog.text:
                    await asyncio.sleep(0.001)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert "RuntimeError at " in caplog.text
    assert " in failing_start" in caplog.text
    assert "private event payload" not in caplog.text


async def test_upstream_cleanup_swallowing_cancel_cannot_restart_source():
    source = TikTokStream(
        EventSink(
            asyncio.Queue(10),
            WebSocketBroadcaster(Status(source="tiktok", state="idle", message="")),
        ),
        Settings(_env_file=None, tiktok_reconnect_min_seconds=0.001),
        "test",
    )
    cleaning = asyncio.Event()
    fake = MagicMock()
    fake.start = AsyncMock(side_effect=UserOfflineError())

    async def disconnect():
        cleaning.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass

    fake.disconnect = AsyncMock(side_effect=disconnect)
    fake.web.close = AsyncMock()
    with patch("app.integrations.tiktok.TikTokLiveClient", return_value=fake):
        task = asyncio.create_task(source.run())
        await cleaning.wait()
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=1)
        assert task in done and task.cancelled()
        assert fake.start.await_count == 1
