from fastapi import APIRouter, Response

from app.api.dependencies import MonitorDep
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", responses={503: {"model": HealthResponse}})
async def health(monitor: MonitorDep, response: Response) -> HealthResponse:
    health = monitor.get_health()
    response.status_code = 200 if health.status == "ok" else 503
    return health
