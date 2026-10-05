from math import floor
from time import monotonic

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.api.dependencies import MonitorDep

router = APIRouter()


@router.get("/gift-images/{key}")
async def gift_image(key: str, request: Request, monitor: MonitorDep) -> Response:
    image = await monitor.get_gift_image(key)
    if image is None:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    headers = {
        "Cache-Control": f"public, max-age={max(0, floor(image.expires_at - monotonic()))}",
        "ETag": image.etag,
        "X-Content-Type-Options": "nosniff",
    }
    if request.headers.get("if-none-match") == image.etag:
        return Response(status_code=304, headers=headers)
    return Response(content=image.content, media_type=image.media_type, headers=headers)
