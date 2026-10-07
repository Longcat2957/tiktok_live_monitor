from typing import Literal

from pydantic import BaseModel

from .events import Status


class QueueInfo(BaseModel):
    size: int
    capacity: int


class StorageInfo(BaseModel):
    ready: bool
    error: str | None
    queued: int
    saved_comments: int
    saved_diagnostics: int
    dropped: int


class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    source: Status
    websocket_connections: int
    pending_commands: int
    queue: QueueInfo
    fault: str | None
    recoveries: int
    dropped_comments: int
    slow_disconnects: int
    storage: StorageInfo
