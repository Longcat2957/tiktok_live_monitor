import asyncio
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from threading import Event

import pytest

from app.schemas.events import Comment, Status, User
from app.services.archive import BATCH_SIZE, CAPACITY, Archive, backup


def comment(number: int) -> Comment:
    return Comment(
        id=f"event-{number}",
        user=User(nickname="테스터", unique_id="tester"),
        comment=f"댓글 {number}",
    )


def status() -> Status:
    return Status(
        source="mock", state="connected", message="test", session_id="session", username="host"
    )


async def wait_saved(archive: Archive, count: int) -> None:
    async def wait() -> None:
        while archive.get_health().saved_comments < count:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait(), timeout=3)


async def test_create_order_flush_reopen_and_safe_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "new" / "monitor.sqlite3"
    archive = Archive(path)
    await archive.start()
    assert archive.get_health().ready
    for number in range(7):
        archive.comment(comment(number), status())
    archive.diagnostic("source_error", status(), level="error", details={"error_type": "EOFError"})
    await archive.close()  # Shutdown flushes without waiting for the one-second timer.
    assert archive.get_health().queued == 0
    assert archive.get_health().saved_comments == 7
    assert archive.get_health().saved_diagnostics == 1
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        rows = connection.execute(
            "SELECT id, event_id, session_id, source, username, user_id, nickname, comment, "
            "received_at FROM comments ORDER BY id"
        ).fetchall()
        assert [row[1] for row in rows] == [f"event-{number}" for number in range(7)]
        assert rows[0][2:8] == ("session", "mock", "host", "tester", "테스터", "댓글 0")
        assert rows[0][8].endswith("+00:00")
        diagnostic = connection.execute("SELECT event, level, details FROM diagnostics").fetchone()
        assert diagnostic[:2] == ("source_error", "error")
        assert json.loads(diagnostic[2]) == {"error_type": "EOFError"}

    reopened = Archive(path)
    await reopened.start()
    reopened.comment(comment(7), status())
    reopened.comment(comment(7), status())  # Event IDs cannot accidentally duplicate a row.
    await reopened.close()
    assert reopened.get_health().saved_comments == 1
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM comments").fetchone() == (8,)
        assert (
            connection.execute("SELECT id FROM comments WHERE event_id='event-7'").fetchone()[0] > 7
        )


async def test_timer_flush_and_live_wal_backup(tmp_path: Path) -> None:
    path = tmp_path / "monitor.sqlite3"
    archive = Archive(path)
    await archive.start()
    try:
        archive.comment(comment(0), status())
        await wait_saved(archive, 1)  # A partial batch becomes visible while the service runs.
        for number in range(1, BATCH_SIZE + 1):
            archive.comment(comment(number), status())
        await wait_saved(archive, BATCH_SIZE + 1)
        assert path.with_name(path.name + "-wal").exists()
        destination = tmp_path / "snapshot.sqlite3"
        await asyncio.to_thread(backup, path, destination)
        with closing(sqlite3.connect(destination)) as snapshot:
            assert snapshot.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert snapshot.execute("SELECT COUNT(*) FROM comments").fetchone() == (BATCH_SIZE + 1,)
            assert snapshot.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    finally:
        await archive.close()


async def test_bounded_queue_never_waits_for_slow_disk(tmp_path: Path, monkeypatch) -> None:
    archive = Archive(tmp_path / "monitor.sqlite3")
    await archive.start()
    started, release = Event(), Event()
    original_write = archive._write

    def slow_write(batch):
        started.set()
        assert release.wait(timeout=5)
        return original_write(batch)

    monkeypatch.setattr(archive, "_write", slow_write)
    try:
        for number in range(BATCH_SIZE):
            archive.comment(comment(number), status())
        assert await asyncio.to_thread(started.wait, 2)
        for number in range(BATCH_SIZE, BATCH_SIZE + CAPACITY + 3):
            archive.comment(comment(number), status())
        assert archive.get_health().queued == BATCH_SIZE + CAPACITY
        assert archive.get_health().dropped == 3
        await asyncio.wait_for(asyncio.sleep(0), timeout=0.1)
    finally:
        release.set()
        await archive.close()
    assert archive.get_health().saved_comments == BATCH_SIZE + CAPACITY
    assert archive.get_health().queued == 0


async def test_cancelled_start_closes_worker_connection(tmp_path: Path, monkeypatch) -> None:
    archive = Archive(tmp_path / "monitor.sqlite3")
    entered, release = Event(), Event()
    original_open = archive._open

    def delayed_open():
        entered.set()
        assert release.wait(timeout=5)
        original_open()

    monkeypatch.setattr(archive, "_open", delayed_open)
    task = asyncio.create_task(archive.start())
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert archive._connection is None and archive._executor is None
    assert not archive.get_health().ready


@pytest.mark.parametrize("kind", ["corrupt", "future", "unrecognized"])
async def test_initialization_failure_preserves_existing_file(tmp_path: Path, kind: str, caplog):
    path = tmp_path / "monitor.sqlite3"
    if kind == "corrupt":
        path.write_bytes(b"invalid SQLite data with PRIVATE_PAYLOAD")
    else:
        with closing(sqlite3.connect(path)) as connection:
            if kind == "future":
                connection.execute("PRAGMA user_version=2")
            else:
                connection.execute("CREATE TABLE unrelated(value TEXT)")
                connection.commit()
    original = path.read_bytes()
    archive = Archive(path)
    await archive.start()
    archive.comment(comment(0), status())
    await archive.close()
    health = archive.get_health()
    assert not health.ready and health.error is not None
    assert health.dropped == 1
    assert path.read_bytes() == original
    assert "PRIVATE_PAYLOAD" not in caplog.text


async def test_write_failure_rolls_back_batch_and_counts_unsaved_records(tmp_path: Path, caplog):
    path = tmp_path / "monitor.sqlite3"
    archive = Archive(path)
    await archive.start()
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "CREATE TRIGGER reject_diagnostic BEFORE INSERT ON diagnostics "
            "BEGIN SELECT RAISE(ABORT, 'PRIVATE_PAYLOAD'); END"
        )
        connection.commit()
    archive.comment(comment(0), status())
    archive.diagnostic("test")
    await archive.close()
    health = archive.get_health()
    assert health.error == "write:IntegrityError"
    assert health.dropped == 2 and health.queued == 0
    assert health.saved_comments == 0 and health.saved_diagnostics == 0
    assert "PRIVATE_PAYLOAD" not in caplog.text
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM comments").fetchone() == (0,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_backup_refuses_overwrite_missing_source_and_cleans_failed_output(tmp_path: Path) -> None:
    source = tmp_path / "monitor.sqlite3"
    output = tmp_path / "snapshot.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        backup(source, output)
    assert not source.exists() and not output.exists()
    source.write_bytes(b"corrupt")
    with pytest.raises(sqlite3.DatabaseError):
        backup(source, output)
    assert not output.exists()
    output.write_bytes(b"keep output")
    with pytest.raises(FileExistsError):
        backup(source, output)
    assert output.read_bytes() == b"keep output"
    with pytest.raises(ValueError):
        backup(source, source)
    assert source.read_bytes() == b"corrupt"
