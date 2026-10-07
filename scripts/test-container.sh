#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SMOKE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/tiktok-monitor-smoke.XXXXXX")"
SMOKE_PROJECT="tiktok-monitor-smoke-$(date +%s)-$$"
export SMOKE_IMAGE="tiktok-live-monitor:${SMOKE_PROJECT}"
export SMOKE_ENV_FILE="$PROJECT_ROOT/.env.example"
command -v python3 >/dev/null || { echo 'SQLite snapshot 검증에 Python 3가 필요합니다.' >&2; exit 1; }

cat >"$SMOKE_DIR/compose.yaml" <<'YAML'
services:
  app:
    image: ${SMOKE_IMAGE}
    env_file: !override
      - ${SMOKE_ENV_FILE}
    ports: !override
      - "127.0.0.1::8000"
    environment:
      MOCK_INTERVAL_SECONDS: "0.03"
      LOG_LEVEL: INFO
YAML

# Explicit files and an empty interpolation env keep the user's .env untouched.
compose=(docker compose --env-file /dev/null --project-name "$SMOKE_PROJECT"
  --file "$PROJECT_ROOT/compose.yaml" --file "$SMOKE_DIR/compose.yaml")
cleanup() {
  local result=$?
  trap - EXIT
  if (( result != 0 )); then
    "${compose[@]}" logs --no-color >"$SMOKE_DIR/container.log" 2>&1 || true
    echo "Container smoke failed; logs: $SMOKE_DIR/container.log" >&2
    tail -n 200 "$SMOKE_DIR/container.log" >&2
  fi
  # This project's unique test volume never shares the production archive.
  "${compose[@]}" down --timeout 20 --remove-orphans --volumes >/dev/null 2>&1 || true
  docker image rm "$SMOKE_IMAGE" >/dev/null 2>&1 || true
  if (( result == 0 )); then rm -rf -- "$SMOKE_DIR"; fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# !override requires Docker Compose 2.24.4 or newer; config fails before building.
"${compose[@]}" config --quiet
"${compose[@]}" build
"${compose[@]}" run --rm --no-deps --no-TTY app python - <<'PY'
import os
from pathlib import Path

archive = Path(os.environ["ARCHIVE_PATH"])
assert os.geteuid() == 10001
assert not archive.exists(), "Smoke archive must start without a database"
assert archive.parent.stat().st_uid == archive.parent.stat().st_gid == 10001
PY
"${compose[@]}" up --detach --wait --wait-timeout 120
SMOKE_CONTAINER="$("${compose[@]}" ps --quiet app)"
[[ -n "$SMOKE_CONTAINER" ]]
[[ "$(docker inspect --format '{{.Config.User}}' "$SMOKE_CONTAINER")" == '10001:10001' ]]
[[ "$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.title"}}' "$SMOKE_IMAGE")" == 'tiktok-live-monitor' ]]
[[ "$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$SMOKE_CONTAINER")" == 'true' ]]
SMOKE_BINDING="$(docker inspect --format '{{range (index .NetworkSettings.Ports "8000/tcp")}}{{.HostIp}}:{{.HostPort}}{{"\n"}}{{end}}' "$SMOKE_CONTAINER")"
[[ "$SMOKE_BINDING" =~ ^127\.0\.0\.1:[0-9]+$ ]]
curl --fail --silent --show-error --max-time 5 "http://$SMOKE_BINDING/health" --output "$SMOKE_DIR/health.json"
curl --fail --silent --show-error --max-time 5 "http://$SMOKE_BINDING/" --output "$SMOKE_DIR/index.html"

"${compose[@]}" exec --no-TTY app python - <<'PY'
import asyncio
import json
import os
import sqlite3
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

BASE = "http://127.0.0.1:8000"


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"src", "href"} and value and "_app/immutable/" in value:
                self.paths.append(value)


async def main():
    assert os.geteuid() == 10001, "Container must run as the monitor user"
    archive = Path(os.environ["ARCHIVE_PATH"])
    assert archive.is_file() and archive.stat().st_uid == archive.stat().st_gid == 10001
    async with httpx.AsyncClient(base_url=BASE, headers={"Origin": BASE}, timeout=5) as client:
        health = await client.get("/health")
        assert health.status_code == 200, "Idle server must be healthy"
        assert health.json()["source"]["state"] == "idle", "Server must await an explicit start"
        assert health.json()["source"]["source"] == "tiktok"
        assert health.json()["pending_commands"] == 0, "Unexpected command at startup"
        assert health.json()["storage"]["ready"] is True
        initial = (await client.get("/config")).json()
        assert initial["session_id"] == health.json()["source"]["session_id"]
        page = await client.get("/")
        assert page.status_code == 200 and "text/html" in page.headers["content-type"]
        assets = Assets()
        assets.feed(page.text)
        assert assets.paths, "Static HTML must reference the compiled frontend"
        for path in set(assets.paths):
            asset = await client.get(urljoin(BASE + "/", path))
            assert asset.status_code == 200 and asset.content, "Compiled frontend asset is missing"
        assert (await client.get("/health", headers={"Host": "invalid.test"})).status_code == 400
        try:
            async with connect(BASE.replace("http:", "ws:") + "/ws", origin="https://invalid.test"):
                raise AssertionError("Cross-origin WebSocket was accepted")
        except InvalidStatus as denied:
            assert denied.response.status_code == 403

        async with connect(BASE.replace("http:", "ws:") + "/ws", origin=BASE) as socket:
            first = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
            assert first["type"] == "status" and first["state"] == "idle"
            session = first["session_id"]

            async def change(method, path, **values):
                nonlocal session
                previous = session
                response = await client.request(method, path, json={"session_id": session, **values})
                assert response.status_code == 200, "Monitor command failed"
                current = response.json()
                session = current["session_id"]
                assert session != previous, "Command must create a new session"
                async with asyncio.timeout(5):
                    while True:
                        event = json.loads(await socket.recv())
                        if event["type"] == "status" and event["session_id"] == session:
                            return current

            async def comment():
                async with asyncio.timeout(5):
                    while True:
                        event = json.loads(await socket.recv())
                        if event["type"] == "comment":
                            assert event["comment"] and (event["user"]["nickname"] or event["user"]["unique_id"])
                            return event["id"]

            started = await change("POST", "/account", source="mock")
            assert started["source"] == "mock" and started["username"] is None
            first_comment = await comment()
            async with asyncio.timeout(5):
                with sqlite3.connect(archive.as_uri() + "?mode=ro", uri=True) as database:
                    while not database.execute(
                        "SELECT 1 FROM comments WHERE event_id=? AND source='mock'", (first_comment,)
                    ).fetchone():
                        await asyncio.sleep(0.05)
                    assert database.execute("SELECT COUNT(*) FROM diagnostics").fetchone()[0] > 0
            async with asyncio.timeout(5):
                while True:
                    event = json.loads(await socket.recv())
                    if event["type"] == "activity":
                        assert event["kind"] in {"gift", "follow", "share", "subscribe"}
                        break
            previous = session
            await change("POST", "/refresh")
            assert await comment() != first_comment, "Refresh must receive new comments"
            stale = await client.post("/refresh", json={"session_id": previous})
            assert stale.status_code == 409, "Old sessions must not change the receiver"
            updated = await change("PATCH", "/config", settings={"comment_history_size": 7})
            assert updated["comment_history_size"] == 7 and updated["source"] == "mock"
            assert (await client.get("/config")).json()["comment_history_size"] == 7
            await comment()
            stopped = await change("DELETE", "/account")
            assert stopped["state"] == "idle" and stopped["username"] is None
            assert (await client.get("/health")).json()["source"]["state"] == "idle"
            try:
                async with asyncio.timeout(0.2):
                    while True:
                        event = json.loads(await socket.recv())
                        assert event["type"] == "status", "Stopped receiver emitted a feed event"
            except TimeoutError:
                pass
            # Exercise process shutdown with active workers, not only an idle server.
            await change("POST", "/account", source="mock")
            last_comment = await comment()
            Path("/tmp/archive-observed.json").write_text(json.dumps({"event_id": last_comment}))


asyncio.run(main())
print("Container HTTP, static assets and mock WebSocket lifecycle passed.")
PY

"${compose[@]}" exec --no-TTY app cat /tmp/archive-observed.json >"$SMOKE_DIR/archive-observed.json"
"${compose[@]}" stop --timeout 20 app
SMOKE_EXIT="$(docker inspect --format '{{.State.ExitCode}}' "$SMOKE_CONTAINER")"
[[ "$SMOKE_EXIT" == 0 || "$SMOKE_EXIT" == 143 ]]
"${compose[@]}" logs --no-color app >"$SMOKE_DIR/container.log"
grep -q 'Application shutdown complete' "$SMOKE_DIR/container.log"
"${compose[@]}" run --rm --no-deps --no-TTY app python - <<'PY' >"$SMOKE_DIR/archive-stopped.json"
import json
import os
import sqlite3
from pathlib import Path

with sqlite3.connect(Path(os.environ["ARCHIVE_PATH"]).as_uri() + "?mode=ro", uri=True) as database:
    assert database.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    comments = database.execute("SELECT COUNT(*), MAX(id) FROM comments").fetchone()
    diagnostics = database.execute("SELECT COUNT(*) FROM diagnostics").fetchone()[0]
    print(json.dumps({"comments": comments, "diagnostics": diagnostics}))
PY
"${compose[@]}" up --detach --no-build --pull never --force-recreate --wait --wait-timeout 120
SMOKE_CONTAINER="$("${compose[@]}" ps --quiet app)"
"${compose[@]}" exec --no-TTY app python -m app.services.archive /data/smoke-backup.sqlite3
if "${compose[@]}" exec --no-TTY app python -m app.services.archive /data/smoke-backup.sqlite3 \
  >"$SMOKE_DIR/backup-existing.log" 2>&1; then
  echo 'Snapshot CLI overwrote an existing destination.' >&2
  exit 1
fi
docker cp "$SMOKE_CONTAINER:/data/smoke-backup.sqlite3" "$SMOKE_DIR/smoke-backup.sqlite3"
python3 - "$SMOKE_DIR" <<'PY'
import json
import sqlite3
import sys
from pathlib import Path

directory = Path(sys.argv[1])
stopped = json.loads((directory / "archive-stopped.json").read_text())
observed = json.loads((directory / "archive-observed.json").read_text())
with sqlite3.connect((directory / "smoke-backup.sqlite3").as_uri() + "?mode=ro", uri=True) as database:
    assert database.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert list(database.execute("SELECT COUNT(*), MAX(id) FROM comments").fetchone()) == stopped["comments"]
    assert database.execute("SELECT COUNT(*) FROM diagnostics").fetchone()[0] >= stopped["diagnostics"] > 0
    assert database.execute("SELECT 1 FROM comments WHERE event_id=?", (observed["event_id"],)).fetchone(), "Shutdown must flush the last observed comment"
    assert database.execute("PRAGMA journal_mode").fetchone()[0] == "delete", "Snapshot must be a standalone DB"
print("SQLite creation, shutdown flush, container replacement and external snapshot passed.")
PY
"${compose[@]}" exec --no-TTY app rm -- /data/smoke-backup.sqlite3
"${compose[@]}" stop --timeout 20 app

# An isolated 1 MiB tmpfs exercises actual ENOSPC without filling the host disk
# or attaching any project volume. The test subclass only observes error codes.
docker run --rm --interactive --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /data:rw,size=1m,uid=10001,gid=10001,mode=0700 \
  --tmpfs /tmp:rw,size=1m,mode=1777 \
  "$SMOKE_IMAGE" python - <<'PY' 2>"$SMOKE_DIR/disk-full.log"
import asyncio
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import httpx

from app.config import Settings
from app.main import create_app
from app.schemas.events import Comment, User
from app.services.archive import Archive


class ObservedArchive(Archive):
    attempted = 0
    failure_code = None

    def _enqueue(self, record):
        self.attempted += 1
        super()._enqueue(record)

    def _fail(self, operation, exc):
        self.failure_code = getattr(exc, "sqlite_errorcode", None)
        super()._fail(operation, exc)


async def main():
    path = Path("/data/monitor.sqlite3")
    assert not path.exists()
    app = create_app(Settings(_env_file=None, archive_path=path, log_level="WARNING"))
    with patch("app.services.monitor.Archive", ObservedArchive):
        async with app.router.lifespan_context(app):
            monitor = app.state.monitor
            archive = monitor.archive
            assert archive.get_health().ready
            user = User(nickname="Full fixture", unique_id="full")

            def comment(number, text):
                archive.comment(
                    Comment(id=f"full-{number}", user=user, comment=text),
                    monitor.broadcaster.status,
                )

            for number in range(10):
                comment(number, "committed prefix")
            async with asyncio.timeout(5):
                while archive.get_health().saved_comments != 10:
                    await asyncio.sleep(0.02)
            for number in range(10, 210):
                marker = "PRIVATE_DISK_PAYLOAD"
                comment(number, marker + "x" * (10_000 - len(marker)))
            async with asyncio.timeout(5):
                while archive.get_health().error is None:
                    await asyncio.sleep(0.02)
            failed = archive.get_health()
            assert archive.failure_code == sqlite3.SQLITE_FULL
            assert failed.error == "write:OperationalError"
            assert not failed.ready and failed.dropped > 0 and failed.queued == 0
            comment(210, "PRIVATE_DISK_PAYLOAD after failure")
            archive.diagnostic("disk_full_fixture_after_failure")
            assert archive.get_health().dropped == failed.dropped + 2
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
            ) as client:
                response = await client.get("/health")
                assert response.status_code == 503
                assert response.json()["storage"]["error"] == failed.error
                assert (await client.get("/config")).status_code == 200

    final = archive.get_health()
    assert final.queued == 0 and archive._executor is None
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        rows = database.execute("SELECT id,event_id FROM comments ORDER BY id").fetchall()
        assert rows == [(number + 1, f"full-{number}") for number in range(10)]
        assert len(rows) == final.saved_comments
        assert database.execute("SELECT COUNT(*) FROM diagnostics").fetchone()[0] == final.saved_diagnostics
    assert final.saved_comments + final.saved_diagnostics + final.dropped == archive.attempted
    print(json.dumps({"sqlite_errorcode": archive.failure_code, "storage": final.model_dump()}))


asyncio.run(main())
PY
grep -q 'SQLite archive write failed (OperationalError)' "$SMOKE_DIR/disk-full.log"
if grep -q 'PRIVATE_DISK_PAYLOAD' "$SMOKE_DIR/disk-full.log"; then
  echo 'Disk-full diagnostics exposed a comment payload.' >&2
  exit 1
fi
echo 'Bounded tmpfs SQLITE_FULL, committed prefix, degraded health and safe diagnostics passed.'
if [[ -n "${SMOKE_PUBLISH_TAG:-}" ]]; then
  # Keep the exact tested image for CI publication after the smoke tag is removed.
  docker tag "$SMOKE_IMAGE" "$SMOKE_PUBLISH_TAG"
fi
echo 'Container smoke passed: non-root, read-only, localhost-only, SQLite persistence and clean shutdown.'
