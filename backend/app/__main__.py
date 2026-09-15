import uvicorn

from .config import Settings

if __name__ == "__main__":
    settings = Settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
        timeout_graceful_shutdown=15,
        ws_max_size=1024,
        forwarded_allow_ips="",
        ws="websockets-sansio",
    )
