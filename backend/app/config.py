from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment_queue_size: int = Field(default=500, ge=1, le=10_000)
    comment_history_size: int = Field(default=30, ge=1, le=1000)
    tiktok_reconnect_min_seconds: float = Field(default=2, gt=0, le=300)
    tiktok_reconnect_max_seconds: float = Field(default=30, gt=0, le=3600)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    mock_interval_seconds: float = Field(default=1.5, gt=0, le=3600)

    @model_validator(mode="after")
    def validate_source(self) -> "RuntimeSettings":
        if self.tiktok_reconnect_max_seconds < self.tiktok_reconnect_min_seconds:
            raise ValueError("재연결 최대 간격은 최소 간격 이상이어야 합니다")
        return self


class Settings(RuntimeSettings, BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    comment_source: Literal["tiktok", "mock"] = "tiktok"
    host: str = Field(default="0.0.0.0", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    static_dir: Path = ROOT / "frontend" / "build"
