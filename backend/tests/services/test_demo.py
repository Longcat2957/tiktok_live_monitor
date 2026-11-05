import asyncio
from itertools import count

from app.realtime.broadcaster import WebSocketBroadcaster
from app.schemas.events import Status
from app.services.demo import DemoStream
from app.services.event_sink import EventSink


async def test_reconnecting_mock_continues_sequence() -> None:
    queue = asyncio.Queue(10)
    manager = WebSocketBroadcaster(Status(source="mock", state="idle", message="test"))
    sequence = count()
    for number in range(1, 11):
        source = DemoStream(EventSink(queue, manager), 3600, sequence)
        task = asyncio.create_task(source.run())
        try:
            comment = await asyncio.wait_for(queue.get(), timeout=1)
            assert comment.comment.startswith(f"[데모 #{number}] ")
            queue.task_done()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            while not queue.empty():
                queue.get_nowait()
                queue.task_done()


def test_source_sink_bounds_queue_counts_drops_and_rate_limits_logs(caplog):
    from app.schemas.events import Comment, User

    queue = asyncio.Queue(2)
    manager = WebSocketBroadcaster(Status(source="mock", state="idle", message="test"))
    sink = EventSink(queue, manager)
    for number in range(5):
        sink.publish(Comment(user=User(nickname="n", unique_id="u"), comment=str(number)))
    assert manager.dropped_comments == 3
    assert [queue.get_nowait().comment for _ in range(2)] == ["3", "4"]
    assert len(caplog.records) == 2  # Cumulative drops 1 and 2, no per-event flood.
    sink.active = False
    sink.publish(Comment(user=User(nickname="n", unique_id="u"), comment="late"))
    assert queue.empty()


async def test_demo_updates_distinct_metrics_for_both_platforms_each_cycle():
    from app.schemas.events import YouTubeStatus

    queue = asyncio.Queue(20)
    manager = WebSocketBroadcaster(
        Status(
            source="mock",
            state="connecting",
            message="test",
            youtube=YouTubeStatus(video_id="demo", state="connecting", message="test"),
        )
    )
    source = DemoStream(
        EventSink(queue, manager),
        0.001,
        count(),
        EventSink(queue, manager, platform="youtube"),
    )
    task = asyncio.create_task(source.run())
    try:
        youtube_comments = 0
        async with asyncio.timeout(1):
            while youtube_comments < 2:
                event = await queue.get()
                queue.task_done()
                if event.platform == "youtube":
                    youtube_comments += 1
        assert manager.status.live.viewers == 129 and manager.status.live.likes == 1217
        assert (
            manager.status.youtube.live.viewers == 65 and manager.status.youtube.live.likes == 487
        )
        assert manager.status.youtube.live.state == "live"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
