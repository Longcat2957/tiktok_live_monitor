import asyncio
import logging
from typing import Protocol

from ..models import FeedEvent, LiveInfo, SourceState
from ..websocket import WebSocketManager, enqueue_comment


class SourceSink:
    """One attempt's event boundary; invalidated before cancellation/transition."""

    def __init__(self, queue: asyncio.Queue[FeedEvent], manager: WebSocketManager) -> None:
        self.queue = queue
        self.manager = manager
        self.session_id = manager.status.session_id
        self.active = True

    def publish(self, comment: FeedEvent) -> None:
        if self.active and self.session_id == self.manager.status.session_id:
            if enqueue_comment(self.queue, comment):
                self.manager.dropped_comments += 1
                total = self.manager.dropped_comments
                # Log at powers of two so overload cannot create an unbounded log stream.
                if total & (total - 1) == 0:
                    logging.getLogger(__name__).warning("Source queue dropped events: %d", total)

    def live(self, info: LiveInfo) -> None:
        if self.active and self.session_id == self.manager.status.session_id:
            self.manager.update_live(info)

    def status(self, state: SourceState, message: str) -> None:
        if self.active:
            self.manager.update_status(state, message, self.session_id)


class CommentSource(Protocol):
    async def run(self) -> None: ...
