import asyncio
import logging
from datetime import UTC, datetime

from ..diagnostics import exception_location
from ..realtime.broadcaster import WebSocketBroadcaster, enqueue_event
from ..schemas.events import Comment, FeedEvent, LiveInfo, SourceState
from .archive import Archive


class EventSink:
    """One attempt's event boundary; invalidated before cancellation/transition."""

    def __init__(
        self,
        queue: asyncio.Queue[FeedEvent],
        broadcaster: WebSocketBroadcaster,
        archive: Archive | None = None,
    ) -> None:
        self.queue = queue
        self.broadcaster = broadcaster
        self.archive = archive
        self.context = broadcaster.status
        self.session_id = broadcaster.status.session_id
        self.active = True
        self.upstream_messages = 0
        self.last_upstream_message_at: str | None = None
        self.received_comments = 0
        self.last_comment_received_at: str | None = None
        self.last_comment_received_id: str | None = None
        self.invalid_comments = 0
        self.invalid_activities = 0

    def diagnostic(
        self,
        event: str,
        *,
        level: str = "info",
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        if self.archive is not None:
            self.archive.diagnostic(event, self.context, level=level, details=details)

    def upstream_message(self) -> None:
        if self.active and self.session_id == self.broadcaster.status.session_id:
            self.upstream_messages += 1
            self.last_upstream_message_at = datetime.now(UTC).isoformat()

    def invalid_event(self, kind: str, error: Exception) -> None:
        if not self.active or self.session_id != self.broadcaster.status.session_id:
            return
        if kind == "comment":
            self.invalid_comments += 1
            total = self.invalid_comments
        else:
            self.invalid_activities += 1
            total = self.invalid_activities
        if total & (total - 1) == 0:
            self.diagnostic(
                "invalid_" + kind,
                level="warning",
                details={
                    "count": total,
                    "error_type": type(error).__name__,
                    "location": exception_location(error),
                },
            )

    def snapshot(self) -> dict[str, str | int | float | bool | None]:
        return {
            "upstream_messages": self.upstream_messages,
            "last_upstream_message_at": self.last_upstream_message_at,
            "received_comments": self.received_comments,
            "last_comment_received_at": self.last_comment_received_at,
            "last_comment_received_id": self.last_comment_received_id,
            "invalid_comments": self.invalid_comments,
            "invalid_activities": self.invalid_activities,
        }

    def publish(self, event: FeedEvent) -> None:
        if self.active and self.session_id == self.broadcaster.status.session_id:
            if isinstance(event, Comment):
                self.received_comments += 1
                self.last_comment_received_at = event.received_at.isoformat()
                self.last_comment_received_id = event.id
                if self.archive is not None:
                    self.archive.comment(event, self.context)
            if enqueue_event(self.queue, event):
                self.broadcaster.dropped_comments += 1
                total = self.broadcaster.dropped_comments
                # Log at powers of two so overload cannot create an unbounded log stream.
                if total & (total - 1) == 0:
                    logging.getLogger(__name__).warning("Source queue dropped events: %d", total)
                    self.diagnostic("source_queue_full", level="warning", details={"count": total})

    def live(self, info: LiveInfo) -> None:
        if self.active and self.session_id == self.broadcaster.status.session_id:
            self.broadcaster.update_live(info)

    def status(self, state: SourceState, message: str) -> None:
        if self.active and self.session_id == self.broadcaster.status.session_id:
            changed = self.broadcaster.status.state != state
            self.broadcaster.update_status(state, message, self.session_id)
            if changed:
                self.diagnostic("source_state", details={"state": state})
