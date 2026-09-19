from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.dependencies import MonitorDep
from app.api.security import same_origin

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(socket: WebSocket, monitor: MonitorDep) -> None:
    if not same_origin(socket, required=True):
        await socket.close(code=1008)
        return
    broadcaster = monitor.broadcaster
    try:
        if not await broadcaster.connect(socket):
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
        await broadcaster.disconnect(socket)
