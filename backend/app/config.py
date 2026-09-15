from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    tiktok_username: str = ""
    comment_source: Literal["tiktok", "mock"] = "tiktok"
    comment_queue_size: int = Field(default=500, ge=1, le=100_000)
    comment_history_size: int = Field(default=30, ge=1, le=1000)
    tiktok_reconnect_min_seconds: float = Field(default=2, gt=0, le=300)
    tiktok_reconnect_max_seconds: float = Field(default=30, gt=0, le=3600)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    host: str = Field(default="0.0.0.0", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    mock_interval_seconds: float = Field(default=1.5, gt=0, le=3600)
    static_dir: Path = ROOT / "frontend" / "build"

    @field_validator("tiktok_username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        import re

        value = value.strip().removeprefix("@")
        if value and not re.fullmatch(r"[A-Za-z0-9_.]{1,24}", value):
            raise ValueError("TIKTOK_USERNAME에는 URL이 아닌 TikTok 계정 아이디를 입력하세요")
        return value

    @model_validator(mode="after")
    def validate_source(self) -> "Settings":
        if self.comment_source == "tiktok" and not self.tiktok_username:
            raise ValueError("COMMENT_SOURCE=tiktok에는 TIKTOK_USERNAME이 필요합니다")
        if self.tiktok_reconnect_max_seconds < self.tiktok_reconnect_min_seconds:
            raise ValueError("재연결 최대 간격은 최소 간격 이상이어야 합니다")
        return self
