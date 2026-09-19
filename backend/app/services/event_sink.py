import asyncio
import logging

from ..realtime.broadcaster import WebSocketBroadcaster, enqueue_event
from ..schemas.events import FeedEvent, LiveInfo, SourceState


class EventSink:
    """One attempt's event boundary; invalidated before cancellation/transition."""

    def __init__(self, queue: asyncio.Queue[FeedEvent], broadcaster: WebSocketBroadcaster) -> None:
        self.queue = queue
        self.broadcaster = broadcaster
        self.session_id = broadcaster.status.session_id
        self.active = True

    def publish(self, event: FeedEvent) -> None:
        if self.active and self.session_id == self.broadcaster.status.session_id:
            if enqueue_event(self.queue, event):
                self.broadcaster.dropped_comments += 1
                total = self.broadcaster.dropped_comments
                # Log at powers of two so overload cannot create an unbounded log stream.
                if total & (total - 1) == 0:
                    logging.getLogger(__name__).warning("Source queue dropped events: %d", total)

    def live(self, info: LiveInfo) -> None:
        if self.active and self.session_id == self.broadcaster.status.session_id:
            self.broadcaster.update_live(info)

    def status(self, state: SourceState, message: str) -> None:
        if self.active:
            self.broadcaster.update_status(state, message, self.session_id)
