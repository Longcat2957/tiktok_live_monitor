#!/usr/bin/env bash
set -euo pipefail
AUTOSTART_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/labwc/autostart"
SYSTEM_AUTOSTART=/etc/xdg/labwc/autostart

# Old install.sh copied the system file, launching Pi desktop services twice.
# Only remove an unchanged copy at the start of our app's autostart file.
if [[ ! -f "$AUTOSTART_FILE" || ! -s "$SYSTEM_AUTOSTART" ]] ||
   ! grep -Fxq '# tiktok-live-monitor kiosk' "$AUTOSTART_FILE"; then
  exit 0
fi
system_bytes="$(wc -c < "$SYSTEM_AUTOSTART")"
if cmp -s -n "$system_bytes" "$SYSTEM_AUTOSTART" "$AUTOSTART_FILE"; then
  backup="$(mktemp "$AUTOSTART_FILE.backup.XXXXXXXX")"
  cp -p -- "$AUTOSTART_FILE" "$backup"
  tail -c "+$((system_bytes + 1))" -- "$backup" > "$AUTOSTART_FILE"
  echo "중복 Desktop 자동 시작 설정을 제거했습니다. 백업: $backup"
  echo '작업 표시줄 중복 실행을 해소하려면 방송 종료 후 로그아웃·로그인하거나 재부팅하세요.'
fi
