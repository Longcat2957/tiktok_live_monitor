import re
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .events import SourceName


class SessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=64)


class AccountInput(SessionInput):
    source: SourceName = "tiktok"
    username: str = Field(default="", max_length=256)
    youtube_video_id: str = Field(default="", max_length=2048)

    @model_validator(mode="after")
    def normalize(self) -> AccountInput:
        if self.source == "mock":
            self.username = ""
            self.youtube_video_id = ""
            return self
        value = self.username.strip()
        if value.startswith("https://"):
            url = urlsplit(value)
            if url.netloc not in {"www.tiktok.com", "tiktok.com", "m.tiktok.com"}:
                raise ValueError("TikTok 프로필 또는 LIVE 주소를 입력하세요")
            match = re.fullmatch(r"/@([A-Za-z0-9_.]{1,24})(?:/live)?/?", url.path)
            value = match[1] if match else ""
        value = value.removeprefix("@")
        if not re.fullmatch(r"[A-Za-z0-9_.]{1,24}", value):
            raise ValueError("@아이디 또는 https://www.tiktok.com/@아이디/live를 입력하세요")
        self.username = value
        value = self.youtube_video_id.strip()
        if value.startswith("https://"):
            url = urlsplit(value)
            if url.netloc in {"www.youtube.com", "youtube.com", "m.youtube.com"}:
                if url.path == "/watch":
                    identifiers = parse_qs(url.query).get("v", [])
                    value = identifiers[0] if len(identifiers) == 1 else "invalid"
                else:
                    match = re.fullmatch(r"/live/([A-Za-z0-9_-]{11})/?", url.path)
                    value = match[1] if match else "invalid"
            elif url.netloc == "youtu.be":
                value = url.path.removeprefix("/").removesuffix("/") or "invalid"
            else:
                value = "invalid"
        if value and not re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
            raise ValueError("YouTube 방송 주소 또는 11자리 영상 ID를 입력하세요")
        self.youtube_video_id = value
        return self
