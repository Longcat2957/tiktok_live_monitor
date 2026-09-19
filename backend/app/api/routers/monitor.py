from fastapi import APIRouter

from app.api.dependencies import MonitorDep
from app.schemas.events import Status
from app.schemas.monitor import AccountInput, SessionInput

router = APIRouter()


@router.post("/account")
async def start(account: AccountInput, monitor: MonitorDep) -> Status:
    return await monitor.start(
        account.session_id, source=account.source, username=account.username or None
    )


@router.post("/refresh")
async def refresh(session: SessionInput, monitor: MonitorDep) -> Status:
    return await monitor.refresh(session.session_id)


@router.delete("/account")
async def stop(session: SessionInput, monitor: MonitorDep) -> Status:
    return await monitor.stop(session.session_id)
