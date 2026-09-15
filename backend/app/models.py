from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

SourceName = Literal["tiktok", "mock"]
SourceState = Literal["connecting", "connected", "waiting", "disconnected", "error"]


class User(BaseModel):
    nickname: str
    unique_id: str


class Comment(BaseModel):
    type: Literal["comment"] = "comment"
    id: str = Field(default_factory=lambda: str(uuid4()))
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    user: User
    comment: str = Field(min_length=1)


class Status(BaseModel):
    type: Literal["status"] = "status"
    source: SourceName
    state: SourceState
    message: str


Message = Comment | Status
