import asyncio
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from threading import Event

import pytest

from app.schemas.events import Comment, Status, User
from app.services.archive import BATCH_SIZE, CAPACITY, Archive, backup


def comment(number: int, body: str | None = None) -> Comment:
    return Comment(
        id=f"event-{number}",
        user=User(nickname="테스터", unique_id="tester"),
        comment=body if body is not None else f"댓글 {number}",
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


async def worker_sql(archive: Archive, *statements: str):
    def execute():
        assert archive._connection is not None
        return [archive._connection.execute(statement).fetchone() for statement in statements]

    return await asyncio.get_running_loop().run_in_executor(archive._executor, execute)


def rows(path: Path):
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        return connection.execute("SELECT event_id, comment FROM comments ORDER BY id").fetchall()


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


@pytest.mark.parametrize("expired_deadline", [False, True])
async def test_ready_queue_batches_without_waiting_and_respects_deadline(
    tmp_path: Path, monkeypatch, expired_deadline: bool
) -> None:
    path = tmp_path / "monitor.sqlite3"
    archive = Archive(path)
    await archive.start()
    original_get, original_write = archive._queue.get, archive._write
    gets = 0
    batch_sizes = []

    async def counted_get():
        nonlocal gets
        gets += 1
        return await original_get()

    def measured_write(batch):
        batch_sizes.append(len(batch))
        return original_write(batch)

    monkeypatch.setattr(archive._queue, "get", counted_get)
    monkeypatch.setattr(archive, "_write", measured_write)
    if expired_deadline:
        monkeypatch.setattr("app.services.archive.FLUSH_SECONDS", 0)
    total = BATCH_SIZE + 7
    try:
        for number in range(total):
            archive.comment(comment(number), status())
        assert archive._queue.qsize() == total  # Writer starts with an already populated queue.
    finally:
        await asyncio.wait_for(archive.close(), timeout=3)
    assert batch_sizes == ([1] * total if expired_deadline else [BATCH_SIZE, 7])
    assert gets == (total + 1 if expired_deadline else 2)
    assert rows(path) == [(f"event-{number}", f"댓글 {number}") for number in range(total)]
    health = archive.get_health()
    assert health.saved_comments == total and health.saved_diagnostics == 0
    assert health.queued == health.dropped == 0 and health.error is None
    assert archive._task is not None and archive._task.done() and archive._executor is None


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


@pytest.mark.parametrize(
    ("fault", "expected_code"),
    [
        ("full", sqlite3.SQLITE_FULL),
        ("readonly", sqlite3.SQLITE_READONLY),
        ("busy", sqlite3.SQLITE_BUSY),
    ],
)
async def test_real_sqlite_write_fault_preserves_commits_and_recovers_after_restart(
    tmp_path: Path, monkeypatch, caplog, fault: str, expected_code: int
) -> None:
    path = tmp_path / "monitor.sqlite3"
    archive = Archive(path)
    await archive.start()
    captured = []
    blocker = None
    original_write = archive._write

    def capture_error(batch):
        try:
            return original_write(batch)
        except sqlite3.Error as exc:
            captured.append(exc.sqlite_errorcode)
            raise

    try:
        for number in range(BATCH_SIZE):
            archive.comment(comment(number), status())
        await asyncio.wait_for(archive._queue.join(), timeout=3)
        original = rows(path)
        assert [row[0] for row in original] == [f"event-{number}" for number in range(BATCH_SIZE)]
        if fault == "full":
            page_count = (await worker_sql(archive, "PRAGMA page_count"))[0][0]
            # SQLite's page ceiling produces genuine SQLITE_FULL without filling the host disk.
            ceiling = (await worker_sql(archive, f"PRAGMA max_page_count={page_count + 1}"))[0][0]
            assert ceiling == page_count + 1
        elif fault == "readonly":
            # Exercise SQLite's actual read-only write guard, not a filesystem remount.
            await worker_sql(archive, "PRAGMA query_only=ON")
        else:
            await worker_sql(archive, "PRAGMA busy_timeout=25")
            blocker = sqlite3.connect(path)
            blocker.execute("BEGIN IMMEDIATE")
        monkeypatch.setattr(archive, "_write", capture_error)
        for number in range(BATCH_SIZE, 2 * BATCH_SIZE):
            body = "PRIVATE_PAYLOAD".ljust(10_000, "x") if number > BATCH_SIZE else "first"
            archive.comment(comment(number, body), status())
        await asyncio.wait_for(archive._queue.join(), timeout=3)
        assert captured == [expected_code]
        health = archive.get_health()
        assert not health.ready and health.error == "write:OperationalError"
        assert health.saved_comments == BATCH_SIZE and health.saved_diagnostics == 0
        assert health.dropped == BATCH_SIZE and health.queued == 0
        archive.comment(comment(2 * BATCH_SIZE, "PRIVATE_PAYLOAD after failure"), status())
        assert archive.get_health().dropped == BATCH_SIZE + 1
        assert rows(path) == original
        assert "PRIVATE_PAYLOAD" not in caplog.text
        assert "PRIVATE_PAYLOAD" not in health.error
    finally:
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        if fault == "full":
            await worker_sql(archive, "PRAGMA max_page_count=2147483646")
        elif fault == "readonly":
            await worker_sql(archive, "PRAGMA query_only=OFF")
        await asyncio.wait_for(archive.close(), timeout=3)

    restarted = Archive(path)
    await restarted.start()
    try:
        assert restarted.get_health().ready
        restarted.comment(comment(2 * BATCH_SIZE + 1), status())
    finally:
        await asyncio.wait_for(restarted.close(), timeout=3)
    assert restarted.get_health().saved_comments == 1
    assert restarted.get_health().dropped == 0 and restarted.get_health().error is None
    assert rows(path) == original + [(f"event-{2 * BATCH_SIZE + 1}", f"댓글 {2 * BATCH_SIZE + 1}")]


async def test_saturated_queue_sql_failure_and_followups_account_for_every_record(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    path = tmp_path / "monitor.sqlite3"
    archive = Archive(path)
    await archive.start()
    entered, release = Event(), Event()
    captured = []
    original_write = archive._write

    def blocked_write(batch):
        entered.set()
        assert release.wait(timeout=5)
        try:
            return original_write(batch)
        except sqlite3.Error as exc:
            captured.append(exc.sqlite_errorcode)
            raise

    try:
        for number in range(BATCH_SIZE):
            archive.comment(comment(number), status())
        await asyncio.wait_for(archive._queue.join(), timeout=3)
        original = rows(path)
        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                "CREATE TRIGGER reject_diagnostic BEFORE INSERT ON diagnostics "
                "BEGIN SELECT RAISE(ABORT, 'PRIVATE_PAYLOAD'); END"
            )
            connection.commit()
        monkeypatch.setattr(archive, "_write", blocked_write)
        for number in range(BATCH_SIZE, 2 * BATCH_SIZE - 1):
            archive.comment(comment(number), status())
        archive.diagnostic("injected_failure")  # Last row aborts after 99 tentative inserts.
        assert await asyncio.to_thread(entered.wait, 2)
        for number in range(2 * BATCH_SIZE, 2 * BATCH_SIZE + CAPACITY + 3):
            archive.comment(comment(number), status())
        health = archive.get_health()
        assert health.queued == BATCH_SIZE + CAPACITY and health.dropped == 3
        progressed = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(progressed.set_result, None)
        await asyncio.wait_for(progressed, timeout=0.1)
        release.set()
        await asyncio.wait_for(archive._queue.join(), timeout=3)
        assert captured == [sqlite3.SQLITE_CONSTRAINT_TRIGGER]
        for number in range(3):
            archive.comment(comment(10_000 + number), status())
        for _ in range(4):
            archive.diagnostic("after_failure")
        health = archive.get_health()
        assert not health.ready and health.error == "write:IntegrityError"
        assert health.saved_comments == BATCH_SIZE and health.saved_diagnostics == 0
        assert health.queued == 0 and health.dropped == BATCH_SIZE + CAPACITY + 3 + 7
        submitted = 2 * BATCH_SIZE + CAPACITY + 3 + 7
        assert health.saved_comments + health.saved_diagnostics + health.dropped == submitted
        assert rows(path) == original
        assert "PRIVATE_PAYLOAD" not in caplog.text
    finally:
        release.set()
        await asyncio.wait_for(archive.close(), timeout=3)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("DROP TRIGGER reject_diagnostic")
        connection.commit()
    restarted = Archive(path)
    await restarted.start()
    restarted.comment(comment(20_000), status())
    await asyncio.wait_for(restarted.close(), timeout=3)
    assert restarted.get_health().saved_comments == 1 and restarted.get_health().error is None
    assert rows(path) == original + [("event-20000", "댓글 20000")]


async def test_backup_copies_consistent_database_while_archive_commits(
    tmp_path: Path, monkeypatch
) -> None:
    path, destination = tmp_path / "monitor.sqlite3", tmp_path / "snapshot.sqlite3"
    archive = Archive(path)
    await archive.start()
    copying, committed = Event(), Event()
    backup_task = None
    progress_calls = []
    original_connect = sqlite3.connect

    def progress(code, remaining, total):
        progress_calls.append((code, remaining, total))
        if not copying.is_set() and remaining > 0:
            copying.set()
            assert committed.wait(timeout=5)

    class SteppedConnection(sqlite3.Connection):
        def backup(self, target, **kwargs):
            return super().backup(target, pages=1, progress=progress, sleep=0.01, **kwargs)

    def stepped_connect(*args, **kwargs):
        return original_connect(*args, factory=SteppedConnection, **kwargs)

    try:
        for number in range(BATCH_SIZE):
            archive.comment(comment(number, "x" * 10_000), status())
        await asyncio.wait_for(archive._queue.join(), timeout=3)
        monkeypatch.setattr(sqlite3, "connect", stepped_connect)
        backup_task = asyncio.create_task(asyncio.to_thread(backup, path, destination))
        assert await asyncio.to_thread(copying.wait, 2)
        assert not backup_task.done() and progress_calls[0][1] > 0
        for number in range(BATCH_SIZE, 2 * BATCH_SIZE):
            archive.comment(comment(number, "y" * 10_000), status())
        await asyncio.wait_for(archive._queue.join(), timeout=3)
        assert archive.get_health().saved_comments == 2 * BATCH_SIZE
        assert not backup_task.done(), "Second transaction must commit while the backup is active"
        committed.set()
        await asyncio.wait_for(backup_task, timeout=5)
        source_rows, snapshot_rows = rows(path), rows(destination)
        assert snapshot_rows == source_rows
        assert [row[0] for row in snapshot_rows] == [
            f"event-{number}" for number in range(2 * BATCH_SIZE)
        ]
        assert progress_calls[-1][0] == sqlite3.SQLITE_DONE and progress_calls[-1][1] == 0
        assert archive.get_health().dropped == 0 and archive.get_health().error is None
        with closing(sqlite3.connect(destination)) as connection:
            assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    finally:
        committed.set()
        if backup_task is not None:
            await asyncio.wait_for(asyncio.shield(backup_task), timeout=5)
        await asyncio.wait_for(archive.close(), timeout=3)
