import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta

from app.realtime.broadcaster import WebSocketBroadcaster
from app.schemas.events import Comment, Status, User, YouTubeStatus
from app.services.archive import Archive, ArchiveContext
from app.services.event_sink import EventSink


async def eventually(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.005)


def comment(body, received_at=None):
    values = {} if received_at is None else {"received_at": received_at}
    return Comment(user=User(nickname="n", unique_id="u"), comment=body, **values)


def context(source):
    return ArchiveContext("session", source, "account")


async def test_startup_retention_only_removes_expired_youtube_rows_and_reuses_schema(
    tmp_path, monkeypatch
):
    fixed_now = datetime(2026, 11, 5, 12, tzinfo=UTC)
    cutoff = fixed_now - timedelta(days=30) + timedelta(seconds=60)
    path = tmp_path / "archive.sqlite3"
    archive = Archive(path)
    await archive.start()
    for source in ["youtube", "tiktok", "mock"]:
        for label, stamp in [
            ("old", cutoff - timedelta(days=1)),
            ("edge", cutoff),
            ("recent", cutoff + timedelta(milliseconds=1)),
        ]:
            archive.comment(comment(source + label, stamp), context(source))
            archive.diagnostic(label, context(source))
    await archive.close()
    with sqlite3.connect(path) as db:
        for label, stamp in [
            ("old", cutoff - timedelta(days=1)),
            ("edge", cutoff),
            ("recent", cutoff + timedelta(milliseconds=1)),
        ]:
            db.execute(
                "UPDATE diagnostics SET occurred_at=? WHERE event=?", (stamp.isoformat(), label)
            )

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr("app.services.archive.datetime", Clock)
    reopened = Archive(path)
    try:
        await reopened.start()
        assert reopened.get_health().ready and reopened.get_health().error is None
        with sqlite3.connect(path) as db:
            assert db.execute("PRAGMA user_version").fetchone() == (1,)
            assert db.execute("SELECT comment FROM comments WHERE source='youtube'").fetchall() == [
                ("youtuberecent",)
            ]
            assert db.execute(
                "SELECT event FROM diagnostics WHERE source='youtube'"
            ).fetchall() == [("recent",)]
            for source in ["tiktok", "mock"]:
                assert db.execute(
                    "SELECT count(*) FROM comments WHERE source=?", (source,)
                ).fetchone() == (3,)
                assert db.execute(
                    "SELECT count(*) FROM diagnostics WHERE source=?", (source,)
                ).fetchone() == (3,)
            query_plan = db.execute(
                "EXPLAIN QUERY PLAN DELETE FROM comments WHERE source='youtube' AND received_at<=?",
                (cutoff.isoformat(),),
            ).fetchall()
            assert "comments_youtube_received_at" in str(query_plan)
    finally:
        await reopened.close()


async def test_idle_writer_expires_youtube_without_waiting_for_new_comments(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.archive.YOUTUBE_RETENTION_SECONDS", 0.02)
    monkeypatch.setattr("app.services.archive.FLUSH_SECONDS", 0.001)
    archive = Archive(tmp_path / "archive.sqlite3")
    await archive.start()
    try:
        archive.comment(
            comment("expired", datetime.now(UTC) - timedelta(days=31)), context("youtube")
        )
        archive.comment(comment("keep"), context("youtube"))
        await eventually(lambda: archive.get_health().saved_comments == 2)
        with sqlite3.connect(archive.path) as db:
            await eventually(lambda: db.execute("SELECT count(*) FROM comments").fetchone() == (1,))
            assert db.execute("SELECT comment FROM comments").fetchall() == [("keep",)]
        assert archive.get_health().dropped == 0
    finally:
        await archive.close()


async def test_retention_failure_reports_error_but_preserves_queue_and_recovers(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr("app.services.archive.YOUTUBE_RETENTION_SECONDS", 0.02)
    monkeypatch.setattr("app.services.archive.FLUSH_SECONDS", 0.001)
    archive = Archive(tmp_path / "archive.sqlite3")
    prune = archive._prune_youtube
    enabled = False

    def failing_prune():
        if not enabled:
            raise sqlite3.OperationalError("private diagnostic text")
        prune()

    monkeypatch.setattr(archive, "_prune_youtube", failing_prune)
    await archive.start()
    try:
        assert archive.get_health().error == "retention:OperationalError"
        archive.comment(comment("one"), context("youtube"))
        archive.comment(comment("two"), context("tiktok"))
        await eventually(lambda: archive.get_health().saved_comments == 2)
        assert archive.get_health().dropped == 0
        assert "private diagnostic text" not in caplog.text
        enabled = True
        await eventually(lambda: archive.get_health().error is None)
    finally:
        await archive.close()
    with sqlite3.connect(archive.path) as db:
        assert db.execute("SELECT comment FROM comments ORDER BY id").fetchall() == [
            ("one",),
            ("two",),
        ]


async def test_youtube_archive_precedes_display_queue_drop(tmp_path):
    archive = Archive(tmp_path / "archive.sqlite3")
    await archive.start()
    broadcaster = WebSocketBroadcaster(
        Status(
            source="tiktok",
            state="connected",
            message="test",
            username="test",
            youtube=YouTubeStatus(video_id="abcdefghijk", state="connected", message="test"),
        )
    )
    queue = asyncio.Queue(1)
    sink = EventSink(queue, broadcaster, archive, platform="youtube")
    for body in ["one", "two", "three"]:
        sink.publish(comment(body))
    assert broadcaster.dropped_comments == 2
    assert queue.get_nowait().comment == "three"
    queue.task_done()
    await archive.close()
    with sqlite3.connect(archive.path) as db:
        assert db.execute(
            "SELECT source, username, comment FROM comments ORDER BY id"
        ).fetchall() == [("youtube", "abcdefghijk", body) for body in ["one", "two", "three"]]
