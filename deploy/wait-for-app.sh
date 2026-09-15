#!/usr/bin/env bash
set -euo pipefail
APP_URL="${APP_URL:-http://127.0.0.1:8000}"
for browser in chromium chromium-browser; do
  if command -v "$browser" >/dev/null 2>&1; then
    CHROMIUM_BIN="$(command -v "$browser")"
    break
  fi
done
if [[ -z "${CHROMIUM_BIN:-}" ]]; then
  echo 'Chromium을 찾을 수 없습니다. sudo apt install chromium' >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo 'curl이 필요합니다. sudo apt install curl' >&2
  exit 1
fi
# Keep waiting across network outages and long first builds; log once every 30s.
attempt=0
until curl --fail --silent --max-time 4 "$APP_URL/health" >/dev/null && \
      curl --fail --silent --max-time 4 "$APP_URL/" >/dev/null; do
  if (( attempt % 10 == 0 )); then
    echo "$(date -Is) 앱 준비 대기: $APP_URL"
  fi
  attempt=$((attempt + 1))
  sleep 3
done
echo "$(date -Is) 앱 준비 완료. Chromium kiosk 시작"
exec "$CHROMIUM_BIN" "$APP_URL" --kiosk --noerrdialogs --disable-infobars \
  --no-first-run --start-maximized --ozone-platform=wayland \
  --user-data-dir="${XDG_CONFIG_HOME:-$HOME/.config}/tiktok-live-monitor/chromium"
