"""Isolated browser-test server; fault controls are never included in the app image."""

import asyncio
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from threading import Event
from typing import Literal, cast

import uvicorn
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from starlette.routing import Mount

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main  # noqa: E402
from app.config import Settings  # noqa: E402
from app.schemas.events import Comment, LiveInfo, User  # noqa: E402
from app.services import monitor as monitor_module  # noqa: E402
from app.services.archive import Archive, Record  # noqa: E402
from app.services.event_sink import EventSink  # noqa: E402
from app.services.monitor import EventStream, MonitorService  # noqa: E402


class FaultArchive(Archive):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.gate = Event()
        self.gate.set()
        self.entered = Event()
        self.fail_write = Event()

    def _write(self, batch: list[Record]) -> tuple[int, int]:
        self.entered.set()
        if not self.gate.wait(timeout=15):
            raise TimeoutError("Browser test did not release its writer")
        if self.fail_write.is_set():
            raise sqlite3.OperationalError("PRIVATE simulated disk failure")
        return super()._write(batch)


class ControlledStream:
    def __init__(self, sink: EventSink) -> None:
        self.sink = sink

    async def run(self) -> None:
        self.sink.live(LiveInfo(state="live"))
        self.sink.status("connected", "Controlled test stream")
        await asyncio.Event().wait()


class FaultMonitor(MonitorService):
    def _make_stream(self, sink: EventSink) -> EventStream:
        return ControlledStream(sink)


# Patch only this helper process; production source and archive classes stay untouched.
monitor_module.Archive = FaultArchive
main.MonitorService = FaultMonitor
app = main.create_app(
    Settings(_env_file=None, archive_path=Path(os.environ["ARCHIVE_PATH"]), comment_queue_size=4000)
)


class Control(BaseModel):
    action: Literal["block", "release", "fail", "burst", "upstream", "snapshot"]
    count: int = Field(default=1, ge=1, le=3000)
    prefix: str = Field(default="test", pattern=r"^[a-z0-9-]{1,40}$")


def monitor(request: Request) -> FaultMonitor:
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, "Test controls are loopback-only")
    return cast(FaultMonitor, request.app.state.monitor)


@app.post("/__test/control")
async def control(request: Request, command: Control) -> dict[str, bool]:
    service = monitor(request)
    archive = cast(FaultArchive, service.archive)
    if command.action == "block":
        archive.entered.clear()
        archive.gate.clear()
    elif command.action == "release":
        archive.gate.set()
    elif command.action == "fail":
        archive.fail_write.set()
        archive.gate.set()
    elif command.action == "snapshot":
        service._record_snapshot()
    else:
        sink = service.sink
        if sink is None or not sink.active:
            raise HTTPException(409, "Start the controlled stream first")
        for index in range(command.count):
            if command.action == "upstream":
                sink.upstream_message()
            else:
                sink.publish(
                    Comment(
                        id=f"{command.prefix}-{index}",
                        user=User(nickname="테스트 시청자", unique_id="test-viewer"),
                        comment=f"{command.prefix} {index} 💚",
                    )
                )
    return {"ok": True}


def read_records(path: Path) -> dict[str, object]:
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)) as database:
        rows = database.execute(
            "SELECT event_id, session_id, username FROM comments ORDER BY id LIMIT 6000"
        ).fetchall()
        snapshots = database.execute(
            "SELECT session_id, details FROM diagnostics WHERE event='pipeline_snapshot' "
            "ORDER BY id LIMIT 100"
        ).fetchall()
    return {
        "rows": [dict(zip(("event_id", "session_id", "username"), row)) for row in rows],
        "snapshots": [{"session_id": row[0], "details": json.loads(row[1])} for row in snapshots],
    }


@app.get("/__test/state")
async def state(request: Request) -> dict[str, object]:
    service = monitor(request)
    archive = cast(FaultArchive, service.archive)
    records = await asyncio.to_thread(read_records, archive.path)
    return {
        **records,
        "health": service.get_health().model_dump(mode="json"),
        "writer_waiting": archive.entered.is_set() and not archive.gate.is_set(),
        "flow": service.sink.snapshot() if service.sink is not None else {},
    }


# Test controls precede the production static mount.
for route in list(app.router.routes):
    if isinstance(route, Mount) and route.name == "ui":
        app.router.routes.remove(route)
        app.router.routes.append(route)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=18769, ws="websockets-sansio", log_level="warning")
