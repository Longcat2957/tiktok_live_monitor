#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SMOKE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/tiktok-monitor-smoke.XXXXXX")"
SMOKE_PROJECT="tiktok-monitor-smoke-$(date +%s)-$$"
export SMOKE_IMAGE="tiktok-live-monitor:${SMOKE_PROJECT}"
export SMOKE_ENV_FILE="$PROJECT_ROOT/.env.example"

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
  "${compose[@]}" down --timeout 20 --remove-orphans >/dev/null 2>&1 || true
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
from html.parser import HTMLParser
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
    async with httpx.AsyncClient(base_url=BASE, headers={"Origin": BASE}, timeout=5) as client:
        health = await client.get("/health")
        assert health.status_code == 200, "Idle server must be healthy"
        assert health.json()["source"]["state"] == "idle", "Server must await an explicit start"
        assert health.json()["source"]["source"] == "tiktok"
        assert health.json()["pending_commands"] == 0, "Unexpected command at startup"
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
            await comment()


asyncio.run(main())
print("Container HTTP, static assets and mock WebSocket lifecycle passed.")
PY

"${compose[@]}" stop --timeout 20 app
SMOKE_EXIT="$(docker inspect --format '{{.State.ExitCode}}' "$SMOKE_CONTAINER")"
[[ "$SMOKE_EXIT" == 0 || "$SMOKE_EXIT" == 143 ]]
"${compose[@]}" logs --no-color app >"$SMOKE_DIR/container.log"
grep -q 'Application shutdown complete' "$SMOKE_DIR/container.log"
echo 'Container smoke passed: non-root, read-only, localhost-only and clean shutdown.'
