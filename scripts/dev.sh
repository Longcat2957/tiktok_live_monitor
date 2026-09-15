#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${1:-}" == --help ]]; then
  cat <<'EOF'
사용법: ./scripts/dev.sh
Linux 데스크톱에서 의존성 설치 → mock 개발 서버 → Chromium 실행.
Ctrl+C로 서버와 전용 브라우저를 함께 종료합니다.

환경변수:
  COMMENT_SOURCE=tiktok  첫 화면의 초기 모드 (계정은 화면에서 입력, 기본 mock)
  CHROMIUM_BIN=/경로     Chromium 실행 파일 직접 지정
  DEV_OPEN_BROWSER=0    브라우저 없이 서버만 실행 (기본 1)
EOF
  exit 0
fi
if (( $# != 0 )); then
  echo '지원하지 않는 인자입니다. ./scripts/dev.sh --help를 확인하세요.' >&2
  exit 1
fi

for tool in uv pnpm node curl setsid; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "$tool 명령이 필요합니다. docs/installation-dev.md를 확인하세요." >&2
    exit 1
  fi
done

if [[ "${DEV_OPEN_BROWSER:-1}" != 0 ]]; then
  if [[ -z "${CHROMIUM_BIN:-}" ]]; then
    for browser in chromium chromium-browser; do
      if command -v "$browser" >/dev/null 2>&1; then
        CHROMIUM_BIN="$(command -v "$browser")"
        break
      fi
    done
  fi
  if [[ -z "${CHROMIUM_BIN:-}" ]] || ! command -v "$CHROMIUM_BIN" >/dev/null 2>&1; then
    echo 'Chromium이 필요합니다. 설치하거나 CHROMIUM_BIN을 지정하세요.' >&2
    exit 1
  fi
  if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    echo '그래픽 세션에서 실행하세요. 서버만 실행하려면 DEV_OPEN_BROWSER=0을 지정하세요.' >&2
    exit 1
  fi
fi

export COMMENT_SOURCE="${COMMENT_SOURCE:-mock}"
echo "개발 의존성 설치 (source=$COMMENT_SOURCE)"
(cd "$PROJECT_ROOT/backend" && uv sync --locked)
(cd "$PROJECT_ROOT/frontend" && pnpm install --frozen-lockfile)

# Fail before launching anything if either fixed development port is occupied.
"$PROJECT_ROOT/backend/.venv/bin/python" - <<'PY'
import socket
import sys

for port in (8000, 5173):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            sys.exit(f"127.0.0.1:{port} 포트를 사용할 수 없습니다. 기존 서버를 확인하세요.")
PY

pids=()
browser_profile=''
cleanup() {
  trap - EXIT INT TERM
  # Each child owns a session, including reload workers and pnpm's Vite child.
  for pid in "${pids[@]}"; do
    kill -TERM -- "-$pid" 2>/dev/null || true
  done
  for attempt in {1..50}; do
    alive=0
    for pid in "${pids[@]}"; do
      if kill -0 -- "-$pid" 2>/dev/null; then alive=1; fi
    done
    if (( alive == 0 )); then break; fi
    sleep 0.1
  done
  for pid in "${pids[@]}"; do
    kill -KILL -- "-$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  if [[ -n "$browser_profile" ]]; then rm -rf -- "$browser_profile"; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$PROJECT_ROOT/backend"
setsid uv run --locked --no-sync uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &
pids+=("$!")
cd "$PROJECT_ROOT/frontend"
BACKEND_URL=http://127.0.0.1:8000 setsid pnpm dev --port 5173 --strictPort &
pids+=("$!")

check_servers() {
  for pid in "${pids[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo '개발 서버가 종료되었습니다. 위 로그를 확인하세요.' >&2
      exit 1
    fi
  done
}

echo '개발 서버 준비 대기 (최대 60초)'
deadline=$((SECONDS + 60))
while true; do
  check_servers
  if curl --fail --silent --max-time 2 http://127.0.0.1:8000/health >/dev/null && \
     curl --fail --silent --max-time 2 http://127.0.0.1:5173/ >/dev/null && \
     curl --fail --silent --max-time 2 http://127.0.0.1:5173/health >/dev/null; then
    break
  fi
  if (( SECONDS >= deadline )); then
    echo '개발 서버 준비 시간이 초과되었습니다.' >&2
    exit 1
  fi
  sleep 1
done

server_pids=("${pids[@]}")
if [[ "${DEV_OPEN_BROWSER:-1}" != 0 ]]; then
  browser_profile="$(mktemp -d /tmp/tiktok-live-monitor-dev.XXXXXXXX)"
  setsid "$CHROMIUM_BIN" --user-data-dir="$browser_profile" --no-first-run \
    --no-default-browser-check --new-window http://127.0.0.1:5173 &
  browser_pid=$!
  pids+=("$browser_pid")
  # Check server health separately: closing the browser leaves development running.
  sleep 1
  if ! kill -0 "$browser_pid" 2>/dev/null; then
    wait "$browser_pid" || { echo 'Chromium 실행에 실패했습니다.' >&2; exit 1; }
  fi
fi

echo '개발 모드 실행 중: http://127.0.0.1:5173 (종료: Ctrl+C)'
# Include the browser in cleanup, but only monitor the two server processes.
while true; do
  for pid in "${server_pids[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo '개발 서버가 종료되어 전체 실행을 정리합니다.' >&2
      exit 1
    fi
  done
  sleep 1
done
