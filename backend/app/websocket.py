import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass

from fastapi import WebSocket

from .models import Comment, Message, Status

logger = logging.getLogger(__name__)


def enqueue_comment(queue: asyncio.Queue[Comment], comment: Comment) -> None:
    if queue.full():
        queue.get_nowait()
        queue.task_done()
        logger.warning("Comment queue full: dropped oldest comment")
    queue.put_nowait(comment)


@dataclass
class Peer:
    queue: asyncio.Queue[Message]
    task: asyncio.Task[None]


class WebSocketManager:
    def __init__(self, status: Status, capacity: int = 100, send_timeout: float = 5) -> None:
        self.status = status
        self.capacity = capacity
        self.send_timeout = send_timeout
        self.clients: dict[WebSocket, Peer] = {}
        self.tasks: set[asyncio.Task[None]] = set()

    async def connect(self, socket: WebSocket) -> None:
        if socket in self.clients:
            return
        await socket.accept()
        queue: asyncio.Queue[Message] = asyncio.Queue(self.capacity)
        queue.put_nowait(self.status)
        task = asyncio.create_task(self._send(socket, queue))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        self.clients[socket] = Peer(queue, task)
        # Enter the sender's try/finally before an immediate burst can cancel it.
        await asyncio.sleep(0)

    async def _send(self, socket: WebSocket, queue: asyncio.Queue[Message]) -> None:
        try:
            while True:
                message = await queue.get()
                try:
                    await asyncio.wait_for(
                        socket.send_json(message.model_dump(mode="json")), self.send_timeout
                    )
                finally:
                    queue.task_done()
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
                logger.warning("Disconnecting slow WebSocket client (queue full)")
                self.clients.pop(socket, None)
                peer.task.cancel()
            else:
                peer.queue.put_nowait(message)

    def set_status(self, status: Status) -> None:
        self.status = status
        logger.info("Source %s: %s", status.state, status.message)
        self.broadcast(status)

    async def consume(self, queue: asyncio.Queue[Comment]) -> None:
        while True:
            comment = await queue.get()
            try:
                self.broadcast(comment)
            finally:
                queue.task_done()

    async def close(self) -> None:
        await asyncio.gather(*(self.disconnect(socket) for socket in list(self.clients)))
        # Include senders removed by queue overflow but still closing their sockets.
        remaining = list(self.tasks)
        for task in remaining:
            task.cancel()
        await asyncio.gather(*remaining, return_exceptions=True)
