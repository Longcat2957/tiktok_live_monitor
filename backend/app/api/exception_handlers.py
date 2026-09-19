from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse


async def conflict(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=409)


async def unavailable(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=503)


async def invalid_settings(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": "설정값의 허용 범위를 확인해주세요."}, status_code=422)


async def missing_page(_request: Request, _exc: Exception) -> HTMLResponse:
    return HTMLResponse(
        "페이지가 없습니다. UI가 없다면 frontend에서 pnpm build를 실행하세요.", status_code=404
    )
