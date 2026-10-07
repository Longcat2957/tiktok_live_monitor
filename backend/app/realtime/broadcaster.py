import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import WebSocket

from ..diagnostics import exception_location
from ..schemas.events import Activity, Comment, FeedEvent, LiveInfo, Message, SourceState, Status
from ..services.gift_images import GiftImageCache

if TYPE_CHECKING:
    from ..services.archive import Archive

logger = logging.getLogger(__name__)


def enqueue_event(queue: asyncio.Queue[FeedEvent], event: FeedEvent) -> bool:
    dropped = queue.full()
    if dropped:
        queue.get_nowait()
        queue.task_done()
    queue.put_nowait(event)
    return dropped


@dataclass
class Peer:
    queue: asyncio.Queue[Message]
    task: asyncio.Task[None]
    id: str


class WebSocketBroadcaster:
    def __init__(
        self,
        status: Status,
        capacity: int = 100,
        send_timeout: float = 5,
        max_clients: int = 16,
        gift_images: GiftImageCache | None = None,
        archive: "Archive | None" = None,
    ) -> None:
        self.status = status
        self.live_dirty = False
        self.max_clients = max_clients
        self.accepting = 0
        self.dropped_comments = 0
        self.slow_disconnects = 0
        self.capacity = capacity
        self.send_timeout = send_timeout
        self.clients: dict[WebSocket, Peer] = {}
        self.tasks: set[asyncio.Task[None]] = set()
        self.gift_images = gift_images
        self.archive = archive
        # Count successful transport writes across peers, not browser-render acknowledgements.
        self.sent_comments = 0
        self.last_comment_sent_at: str | None = None
        self.last_comment_sent_id: str | None = None

    def _diagnostic(
        self,
        event: str,
        status: Status | None = None,
        *,
        level: str = "info",
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        if self.archive is not None:
            self.archive.diagnostic(event, status or self.status, level=level, details=details)

    async def connect(self, socket: WebSocket) -> bool:
        if socket in self.clients:
            return True
        if len(self.tasks) + self.accepting >= self.max_clients:
            self._diagnostic(
                "websocket_peer_limit", level="warning", details={"max_clients": self.max_clients}
            )
            await socket.close(code=1013)
            return False
        self.accepting += 1
        try:
            await socket.accept()
            queue: asyncio.Queue[Message] = asyncio.Queue(self.capacity)
            queue.put_nowait(self.status)
            peer_id = str(uuid4())
            task = asyncio.create_task(self._send(socket, queue, peer_id))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            self.clients[socket] = Peer(queue, task, peer_id)
            self._diagnostic("websocket_connected", details={"peer_id": peer_id})
        finally:
            self.accepting -= 1
        # Enter the sender's try/finally before an immediate burst can cancel it.
        await asyncio.sleep(0)
        return socket in self.clients

    async def _send(self, socket: WebSocket, queue: asyncio.Queue[Message], peer_id: str) -> None:
        context = self.status
        close_reason = "cancelled"
        try:
            while True:
                message = await queue.get()
                # Preserve the session of an in-flight send across a later session boundary.
                context = message if isinstance(message, Status) else self.status
                try:
                    async with asyncio.timeout(self.send_timeout):
                        await socket.send_json(message.model_dump(mode="json"))
                    if isinstance(message, Comment):
                        self.sent_comments += 1
                        self.last_comment_sent_at = datetime.now(UTC).isoformat()
                        self.last_comment_sent_id = message.id
                finally:
                    queue.task_done()
        except TimeoutError:
            close_reason = "send_timeout"
            self.slow_disconnects += 1
            logger.warning("WebSocket send timed out")
            self._diagnostic(
                "websocket_send_timeout",
                context,
                level="warning",
                details={"peer_id": peer_id, "timeout_seconds": self.send_timeout},
            )
        except asyncio.CancelledError:
            logger.debug("WebSocket sender closed")
        except Exception as exc:
            close_reason = "send_failed"
            logger.debug("WebSocket sender closed: %s", type(exc).__name__)
            self._diagnostic(
                "websocket_send_failed",
                context,
                level="warning",
                details={
                    "peer_id": peer_id,
                    "error_type": type(exc).__name__,
                    "location": exception_location(exc),
                },
            )
        finally:
            self.clients.pop(socket, None)
            self._diagnostic(
                "websocket_disconnected", details={"peer_id": peer_id, "reason": close_reason}
            )
            with suppress(Exception):
                await asyncio.wait_for(socket.close(code=1013), timeout=1)

    async def disconnect(self, socket: WebSocket) -> None:
        peer = self.clients.pop(socket, None)
        if peer:
            peer.task.cancel()
            await asyncio.gather(peer.task, return_exceptions=True)

    def broadcast(self, message: Message) -> None:
        if (
            self.gift_images is not None
            and isinstance(message, Activity)
            and message.kind == "gift"
            and message.gift_image_url
        ):
            message = message.model_copy(
                update={
                    "gift_image_url": (
                        message.gift_image_url
                        if self.status.source == "mock"
                        and message.gift_image_url == "/demo-gift-rose.webp"
                        else self.gift_images.register(message.gift_image_url)
                    )
                }
            )
        for socket, peer in list(self.clients.items()):
            if peer.queue.full():
                self.slow_disconnects += 1
                logger.warning("Disconnecting slow WebSocket client (queue full)")
                self._diagnostic(
                    "websocket_queue_full",
                    level="warning",
                    details={"peer_id": peer.id, "capacity": self.capacity},
                )
                self.clients.pop(socket, None)
                peer.task.cancel()
            else:
                peer.queue.put_nowait(message)

    def begin_session(self, status: Status) -> None:
        self.status = status
        self.live_dirty = False
        # Discard queued old events. An in-flight send still precedes this boundary.
        for peer in self.clients.values():
            while not peer.queue.empty():
                peer.queue.get_nowait()
                peer.queue.task_done()
        self.broadcast(status)

    def update_status(self, state: SourceState, message: str, session_id: str) -> None:
        if session_id != self.status.session_id:
            return
        self.status = self.status.model_copy(update={"state": state, "message": message})
        logger.info("Source state: %s", state)
        self.broadcast(self.status)

    def update_live(self, info: LiveInfo) -> None:
        if info != self.status.live:
            state_changed = info.state != self.status.live.state
            self.status = self.status.model_copy(update={"live": info})
            self.live_dirty = not state_changed
            if state_changed:
                self.broadcast(self.status)

    async def consume(self, queue: asyncio.Queue[FeedEvent]) -> None:
        last_live = monotonic()
        while True:
            if self.live_dirty and monotonic() - last_live >= 1:
                self.broadcast(self.status)
                self.live_dirty = False
                last_live = monotonic()
            try:
                async with asyncio.timeout(1):
                    event = await queue.get()
            except TimeoutError:
                continue
            try:
                self.broadcast(event)
            finally:
                queue.task_done()
            # A nonempty Queue.get() does not yield to the per-browser senders.
            await asyncio.sleep(0)

    async def close(self) -> None:
        await asyncio.gather(*(self.disconnect(socket) for socket in list(self.clients)))
        # Include senders removed by queue overflow but still closing their sockets.
        remaining = list(self.tasks)
        for task in remaining:
            task.cancel()
        await asyncio.gather(*remaining, return_exceptions=True)
