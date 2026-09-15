from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

SourceName = Literal["tiktok", "mock"]
LiveState = Literal["unknown", "live", "paused", "ended"]
SourceState = Literal["idle", "connecting", "connected", "waiting", "disconnected", "error"]


class Badge(BaseModel):
    kind: Literal["subscriber", "fan"]
    level: int | None = Field(default=None, ge=0, le=10000)


class LiveInfo(BaseModel):
    state: LiveState = "unknown"
    viewers: int | None = Field(default=None, ge=0, le=9_007_199_254_740_991)
    likes: int | None = Field(default=None, ge=0, le=9_007_199_254_740_991)


class User(BaseModel):
    nickname: str = Field(max_length=256)
    unique_id: str = Field(max_length=256)
    avatar_url: str | None = Field(default=None, max_length=2048)
    badges: list[Badge] = Field(default_factory=list, max_length=2)


class Comment(BaseModel):
    type: Literal["comment"] = "comment"
    id: str = Field(default_factory=lambda: str(uuid4()))
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    user: User
    comment: str = Field(min_length=1, max_length=10000)


class Activity(BaseModel):
    type: Literal["activity"] = "activity"
    id: str = Field(default_factory=lambda: str(uuid4()))
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    user: User
    kind: Literal["gift", "follow", "share", "subscribe"]
    gift_name: str = Field(default="선물", max_length=256)
    count: int = Field(default=1, ge=1, le=1_000_000_000)


FeedEvent = Comment | Activity


class Status(BaseModel):
    type: Literal["status"] = "status"
    live: LiveInfo = Field(default_factory=LiveInfo)
    source: SourceName
    state: SourceState
    message: str
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    username: str | None = None
    comment_history_size: int = Field(default=30, ge=1, le=1000)


Message = FeedEvent | Status
