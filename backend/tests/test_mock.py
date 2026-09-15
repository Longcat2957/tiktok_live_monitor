import asyncio
from itertools import count

from app.models import Status
from app.sources.base import SourceSink
from app.sources.mock import MockSource
from app.websocket import WebSocketManager


async def test_reconnecting_mock_continues_sequence() -> None:
    queue = asyncio.Queue(10)
    manager = WebSocketManager(Status(source="mock", state="idle", message="test"))
    sequence = count()
    for number in range(1, 11):
        source = MockSource(SourceSink(queue, manager), 3600, sequence)
        task = asyncio.create_task(source.run())
        try:
            comment = await asyncio.wait_for(queue.get(), timeout=1)
            assert comment.comment.startswith(f"[데모 #{number}] ")
            queue.task_done()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def test_source_sink_bounds_queue_counts_drops_and_rate_limits_logs(caplog):
    from app.models import Comment, User

    queue = asyncio.Queue(2)
    manager = WebSocketManager(Status(source="mock", state="idle", message="test"))
    sink = SourceSink(queue, manager)
    for number in range(5):
        sink.publish(Comment(user=User(nickname="n", unique_id="u"), comment=str(number)))
    assert manager.dropped_comments == 3
    assert [queue.get_nowait().comment for _ in range(2)] == ["3", "4"]
    assert len(caplog.records) == 2  # Cumulative drops 1 and 2, no per-event flood.
    sink.active = False
    sink.publish(Comment(user=User(nickname="n", unique_id="u"), comment="late"))
    assert queue.empty()
