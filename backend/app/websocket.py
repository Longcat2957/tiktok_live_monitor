import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from time import monotonic

from fastapi import WebSocket

from .models import FeedEvent, LiveInfo, Message, SourceState, Status

logger = logging.getLogger(__name__)


def enqueue_comment(queue: asyncio.Queue[FeedEvent], comment: FeedEvent) -> bool:
    dropped = queue.full()
    if dropped:
        queue.get_nowait()
        queue.task_done()
    queue.put_nowait(comment)
    return dropped


@dataclass
class Peer:
    queue: asyncio.Queue[Message]
    task: asyncio.Task[None]


class WebSocketManager:
    def __init__(
        self, status: Status, capacity: int = 100, send_timeout: float = 5, max_clients: int = 16
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

    async def connect(self, socket: WebSocket) -> None:
        if socket in self.clients:
            return
        if len(self.tasks) + self.accepting >= self.max_clients:
            await socket.close(code=1013)
            return
        self.accepting += 1
        try:
            await socket.accept()
            queue: asyncio.Queue[Message] = asyncio.Queue(self.capacity)
            queue.put_nowait(self.status)
            task = asyncio.create_task(self._send(socket, queue))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            self.clients[socket] = Peer(queue, task)
        finally:
            self.accepting -= 1
        # Enter the sender's try/finally before an immediate burst can cancel it.
        await asyncio.sleep(0)

    async def _send(self, socket: WebSocket, queue: asyncio.Queue[Message]) -> None:
        try:
            while True:
                message = await queue.get()
                try:
                    async with asyncio.timeout(self.send_timeout):
                        await socket.send_json(message.model_dump(mode="json"))
                finally:
                    queue.task_done()
        except TimeoutError:
            self.slow_disconnects += 1
            logger.warning("WebSocket send timed out")
        except (Exception, asyncio.CancelledError):
            logger.debug("WebSocket sender closed")
        finally:
            self.clients.pop(socket, None)
            with suppress(Exception):
                await asyncio.wait_for(socket.close(code=1013), timeout=1)

    async def disconnect(self, socket: WebSocket) -> None:
        peer = self.clients.pop(socket, None)
        if peer:
            peer.task.cancel()
            await asyncio.gather(peer.task, return_exceptions=True)

    def broadcast(self, message: Message) -> None:
        for socket, peer in list(self.clients.items()):
            if peer.queue.full():
                self.slow_disconnects += 1
                logger.warning("Disconnecting slow WebSocket client (queue full)")
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
                    comment = await queue.get()
            except TimeoutError:
                continue
            try:
                self.broadcast(comment)
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
