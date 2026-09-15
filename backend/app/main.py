import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import HTTPConnection
from starlette.responses import Response

from .config import Settings
from .models import SourceName, Status
from .session import ConflictError, Monitor, UnavailableError

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def same_origin(connection: HTTPConnection, *, required: bool = False) -> bool:
    if connection.url.hostname not in LOCAL_HOSTS:
        return False
    if connection.headers.get("sec-fetch-site") == "cross-site":
        return False
    origin = connection.headers.get("origin")
    if not origin:
        return not required
    scheme = {"ws": "http", "wss": "https"}.get(connection.url.scheme, connection.url.scheme)
    return origin == f"{scheme}://{connection.url.netloc}"


class SessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=64)


class SettingsInput(SessionInput):
    settings: dict[str, object]


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


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(
            level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        logging.getLogger("app").setLevel(config.log_level)
        app.state.monitor = Monitor(config)
        try:
            yield
        finally:
            await app.state.monitor.close()

    app = FastAPI(title="TikTok LIVE Monitor", lifespan=lifespan)

    @app.middleware("http")
    async def local_requests(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.hostname not in LOCAL_HOSTS:
            return JSONResponse({"detail": "로컬 주소로 접속해주세요."}, status_code=400)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not same_origin(request):
            return JSONResponse({"detail": "같은 화면에서 요청해주세요."}, status_code=403)
        return await call_next(request)

    @app.exception_handler(ConflictError)
    async def conflict(_request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(UnavailableError)
    async def unavailable(_request: Request, exc: UnavailableError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(ValidationError)
    async def invalid_settings(_request: Request, _exc: ValidationError) -> JSONResponse:
        return JSONResponse({"detail": "설정값의 허용 범위를 확인해주세요."}, status_code=422)

    @app.get("/health")
    async def health(request: Request) -> JSONResponse:
        monitor: Monitor = request.app.state.monitor
        return JSONResponse(
            {
                "status": "ok" if monitor.healthy else "error",
                "source": monitor.manager.status.model_dump(mode="json"),
                "websocket_connections": len(monitor.manager.clients),
                "pending_commands": len(monitor.commands),
                "queue": {"size": monitor.queue.qsize(), "capacity": monitor.queue.maxsize},
                "fault": monitor.fault,
                "recoveries": monitor.recoveries,
                "dropped_comments": monitor.manager.dropped_comments,
                "slow_disconnects": monitor.manager.slow_disconnects,
            },
            status_code=200 if monitor.healthy else 503,
        )

    @app.get("/config")
    async def client_config(request: Request) -> dict[str, object]:
        monitor: Monitor = request.app.state.monitor
        return monitor.runtime_settings.model_dump() | {
            "session_id": monitor.manager.status.session_id
        }

    @app.post("/account")
    async def start(account: AccountInput, request: Request) -> Status:
        monitor: Monitor = request.app.state.monitor
        return await monitor.change(
            "start", account.session_id, source=account.source, username=account.username or None
        )

    @app.post("/refresh")
    async def refresh(session: SessionInput, request: Request) -> Status:
        monitor: Monitor = request.app.state.monitor
        return await monitor.change("refresh", session.session_id)

    @app.patch("/config")
    async def update_config(update: SettingsInput, request: Request) -> Status:
        monitor: Monitor = request.app.state.monitor
        return await monitor.change("settings", update.session_id, settings=update.settings)

    @app.delete("/account")
    async def stop(session: SessionInput, request: Request) -> Status:
        monitor: Monitor = request.app.state.monitor
        return await monitor.change("stop", session.session_id)

    @app.websocket("/ws")
    async def websocket_endpoint(socket: WebSocket) -> None:
        if not same_origin(socket, required=True):
            await socket.close(code=1008)
            return
        monitor: Monitor = socket.app.state.monitor
        try:
            await monitor.manager.connect(socket)
            if socket not in monitor.manager.clients:
                return
            while True:
                message = await socket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                # This channel is server-to-browser only; reject application input.
                await socket.close(code=1008)
                break
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            await monitor.manager.disconnect(socket)

    @app.exception_handler(404)
    async def missing_page(_request: Request, _exception: Exception) -> HTMLResponse:
        return HTMLResponse(
            "페이지가 없습니다. UI가 없다면 frontend에서 pnpm build를 실행하세요.", status_code=404
        )

    if (config.static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=config.static_dir, html=True), name="ui")
    return app


app = create_app()
