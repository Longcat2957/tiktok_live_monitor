"""Kill a real writer after uncommitted pages spill into the WAL."""

import asyncio
import json
import os
import select
import signal
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from threading import Event

import pytest

from app.schemas.events import Comment, Status, User
from app.services.archive import BATCH_SIZE, Archive, Record
from stress_pipeline import run_soak


async def crash_child(path: Path) -> None:
    class StagedArchive(Archive):
        committed = False

        def _open(self) -> None:
            super()._open()
            assert self._connection is not None
            self._connection.execute("PRAGMA wal_autocheckpoint=0")
            self._connection.execute("PRAGMA cache_size=2")

        def _write(self, batch: list[Record]) -> tuple[int, int]:
            if not self.committed:
                result = super()._write(batch)
                self.committed = True
                return result
            assert self._connection is not None
            wal = path.with_name(path.name + "-wal")
            before = wal.stat().st_size
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.executemany(
                "INSERT INTO comments(event_id,received_at,session_id,source,username,"
                "user_id,nickname,comment) VALUES (?,?,?,?,?,?,?,?)",
                [values for table, values in batch if table == "comments"],
            )
            assert self._connection.in_transaction
            print(
                json.dumps({"staged": True, "wal_before": before, "wal_after": wal.stat().st_size}),
                flush=True,
            )
            Event().wait()  # Parent kills this process while the transaction is open.
            raise AssertionError("Uncommitted writer unexpectedly resumed")

    archive = StagedArchive(path)
    await archive.start()
    assert archive.get_health().ready
    status = Status(source="mock", state="connected", message="crash test")
    user = User(nickname="test", unique_id="test")
    for number in range(BATCH_SIZE * 2):
        archive.comment(
            Comment(
                id=f"crash-{number}",
                user=user,
                comment="committed"
                if number < BATCH_SIZE
                else "PRIVATE_CRASH_PAYLOAD" + "x" * 9000,
            ),
            status,
        )
    await asyncio.Event().wait()


@pytest.mark.skipif(sys.platform == "win32", reason="Requires POSIX SIGKILL and pipe readiness")
async def test_sigkill_preserves_committed_wal_prefix_and_resumes(tmp_path: Path) -> None:
    path = tmp_path / "monitor.sqlite3"
    backend = Path(__file__).resolve().parents[2]
    child = subprocess.Popen(
        [sys.executable, "-u", str(Path(__file__).resolve()), str(path)],
        cwd=backend,
        env={**os.environ, "PYTHONPATH": str(backend)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert child.stdout is not None
        assert await asyncio.to_thread(select.select, [child.stdout], [], [], 10) != ([], [], []), (
            "Writer did not stage its transaction"
        )
        marker = json.loads(child.stdout.readline())
        assert marker["staged"] and marker["wal_after"] > marker["wal_before"] > 0
        child.kill()
        _, stderr = await asyncio.to_thread(child.communicate, timeout=5)
        assert child.returncode == -signal.SIGKILL
        assert b"PRIVATE_CRASH_PAYLOAD" not in stderr
    finally:
        if child.poll() is None:
            child.kill()
        await asyncio.to_thread(child.wait, timeout=5)
        if child.stdout is not None:
            child.stdout.close()
        if child.stderr is not None:
            child.stderr.close()

    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert database.execute("SELECT id,event_id FROM comments ORDER BY id").fetchall() == [
            (number + 1, f"crash-{number}") for number in range(BATCH_SIZE)
        ]
    resumed = Archive(path)
    await resumed.start()
    assert resumed.get_health().ready
    resumed.comment(
        Comment(id="resumed", user=User(nickname="test", unique_id="test"), comment="after kill"),
        Status(source="mock", state="connected", message="resume"),
    )
    await resumed.close()
    assert resumed.get_health().saved_comments == 1 and resumed.get_health().queued == 0
    with closing(sqlite3.connect(path)) as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert database.execute("SELECT id,event_id FROM comments ORDER BY id").fetchall() == [
            *((number + 1, f"crash-{number}") for number in range(BATCH_SIZE)),
            (BATCH_SIZE + 1, "resumed"),
        ]


@pytest.mark.parametrize("profile", [False, True])
async def test_sustained_runner_flushes_real_sqlite_and_websocket_clients(
    tmp_path: Path, profile: bool
) -> None:
    result = await run_soak(
        duration=0.2,
        rate=100,
        clients=2,
        comment_size=1000,
        max_p99_ms=5000,
        max_latency_ms=5000,
        directory=tmp_path,
        profile=profile,
    )
    assert result["ok"], result
    assert result["sqlite_comments"] == result["generated"]
    assert not list(tmp_path.iterdir())
    assert ("profile" in result) is profile
    if profile:
        measured = result["profile"]
        assert measured["main"]["timer"] == "thread_time_cpu"
        assert measured["writer"]["timer"] == "wall"
        writer = measured["writer"]
        assert (
            writer["attempted_records"] == result["sqlite_comments"] + result["sqlite_diagnostics"]
        )
        assert writer["sql_self_wall_seconds"]["executemany"]["calls"] == writer["batches"] * 2
        assert writer["sql_self_wall_seconds"]["__exit__"]["calls"] == writer["batches"]
        assert writer["total_write_thread_cpu_seconds"] > 0
        assert len(measured["main"]["top_self_functions"]) <= 20


if __name__ == "__main__":
    asyncio.run(crash_child(Path(sys.argv[1])))
