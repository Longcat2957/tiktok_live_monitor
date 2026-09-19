from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import HTTPConnection
from starlette.responses import Response

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


async def local_requests(request: Request, call_next: RequestResponseEndpoint) -> Response:
    if request.url.hostname not in LOCAL_HOSTS:
        return JSONResponse({"detail": "로컬 주소로 접속해주세요."}, status_code=400)
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not same_origin(request):
        return JSONResponse({"detail": "같은 화면에서 요청해주세요."}, status_code=403)
    return await call_next(request)
