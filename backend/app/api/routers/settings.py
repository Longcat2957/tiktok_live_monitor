from fastapi import APIRouter

from app.api.dependencies import MonitorDep
from app.schemas.events import Status
from app.schemas.settings import SettingsInput, SettingsResponse

router = APIRouter()


@router.get("/config")
async def client_config(monitor: MonitorDep) -> SettingsResponse:
    return monitor.get_settings()


@router.patch("/config")
async def update_config(update: SettingsInput, monitor: MonitorDep) -> Status:
    return await monitor.update_settings(update.session_id, update.settings)
