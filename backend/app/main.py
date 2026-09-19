import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import exception_handlers
from .api.routers import health, monitor, websocket
from .api.routers import settings as settings_router
from .api.security import local_requests
from .config import Settings
from .services.errors import ConflictError, InvalidSettingsError, UnavailableError
from .services.monitor import MonitorService


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(
            level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        logging.getLogger("app").setLevel(config.log_level)
        service = MonitorService(config)
        app.state.monitor = service
        try:
            yield
        finally:
            await service.close()

    app = FastAPI(title="TikTok LIVE Monitor", lifespan=lifespan)
    app.middleware("http")(local_requests)
    app.add_exception_handler(ConflictError, exception_handlers.conflict)
    app.add_exception_handler(UnavailableError, exception_handlers.unavailable)
    app.add_exception_handler(InvalidSettingsError, exception_handlers.invalid_settings)
    app.add_exception_handler(404, exception_handlers.missing_page)

    app.include_router(health.router)
    app.include_router(settings_router.router)
    app.include_router(monitor.router)
    app.include_router(websocket.router)

    if (config.static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=config.static_dir, html=True), name="ui")
    return app


app = create_app()
