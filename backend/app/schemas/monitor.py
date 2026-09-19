import re
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .events import SourceName


class SessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=64)


class AccountInput(SessionInput):
    source: SourceName = "tiktok"
    username: str = Field(default="", max_length=256)

    @model_validator(mode="after")
    def normalize(self) -> "AccountInput":
        if self.source == "mock":
            self.username = ""
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
        return self
