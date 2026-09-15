import asyncio
from unittest.mock import patch

import pytest

from app.config import Settings
from app.models import Comment, User
from app.session import ConflictError, Monitor, UnavailableError


async def eventually(predicate, timeout=1):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.001)


def make_monitor():
    return Monitor(
        Settings(
            _env_file=None,
            comment_source="mock",
            mock_interval_seconds=0.01,
            tiktok_reconnect_min_seconds=0.01,
            tiktok_reconnect_max_seconds=0.02,
        )
    )


async def start(monitor):
    await monitor.change("start", monitor.manager.status.session_id, source="mock")
    await eventually(lambda: monitor.source_task is not None)


async def test_concurrent_changes_only_one_wins_and_old_events_are_ignored():
    monitor = make_monitor()
    try:
        await start(monitor)
        old_sink = monitor.sink
        sid = monitor.manager.status.session_id
        results = await asyncio.gather(
            monitor.change("refresh", sid), monitor.change("stop", sid), return_exceptions=True
        )
        assert sum(isinstance(result, ConflictError) for result in results) == 1
        current = monitor.manager.status
        old_sink.status("error", "old event")
        old_sink.publish(Comment(user=User(nickname="n", unique_id="u"), comment="old"))
        assert monitor.manager.status == current
        assert not old_sink.active
    finally:
        await monitor.close()


@pytest.mark.parametrize("worker", ["source_task", "consumer_task"])
async def test_worker_exit_recovers_without_user_action(worker):
    monitor = make_monitor()
    try:
        await start(monitor)
        old = getattr(monitor, worker)
        old.cancel()
        await eventually(lambda: monitor.recoveries == 1)
        assert monitor.fault == "worker_stopped"
        assert not monitor.healthy
        await eventually(lambda: getattr(monitor, worker) is not old and monitor.healthy)
        assert monitor.manager.status.state in {"connecting", "connected"}
    finally:
        await monitor.close()


async def test_request_cancellation_does_not_interrupt_transition():
    monitor = make_monitor()
    cleanup = asyncio.Event()
    release = asyncio.Event()

    class Source:
        async def run(self):
            try:
                await asyncio.Event().wait()
            finally:
                cleanup.set()
                await release.wait()

    try:
        with patch.object(monitor, "_make_source", return_value=Source()):
            await start(monitor)
            await asyncio.sleep(0)
            request = asyncio.create_task(monitor.change("stop", monitor.manager.status.session_id))
            await cleanup.wait()
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)
            release.set()
            await eventually(lambda: monitor.manager.status.state == "idle")
            assert monitor.healthy
            assert monitor.source_task is None
    finally:
        release.set()
        await monitor.close()


async def test_uncooperative_worker_is_quarantined_and_new_source_is_blocked():
    monitor = make_monitor()
    release = asyncio.Event()
    entered = asyncio.Event()

    class Source:
        async def run(self):
            entered.set()
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    pass

    with (
        patch("app.session.STOP_TIMEOUT", 0.01),
        patch.object(monitor, "_make_source", return_value=Source()),
    ):
        try:
            await start(monitor)
            await entered.wait()
            sink = monitor.sink
            sid = monitor.manager.status.session_id
            with pytest.raises(UnavailableError):
                await monitor.change("stop", sid)
            assert not monitor.healthy
            assert monitor.fault == "shutdown_timeout"
            assert not sink.active
            with pytest.raises(UnavailableError):
                await monitor.change("refresh", sid)
        finally:
            release.set()
            await eventually(lambda: monitor.source_task.done())
            await monitor.close()


async def test_shutdown_during_transition_never_starts_another_receiver():
    monitor = make_monitor()
    cleaning, release = asyncio.Event(), asyncio.Event()

    class Source:
        async def run(self):
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()

    with patch.object(monitor, "_make_source", return_value=Source()) as factory:
        await start(monitor)
        await asyncio.sleep(0)
        changing = asyncio.create_task(monitor.change("refresh", monitor.manager.status.session_id))
        await cleaning.wait()
        closing = asyncio.create_task(monitor.close())
        await eventually(lambda: monitor.closed)
        release.set()
        result = await asyncio.gather(changing, return_exceptions=True)
        await closing
        assert isinstance(result[0], UnavailableError)
        assert factory.call_count == 1
        assert monitor.source_task is None
        assert not monitor.commands


async def test_runtime_logging_does_not_enable_dependency_debug():
    import logging

    monitor = make_monitor()
    app_logger = logging.getLogger("app")
    root_level, app_level = logging.getLogger().level, app_logger.level
    try:
        await start(monitor)
        await monitor.change(
            "settings", monitor.manager.status.session_id, settings={"log_level": "DEBUG"}
        )
        assert app_logger.level == logging.DEBUG
        assert logging.getLogger().level == root_level
        assert monitor.config.comment_history_size == 30
    finally:
        await monitor.close()
        app_logger.setLevel(app_level)
