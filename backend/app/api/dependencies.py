from typing import Annotated, cast

from fastapi import Depends
from starlette.requests import HTTPConnection

from app.services.monitor import MonitorService


def get_monitor(connection: HTTPConnection) -> MonitorService:
    return cast(MonitorService, connection.app.state.monitor)


MonitorDep = Annotated[MonitorService, Depends(get_monitor)]
