import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .models import Comment, Status
from .sources.base import CommentSource
from .sources.mock import MockSource
from .websocket import WebSocketManager


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        config = settings or Settings()
        logging.basicConfig(
            level=config.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        queue: asyncio.Queue[Comment] = asyncio.Queue(config.comment_queue_size)
        manager = WebSocketManager(
            Status(source=config.comment_source, state="connecting", message="댓글 수신 준비 중")
        )
        source: CommentSource
        if config.comment_source == "mock":
            source = MockSource(queue, manager, config.mock_interval_seconds)
        else:
            from .sources.tiktok import TikTokSource

            source = TikTokSource(queue, manager, config)
        app.state.config = config
        app.state.queue = queue
        app.state.manager = manager
        tasks = [asyncio.create_task(source.run()), asyncio.create_task(manager.consume(queue))]
        app.state.tasks = tasks
        # Added only after API routes; a missing development build must not hide /health.
        mount = None
        if (config.static_dir / "index.html").is_file():
            app.mount("/", StaticFiles(directory=config.static_dir, html=True), name="ui")
            mount = app.router.routes[-1]
        else:
            logging.getLogger(__name__).warning(
                "Frontend build missing: run pnpm build in frontend/"
            )
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await manager.close()
            if mount:
                app.router.routes.remove(mount)

    app = FastAPI(title="TikTok LIVE Monitor", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, object]:
        manager = app.state.manager
        queue = app.state.queue
        return {
            "status": "ok" if all(not task.done() for task in app.state.tasks) else "error",
            "source": manager.status.model_dump(),
            "websocket_connections": len(manager.clients),
            "queue": {"size": queue.qsize(), "capacity": queue.maxsize},
        }

    @app.get("/config")
    async def client_config() -> dict[str, int]:
        return {"comment_history_size": app.state.config.comment_history_size}

    @app.websocket("/ws")
    async def websocket_endpoint(socket: WebSocket) -> None:
        manager: WebSocketManager = app.state.manager
        await manager.connect(socket)
        try:
            while True:
                await socket.receive_text()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            await manager.disconnect(socket)

    @app.exception_handler(404)
    async def missing_page(_request: object, _exception: Exception) -> HTMLResponse:
        return HTMLResponse(
            "페이지가 없습니다. UI가 없다면 frontend에서 pnpm build를 실행하세요.", status_code=404
        )

    return app


app = create_app()
