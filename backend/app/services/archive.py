"""Bounded, nonblocking SQLite storage and consistent external backups."""

import argparse
import asyncio
import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.events import Comment, Status
from app.schemas.health import StorageInfo

logger = logging.getLogger(__name__)
Record = tuple[str, tuple[str | None, ...]]
Detail = str | int | float | bool | None
CAPACITY = 2000
BATCH_SIZE = 100
FLUSH_SECONDS = 1.0

SCHEMA = """
BEGIN;
CREATE TABLE comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    received_at TEXT NOT NULL,
    session_id TEXT NOT NULL,
    source TEXT NOT NULL,
    username TEXT,
    user_id TEXT NOT NULL,
    nickname TEXT NOT NULL,
    comment TEXT NOT NULL
);
CREATE INDEX comments_received_at ON comments(received_at);
CREATE TABLE diagnostics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    level TEXT NOT NULL,
    event TEXT NOT NULL,
    session_id TEXT,
    source TEXT,
    username TEXT,
    details TEXT NOT NULL
);
CREATE INDEX diagnostics_occurred_at ON diagnostics(occurred_at);
PRAGMA user_version = 1;
COMMIT;
"""


class Archive:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._queue: asyncio.Queue[Record | None] = asyncio.Queue(CAPACITY)
        self._executor: ThreadPoolExecutor | None = None
        self._connection: sqlite3.Connection | None = None
        self._task: asyncio.Task[None] | None = None
        self._started = False
        self._closing = False
        self._ready = False
        self._error: str | None = None
        self._pending = 0
        self._saved_comments = 0
        self._saved_diagnostics = 0
        self._dropped = 0

    async def start(self) -> None:
        if self._started or self._closing:
            return
        self._started = True
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlite-archive")
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(self._executor, self._open)
        except asyncio.CancelledError:
            await self.close()
            raise
        except Exception as exc:
            self._fail("initialize", exc)
            await loop.run_in_executor(self._executor, self._close_connection)
            self._executor.shutdown(wait=False)
            self._executor = None
            return
        self._ready = True
        self._task = asyncio.create_task(self._write_loop(), name="sqlite-archive")

    def comment(self, event: Comment, status: Status) -> None:
        received_at = event.received_at
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=UTC)
        self._enqueue(
            (
                "comments",
                (
                    event.id,
                    received_at.astimezone(UTC).isoformat(timespec="milliseconds"),
                    status.session_id,
                    status.source,
                    status.username,
                    event.user.unique_id,
                    event.user.nickname,
                    event.comment,
                ),
            )
        )

    def diagnostic(
        self,
        event: str,
        status: Status | None = None,
        *,
        level: str = "info",
        details: dict[str, Detail] | None = None,
    ) -> None:
        self._enqueue(
            (
                "diagnostics",
                (
                    datetime.now(UTC).isoformat(timespec="milliseconds"),
                    level,
                    event,
                    status.session_id if status else None,
                    status.source if status else None,
                    status.username if status else None,
                    json.dumps(details or {}, ensure_ascii=False, separators=(",", ":")),
                ),
            )
        )

    def get_health(self) -> StorageInfo:
        return StorageInfo(
            ready=self._ready,
            error=self._error,
            queued=self._pending,
            saved_comments=self._saved_comments,
            saved_diagnostics=self._saved_diagnostics,
            dropped=self._dropped,
        )

    def _enqueue(self, record: Record) -> None:
        if self._closing or self._error is not None:
            self._drop(1)
            return
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            self._drop(1)
        else:
            self._pending += 1

    def _drop(self, count: int) -> None:
        self._dropped += count
        if count and self._dropped & (self._dropped - 1) == 0:
            logger.warning("SQLite archive dropped %d records", self._dropped)

    def _discard_queue(self) -> None:
        while not self._queue.empty():
            record = self._queue.get_nowait()
            self._queue.task_done()
            if record is not None:
                self._pending -= 1
                self._drop(1)

    def _fail(self, operation: str, exc: Exception) -> None:
        self._ready = False
        self._error = f"{operation}:{type(exc).__name__}"
        logger.error("SQLite archive %s failed (%s)", operation, type(exc).__name__)
        self._discard_queue()

    def _open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        self._connection = connection
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise ValueError("Unsupported archive schema version")
        if version == 0:
            if connection.execute("SELECT name FROM sqlite_master").fetchone() is not None:
                raise ValueError("Unrecognized archive database")
        else:
            connection.execute(
                "SELECT event_id, received_at, session_id, source, username, user_id, "
                "nickname, comment FROM comments LIMIT 0"
            )
            connection.execute(
                "SELECT occurred_at, level, event, session_id, source, username, details "
                "FROM diagnostics LIMIT 0"
            )
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        if version == 0:
            connection.executescript(SCHEMA)

    def _write(self, batch: list[Record]) -> tuple[int, int]:
        assert self._connection is not None
        with self._connection:
            comments = self._connection.executemany(
                "INSERT INTO comments(event_id, received_at, session_id, source, username, "
                "user_id, nickname, comment) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(event_id) DO NOTHING",
                [values for table, values in batch if table == "comments"],
            ).rowcount
            diagnostics = self._connection.executemany(
                "INSERT INTO diagnostics(occurred_at, level, event, session_id, source, "
                "username, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [values for table, values in batch if table == "diagnostics"],
            ).rowcount
        return comments, diagnostics

    async def _write_loop(self) -> None:
        assert self._executor is not None
        loop = asyncio.get_running_loop()
        while not (self._closing and self._queue.empty()):
            record = await self._queue.get()
            if record is None:
                self._queue.task_done()
                return
            batch = [record]
            deadline = loop.time() + FLUSH_SECONDS
            stopping = False
            while len(batch) < BATCH_SIZE:
                try:
                    record = await asyncio.wait_for(
                        self._queue.get(), timeout=max(0, deadline - loop.time())
                    )
                except TimeoutError:
                    break
                if record is None:
                    self._queue.task_done()
                    stopping = True
                    break
                batch.append(record)
            try:
                comments, diagnostics = await loop.run_in_executor(
                    self._executor, self._write, batch
                )
            except Exception as exc:
                self._drop(len(batch))
                self._pending -= len(batch)
                for _ in batch:
                    self._queue.task_done()
                self._fail("write", exc)
                return
            self._saved_comments += comments
            self._saved_diagnostics += diagnostics
            self._pending -= len(batch)
            for _ in batch:
                self._queue.task_done()
            if stopping:
                return

    def _close_connection(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._task is not None and not self._task.done() and not self._queue.full():
            self._queue.put_nowait(None)
        try:
            if self._task is not None:
                try:
                    await asyncio.shield(self._task)
                except asyncio.CancelledError:
                    await self._task
                    raise
        finally:
            self._discard_queue()
            if self._executor is not None:
                try:
                    await asyncio.get_running_loop().run_in_executor(
                        self._executor, self._close_connection
                    )
                except Exception as exc:
                    self._fail("close", exc)
                finally:
                    self._executor.shutdown(wait=False)
                    self._executor = None
            self._ready = False


def backup(source: Path, destination: Path) -> None:
    """Copy a live database through SQLite, including committed WAL contents."""
    if source.resolve() == destination.resolve():
        raise ValueError("Backup destination must differ from source")
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as reader:
        with destination.open("xb"):
            pass
        try:
            with closing(sqlite3.connect(destination)) as snapshot:
                reader.backup(snapshot)
                snapshot.execute("PRAGMA journal_mode=DELETE")
        except BaseException:
            destination.unlink(missing_ok=True)
            raise


def main() -> None:
    from app.config import Settings

    parser = argparse.ArgumentParser(description="Create a consistent SQLite archive snapshot")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        backup(Settings().archive_path, args.destination)
    except (OSError, sqlite3.Error, ValueError) as exc:
        parser.exit(1, f"SQLite backup failed ({type(exc).__name__})\n")
    print(args.destination)


if __name__ == "__main__":
    main()
