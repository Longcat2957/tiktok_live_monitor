import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from TikTokLive.client.errors import UserOfflineError
from TikTokLive.events import CommentEvent

from app.config import Settings
from app.models import Status
from app.sources.tiktok import TikTokSource, parse_comment
from app.websocket import WebSocketManager


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
    manager = WebSocketManager(Status(source="tiktok", state="connecting", message="test"))
    settings = Settings(
        _env_file=None,
        tiktok_username="test",
        tiktok_reconnect_min_seconds=0.01,
        tiktok_reconnect_max_seconds=0.02,
    )
    source = TikTokSource(asyncio.Queue(10), manager, settings)
    fake = MagicMock()
    fake.start = AsyncMock(side_effect=UserOfflineError())
    fake.disconnect = AsyncMock()
    fake.web.close = AsyncMock()
    with patch("app.sources.tiktok.TikTokLiveClient", return_value=fake):
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
    manager = WebSocketManager(Status(source="tiktok", state="connecting", message="test"))
    source = TikTokSource(
        asyncio.Queue(10), manager, Settings(_env_file=None, tiktok_username="test")
    )
    connection = asyncio.create_task(asyncio.Event().wait())
    fake = MagicMock()
    fake.start = AsyncMock(return_value=connection)

    async def disconnect():
        connection.cancel()

    fake.disconnect = AsyncMock(side_effect=disconnect)
    fake.web.close = AsyncMock()
    with patch("app.sources.tiktok.TikTokLiveClient", return_value=fake):
        task = asyncio.create_task(source.run())
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert connection.done()
    fake.web.close.assert_awaited_once()
