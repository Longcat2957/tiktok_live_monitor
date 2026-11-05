import asyncio
import sqlite3
from unittest.mock import patch

import pytest

from app.config import Settings
from app.schemas.events import Comment, LiveInfo, User
from app.services.errors import UnavailableError
from app.services.monitor import MonitorService


async def eventually(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.001)


class Stream:
    def __init__(self, sink):
        self.sink = sink

    async def run(self):
        self.sink.status("connected", "test")
        self.sink.live(LiveInfo(state="live"))
        await asyncio.Event().wait()


def monitor():
    return MonitorService(
        Settings(
            _env_file=None,
            tiktok_reconnect_min_seconds=0.01,
            tiktok_reconnect_max_seconds=0.02,
            mock_interval_seconds=0.01,
        )
    )


async def start(service):
    await service.initialize()
    await service.start(
        service.broadcaster.status.session_id,
        source="tiktok",
        username="test",
        youtube_video_id="abcdefghijk",
    )
    await eventually(lambda: service.youtube_stream_task is not None)


@pytest.mark.parametrize("platform", ["tiktok", "youtube"])
async def test_source_worker_restart_preserves_other_receiver_consumer_and_session(platform):
    service = monitor()
    with (
        patch.object(service, "_make_stream", Stream),
        patch.object(service, "_make_youtube_stream", Stream),
    ):
        try:
            await start(service)
            session_id = service.broadcaster.status.session_id
            consumer = service.consumer_task
            old_task = service.stream_task if platform == "tiktok" else service.youtube_stream_task
            old_sink = service.sink if platform == "tiktok" else service.youtube_sink
            other = service.youtube_stream_task if platform == "tiktok" else service.stream_task
            old_task.cancel()
            await eventually(lambda: service.recoveries == 1)
            await eventually(
                lambda: (
                    (service.stream_task if platform == "tiktok" else service.youtube_stream_task)
                    is not old_task
                )
            )
            assert service.consumer_task is consumer and not consumer.done()
            assert (
                service.youtube_stream_task if platform == "tiktok" else service.stream_task
            ) is other
            assert not other.done()
            other_sink = service.youtube_sink if platform == "tiktok" else service.sink
            event = Comment(user=User(nickname="n", unique_id="u"), comment="still receiving")
            other_sink.publish(event)
            received = service.queue.get_nowait()
            service.queue.task_done()
            assert received.id == event.id and received.platform == other_sink.platform
            assert service.broadcaster.status.session_id == session_id
            assert not old_sink.active
            status = service.broadcaster.status
            old_sink.status("error", "stale")
            before = service.queue.qsize()
            old_sink.publish(Comment(user=User(nickname="n", unique_id="u"), comment="stale"))
            assert service.queue.qsize() == before
            assert service.broadcaster.status == status
        finally:
            await service.close()
        assert service.youtube_stream_task is None and not service.source_supervisors


async def test_refresh_settings_and_stop_preserve_then_clear_youtube_selection():
    service = monitor()
    with (
        patch.object(service, "_make_stream", Stream),
        patch.object(service, "_make_youtube_stream", Stream),
    ):
        try:
            await start(service)
            first_sink = service.youtube_sink
            refreshed = await service.refresh(service.broadcaster.status.session_id)
            assert refreshed.youtube.video_id == "abcdefghijk"
            updated = await service.update_settings(
                refreshed.session_id, {"comment_history_size": 10}
            )
            assert updated.youtube.video_id == "abcdefghijk"
            assert not first_sink.active
            stopped = await service.stop(updated.session_id)
            assert stopped.youtube is None and stopped.state == "idle"
            assert service.youtube_stream_task is None and service.consumer_task is None
        finally:
            await service.close()


async def test_shared_queue_preserves_interleaving_and_archive_contexts():
    service = monitor()
    with (
        patch.object(service, "_make_stream", Stream),
        patch.object(service, "_make_youtube_stream", Stream),
    ):
        await start(service)
        try:
            # Synchronous acceptance prevents the consumer from running between publications.
            for sink, body in [
                (service.sink, "one"),
                (service.youtube_sink, "two"),
                (service.sink, "three"),
            ]:
                sink.publish(Comment(user=User(nickname="n", unique_id="same"), comment=body))
            assert [(service.queue.get_nowait().platform) for _ in range(3)] == [
                "tiktok",
                "youtube",
                "tiktok",
            ]
            service.youtube_sink.diagnostic("source_state", details={"state": "connected"})
        finally:
            await service.close()
        with sqlite3.connect(service.config.archive_path) as db:
            assert db.execute(
                "SELECT source, username, comment FROM comments ORDER BY id"
            ).fetchall() == [
                ("tiktok", "test", "one"),
                ("youtube", "abcdefghijk", "two"),
                ("tiktok", "test", "three"),
            ]
            assert db.execute(
                "SELECT source, username FROM diagnostics WHERE source='youtube'"
            ).fetchall()


async def test_demo_delivers_both_platforms_without_credentials():
    service = monitor()
    delivered = []
    original = service.broadcaster.broadcast

    def capture(event):
        if isinstance(event, Comment):
            delivered.append(event)
        original(event)

    try:
        await service.initialize()
        with patch.object(service.broadcaster, "broadcast", capture):
            await service.start(service.broadcaster.status.session_id, source="mock")
            await eventually(lambda: len(delivered) >= 2)
            assert [event.platform for event in delivered[:2]] == ["tiktok", "youtube"]
            assert service.broadcaster.status.youtube.state == "connected"
            assert service.broadcaster.status.youtube.live.state == "live"
    finally:
        await service.close()


async def test_uncooperative_youtube_worker_blocks_new_sessions_and_invalidates_both_sinks():
    service = monitor()
    release, entered = asyncio.Event(), asyncio.Event()

    class StuckStream:
        def __init__(self, sink):
            pass

        async def run(self):
            entered.set()
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    pass

    with (
        patch.object(service, "_make_stream", Stream),
        patch.object(service, "_make_youtube_stream", StuckStream),
        patch("app.services.monitor.STOP_TIMEOUT", 0.01),
    ):
        try:
            await start(service)
            await entered.wait()
            with pytest.raises(UnavailableError):
                await service.stop(service.broadcaster.status.session_id)
            assert not service.healthy
            assert not service.sink.active and not service.youtube_sink.active
            with pytest.raises(UnavailableError):
                await service.refresh(service.broadcaster.status.session_id)
        finally:
            release.set()
            await eventually(lambda: service.youtube_stream_task.done())
            await service.close()
