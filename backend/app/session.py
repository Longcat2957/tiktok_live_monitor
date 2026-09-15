import asyncio
import logging
from itertools import count
from typing import Literal

from .config import RuntimeSettings, Settings
from .models import FeedEvent, SourceName, Status
from .sources.base import CommentSource, SourceSink
from .sources.mock import MockSource
from .websocket import WebSocketManager

logger = logging.getLogger(__name__)
STOP_TIMEOUT = 12.0
Action = Literal["start", "stop", "refresh", "settings"]


class ConflictError(Exception):
    pass


class UnavailableError(Exception):
    pass


def observe(task: asyncio.Task[None]) -> None:
    if not task.cancelled():
        if (error := task.exception()) is not None:
            logger.error("Worker %s failed: %s", task.get_name(), type(error).__name__)


class Monitor:
    """Owns the single account, its workers, and serialized session transitions."""

    def __init__(self, config: Settings) -> None:
        self.config = config
        self.manager = WebSocketManager(self._status())
        self.queue: asyncio.Queue[FeedEvent] = asyncio.Queue(config.comment_queue_size)
        self.source_task: asyncio.Task[None] | None = None
        self.consumer_task: asyncio.Task[None] | None = None
        self.supervisor_task: asyncio.Task[None] | None = None
        self.sink: SourceSink | None = None
        self.lock = asyncio.Lock()
        self.commands: set[asyncio.Task[Status]] = set()
        self.stuck: set[asyncio.Task[None]] = set()
        self.closed = False
        self.fault: str | None = None
        self.recoveries = 0
        self.mock_sequence = count()

    def _status(self, source: SourceName | None = None, username: str | None = None) -> Status:
        return Status(
            source=source or self.config.comment_source,
            username=username,
            state="connecting" if source else "idle",
            message="댓글 수신 준비 중" if source else "모드를 선택하고 시작해주세요",
            comment_history_size=self.config.comment_history_size,
        )

    @property
    def runtime_settings(self) -> RuntimeSettings:
        return RuntimeSettings.model_validate(
            {name: getattr(self.config, name) for name in RuntimeSettings.model_fields}
        )

    @property
    def healthy(self) -> bool:
        active = self.manager.status.state != "idle"
        return (
            not self.closed
            and self.fault is None
            and (not active or self.supervisor_task is not None and not self.supervisor_task.done())
        )

    def _make_source(self, sink: SourceSink) -> CommentSource:
        status = self.manager.status
        if status.source == "mock":
            return MockSource(sink, self.config.mock_interval_seconds, self.mock_sequence)
        from .sources.tiktok import TikTokSource

        return TikTokSource(sink, self.config, status.username or "")

    async def change(
        self,
        action: Action,
        session_id: str,
        *,
        source: SourceName | None = None,
        username: str | None = None,
        settings: dict[str, object] | None = None,
    ) -> Status:
        if self.closed or len(self.commands) >= 16:
            raise UnavailableError("요청을 처리할 수 없습니다. 잠시 후 다시 시도해주세요.")
        command = asyncio.create_task(
            self._change(action, session_id, source, username, settings), name="monitor-change"
        )
        self.commands.add(command)

        def done(task: asyncio.Task[Status]) -> None:
            self.commands.discard(task)
            if not task.cancelled():
                task.exception()

        command.add_done_callback(done)
        # A browser disconnect cannot interrupt an accepted transition halfway through.
        return await asyncio.shield(command)

    async def _change(
        self,
        action: Action,
        session_id: str,
        source: SourceName | None,
        username: str | None,
        settings: dict[str, object] | None,
    ) -> Status:
        async with self.lock:
            self.stuck = {task for task in self.stuck if not task.done()}
            if self.closed or self.stuck:
                raise UnavailableError("이전 연결을 종료하지 못했습니다. 서버를 재시작해주세요.")
            current = self.manager.status
            if session_id != current.session_id:
                raise ConflictError(
                    "다른 화면에서 상태가 변경되었습니다. 현재 상태를 확인해주세요."
                )
            if action == "start":
                if current.state != "idle" or source is None:
                    raise ConflictError("모니터 종료 후 첫 화면에서 시작해주세요.")
            elif action == "stop":
                source, username = None, None
            else:
                if current.state == "idle":
                    raise ConflictError("종료된 모니터에는 적용할 수 없습니다.")
                source, username = current.source, current.username
            updated = self.runtime_settings
            if action == "settings":
                changes = settings or {}
                irrelevant = (
                    {"mock_interval_seconds"}
                    if source == "tiktok"
                    else {"tiktok_reconnect_min_seconds", "tiktok_reconnect_max_seconds"}
                )
                if irrelevant.intersection(changes):
                    raise ConflictError("현재 모드에서 사용하는 설정만 변경해주세요.")
                updated = RuntimeSettings.model_validate(updated.model_dump() | changes)
            if not await self._stop_session():
                raise UnavailableError("이전 연결을 종료하지 못했습니다. 서버를 재시작해주세요.")
            if self.closed:
                raise UnavailableError("서버가 종료 중입니다.")
            self.config = self.config.model_copy(update=updated.model_dump())
            logging.getLogger("app").setLevel(self.config.log_level)
            self.queue = asyncio.Queue(self.config.comment_queue_size)
            self.fault = None
            self.manager.begin_session(self._status(source, username))
            if source is not None:
                self.supervisor_task = asyncio.create_task(
                    self._supervise(), name="monitor-supervisor"
                )
                self.supervisor_task.add_done_callback(observe)
            return self.manager.status

    async def _stop_workers(self) -> bool:
        if self.sink is not None:
            self.sink.active = False
        workers = {t for t in (self.source_task, self.consumer_task) if t is not None}
        for task in workers:
            if not task.done():
                task.cancel()
        if not workers:
            return True
        _, pending = await asyncio.wait(workers, timeout=STOP_TIMEOUT)
        self.stuck.update(pending)
        return not pending

    async def _stop_session(self) -> bool:
        if self.sink is not None:
            self.sink.active = False
        supervisor = self.supervisor_task
        if supervisor is not None and not supervisor.done():
            supervisor.cancel()
            _, pending = await asyncio.wait({supervisor}, timeout=STOP_TIMEOUT + 0.5)
            if pending:
                self.stuck.update(pending)
                self.stuck.update(
                    t
                    for t in (self.source_task, self.consumer_task)
                    if t is not None and not t.done()
                )
        if not self.stuck and (supervisor is None or supervisor.done()):
            # Covers cancellation arriving during the supervisor's existing cleanup.
            await self._stop_workers()
        self.stuck = {task for task in self.stuck if not task.done()}
        if self.stuck:
            self.fault = "shutdown_timeout"
            self.manager.update_status(
                "error", "연결 종료 시간 초과 · 서버 재시작 필요", self.manager.status.session_id
            )
            return False
        self.source_task = self.consumer_task = self.supervisor_task = None
        return True

    async def _supervise(self) -> None:
        delay = self.config.tiktok_reconnect_min_seconds
        while True:
            self.sink = SourceSink(self.queue, self.manager)
            self.fault = None
            self.sink.status("connecting", "댓글 수신 준비 중")
            try:
                source = self._make_source(self.sink)
                self.consumer_task = asyncio.create_task(
                    self.manager.consume(self.queue), name="comment-consumer"
                )
                self.source_task = asyncio.create_task(source.run(), name="comment-source")
                for task in (self.consumer_task, self.source_task):
                    task.add_done_callback(observe)
                await asyncio.wait(
                    {self.consumer_task, self.source_task}, return_when=asyncio.FIRST_COMPLETED
                )
                # A source must run until stopped, including when its upstream child is cancelled.
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Worker startup failed: %s", type(exc).__name__)
            finally:
                stopped = await self._stop_workers()
            self.fault = "worker_stopped" if stopped else "shutdown_timeout"
            self.manager.update_status(
                "error",
                "댓글 수신 오류 · 자동 복구 대기"
                if stopped
                else "연결 종료 시간 초과 · 서버 재시작 필요",
                self.manager.status.session_id,
            )
            if not stopped:
                return
            self.recoveries += 1
            logger.warning("Worker stopped; retrying in %.2fs", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, self.config.tiktok_reconnect_max_seconds)

    async def close(self) -> None:
        self.closed = True
        if self.commands:
            await asyncio.wait(self.commands, timeout=STOP_TIMEOUT + 1)
        await self._stop_session()
        await self.manager.close()
