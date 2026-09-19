from app.config import RuntimeSettings

from .monitor import SessionInput


class SettingsInput(SessionInput):
    settings: dict[str, object]


class SettingsResponse(RuntimeSettings):
    session_id: str
