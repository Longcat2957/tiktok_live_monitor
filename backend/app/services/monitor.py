import asyncio
import logging
from functools import partial
from itertools import count
from typing import Literal, Protocol

from pydantic import ValidationError

from ..config import RuntimeSettings, Settings
from ..diagnostics import exception_location
from ..realtime.broadcaster import WebSocketBroadcaster
from ..schemas.events import FeedEvent, SourceName, Status
from ..schemas.health import HealthResponse, QueueInfo
from ..schemas.settings import SettingsResponse
from .archive import Archive
from .demo import DemoStream
from .errors import ConflictError, InvalidSettingsError, UnavailableError
from .event_sink import EventSink
from .gift_images import CachedImage, GiftImageCache

logger = logging.getLogger(__name__)
STOP_TIMEOUT = 12.0
DIAGNOSTICS_INTERVAL_SECONDS = 30.0
Action = Literal["start", "stop", "refresh", "settings"]


class EventStream(Protocol):
    async def run(self) -> None: ...


def observe(
    task: asyncio.Task[None], *, archive: Archive | None = None, status: Status | None = None
) -> None:
    if not task.cancelled():
        if (error := task.exception()) is not None:
            logger.error(
                "Worker %s failed: %s at %s",
                task.get_name(),
                type(error).__name__,
                exception_location(error),
            )
            if archive is not None:
                archive.diagnostic(
                    "worker_failed",
                    status,
                    level="error",
                    details={
                        "worker": task.get_name(),
                        "error_type": type(error).__name__,
                        "location": exception_location(error),
                    },
                )


class MonitorService:
    """Owns the single account, its workers, and serialized session transitions."""

    def __init__(self, config: Settings) -> None:
        self.config = config
        self.archive = Archive(config.archive_path)
        self.gift_images = GiftImageCache()
        self.broadcaster = WebSocketBroadcaster(
            self._status(), gift_images=self.gift_images, archive=self.archive
        )
        self.queue: asyncio.Queue[FeedEvent] = asyncio.Queue(config.comment_queue_size)
        self.stream_task: asyncio.Task[None] | None = None
        self.consumer_task: asyncio.Task[None] | None = None
        self.supervisor_task: asyncio.Task[None] | None = None
        self.sink: EventSink | None = None
        self.lock = asyncio.Lock()
        self.commands: set[asyncio.Task[Status]] = set()
        self.stuck: set[asyncio.Task[None]] = set()
        self._transitioning = False
        self.closed = False
        self.fault: str | None = None
        self.recoveries = 0
        self.demo_sequence = count()
        self.diagnostics_task: asyncio.Task[None] | None = None

    async def initialize(self) -> None:
        if self.diagnostics_task is not None:
            return
        await self.archive.start()
        self.archive.diagnostic("process_started", self.broadcaster.status)
        self.diagnostics_task = asyncio.create_task(
            self._record_snapshots(), name="pipeline-diagnostics"
        )
        self.diagnostics_task.add_done_callback(partial(observe, archive=self.archive))

    def _record_snapshot(self) -> None:
        details = self.sink.snapshot() if self.sink is not None and self.sink.active else {}
        storage = self.archive.get_health()
        details.update(
            {
                "sent_comments": self.broadcaster.sent_comments,
                "last_comment_sent_at": self.broadcaster.last_comment_sent_at,
                "last_comment_sent_id": self.broadcaster.last_comment_sent_id,
                "websocket_connections": len(self.broadcaster.clients),
                "source_queue_size": self.queue.qsize(),
                "dropped_feed_events": self.broadcaster.dropped_comments,
                "slow_disconnects": self.broadcaster.slow_disconnects,
                "storage_queued": storage.queued,
                "storage_dropped": storage.dropped,
                "storage_error": storage.error,
            }
        )
        self.archive.diagnostic("pipeline_snapshot", self.broadcaster.status, details=details)

    async def _record_snapshots(self) -> None:
        while True:
            await asyncio.sleep(DIAGNOSTICS_INTERVAL_SECONDS)
            self._record_snapshot()

    def _status(self, source: SourceName | None = None, username: str | None = None) -> Status:
        return Status(
            source=source or "tiktok",
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
        active = self.broadcaster.status.state != "idle"
        storage = self.archive.get_health()
        return (
            not self.closed
            and self.fault is None
            and storage.ready
            and storage.error is None
            and (
                not active
                or self._transitioning
                or self.supervisor_task is not None
                and not self.supervisor_task.done()
            )
        )

    def _make_stream(self, sink: EventSink) -> EventStream:
        status = self.broadcaster.status
        if status.source == "mock":
            return DemoStream(sink, self.config.mock_interval_seconds, self.demo_sequence)
        from ..integrations.tiktok import TikTokStream

        return TikTokStream(sink, self.config, status.username or "")

    def get_settings(self) -> SettingsResponse:
        return SettingsResponse(
            **self.runtime_settings.model_dump(), session_id=self.broadcaster.status.session_id
        )

    def get_health(self) -> HealthResponse:
        return HealthResponse(
            status="ok" if self.healthy else "error",
            source=self.broadcaster.status,
            websocket_connections=len(self.broadcaster.clients),
            pending_commands=len(self.commands),
            queue=QueueInfo(size=self.queue.qsize(), capacity=self.queue.maxsize),
            fault=self.fault,
            recoveries=self.recoveries,
            dropped_comments=self.broadcaster.dropped_comments,
            slow_disconnects=self.broadcaster.slow_disconnects,
            storage=self.archive.get_health(),
        )

    async def get_gift_image(self, key: str) -> CachedImage | None:
        return await self.gift_images.get(key)

    async def start(
        self, session_id: str, *, source: SourceName, username: str | None = None
    ) -> Status:
        return await self._submit("start", session_id, source=source, username=username)

    async def stop(self, session_id: str) -> Status:
        return await self._submit("stop", session_id)

    async def refresh(self, session_id: str) -> Status:
        return await self._submit("refresh", session_id)

    async def update_settings(self, session_id: str, settings: dict[str, object]) -> Status:
        return await self._submit("settings", session_id, settings=settings)

    async def _submit(
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
            current = self.broadcaster.status
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
                current_settings = updated
                changes = settings or {}
                irrelevant = (
                    {"mock_interval_seconds"}
                    if source == "tiktok"
                    else {"tiktok_reconnect_min_seconds", "tiktok_reconnect_max_seconds"}
                )
                if irrelevant.intersection(changes):
                    raise ConflictError("현재 모드에서 사용하는 설정만 변경해주세요.")
                try:
                    updated = RuntimeSettings.model_validate(updated.model_dump() | changes)
                except ValidationError:
                    raise InvalidSettingsError("설정값의 허용 범위를 확인해주세요.") from None
                if updated == current_settings:
                    return current
            # Cancelling a healthy source is expected during a validated session change.
            self._transitioning = True
            try:
                if not await self._stop_session():
                    raise UnavailableError(
                        "이전 연결을 종료하지 못했습니다. 서버를 재시작해주세요."
                    )
                if self.closed:
                    raise UnavailableError("서버가 종료 중입니다.")
                self.config = self.config.model_copy(update=updated.model_dump())
                logging.getLogger("app").setLevel(self.config.log_level)
                self.queue = asyncio.Queue(self.config.comment_queue_size)
                self.fault = None
                self.broadcaster.begin_session(self._status(source, username))
                self.archive.diagnostic(
                    "session_changed", self.broadcaster.status, details={"action": action}
                )
                if source is not None:
                    self.supervisor_task = asyncio.create_task(
                        self._supervise(), name="monitor-supervisor"
                    )
                    self.supervisor_task.add_done_callback(
                        partial(observe, archive=self.archive, status=self.broadcaster.status)
                    )
                return self.broadcaster.status
            finally:
                self._transitioning = False

    async def _stop_workers(self) -> bool:
        if self.sink is not None:
            if self.sink.active:
                self._record_snapshot()
            self.sink.active = False
        workers = {t for t in (self.stream_task, self.consumer_task) if t is not None}
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
            if self.sink.active:
                self._record_snapshot()
            self.sink.active = False
        supervisor = self.supervisor_task
        if supervisor is not None and not supervisor.done():
            supervisor.cancel()
            _, pending = await asyncio.wait({supervisor}, timeout=STOP_TIMEOUT + 0.5)
            if pending:
                self.stuck.update(pending)
                self.stuck.update(
                    t
                    for t in (self.stream_task, self.consumer_task)
                    if t is not None and not t.done()
                )
        if not self.stuck and (supervisor is None or supervisor.done()):
            # Covers cancellation arriving during the supervisor's existing cleanup.
            await self._stop_workers()
        self.stuck = {task for task in self.stuck if not task.done()}
        if self.stuck:
            self.fault = "shutdown_timeout"
            self.archive.diagnostic("shutdown_timeout", self.broadcaster.status, level="error")
            self.broadcaster.update_status(
                "error",
                "연결 종료 시간 초과 · 서버 재시작 필요",
                self.broadcaster.status.session_id,
            )
            return False
        self.stream_task = self.consumer_task = self.supervisor_task = None
        return True

    async def _supervise(self) -> None:
        delay = self.config.tiktok_reconnect_min_seconds
        while True:
            self.sink = EventSink(self.queue, self.broadcaster, self.archive)
            self.fault = None
            self.sink.status("connecting", "댓글 수신 준비 중")
            try:
                stream = self._make_stream(self.sink)
                self.consumer_task = asyncio.create_task(
                    self.broadcaster.consume(self.queue), name="event-consumer"
                )
                self.stream_task = asyncio.create_task(stream.run(), name="event-stream")
                for task in (self.consumer_task, self.stream_task):
                    task.add_done_callback(
                        partial(observe, archive=self.archive, status=self.broadcaster.status)
                    )
                await asyncio.wait(
                    {self.consumer_task, self.stream_task}, return_when=asyncio.FIRST_COMPLETED
                )
                # A stream must run until stopped, including when its upstream child is cancelled.
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Worker startup failed: %s at %s",
                    type(exc).__name__,
                    exception_location(exc),
                )
                self.archive.diagnostic(
                    "worker_startup_failed",
                    self.broadcaster.status,
                    level="error",
                    details={"error_type": type(exc).__name__, "location": exception_location(exc)},
                )
            finally:
                stopped = await self._stop_workers()
            self.fault = "worker_stopped" if stopped else "shutdown_timeout"
            self.broadcaster.update_status(
                "error",
                "댓글 수신 오류 · 자동 복구 대기"
                if stopped
                else "연결 종료 시간 초과 · 서버 재시작 필요",
                self.broadcaster.status.session_id,
            )
            if not stopped:
                return
            self.recoveries += 1
            logger.warning("Worker stopped; retrying in %.2fs", delay)
            self.archive.diagnostic(
                "worker_retry", self.broadcaster.status, level="warning", details={"delay": delay}
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, self.config.tiktok_reconnect_max_seconds)

    async def close(self) -> None:
        self.closed = True
        if self.diagnostics_task is not None:
            self.diagnostics_task.cancel()
            await asyncio.gather(self.diagnostics_task, return_exceptions=True)
        if self.commands:
            _, pending = await asyncio.wait(self.commands, timeout=STOP_TIMEOUT + 1)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        try:
            async with self.lock:
                await self._stop_session()
            await self.broadcaster.close()
        finally:
            try:
                await self.gift_images.close()
            finally:
                self.archive.diagnostic("process_stopped", self.broadcaster.status)
                await self.archive.close()
