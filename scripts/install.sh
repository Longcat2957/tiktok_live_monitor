#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
if [[ "$(id -u)" == 0 ]]; then
  echo 'Desktop에 자동 로그인할 일반 사용자로 실행하세요 (sudo로 스크립트 전체 실행 금지).' >&2
  exit 1
fi
if [[ ! -f /etc/os-release ]]; then
  echo 'Raspberry Pi OS Desktop 64-bit가 필요합니다.' >&2
  exit 1
fi
source /etc/os-release
if [[ "${ID:-}" != debian && "${ID:-}" != raspbian ]]; then
  echo '지원 OS: Raspberry Pi OS Desktop (Debian 계열).' >&2
  exit 1
fi
if [[ "$(uname -m)" != aarch64 ]]; then
  echo '안내: 이 장비는 ARM64 Pi가 아닙니다. 대상 장비는 Raspberry Pi OS 64-bit입니다.' >&2
fi
for required in docker curl systemctl labwc; do
  if ! command -v "$required" >/dev/null 2>&1; then
    echo "필수 명령 없음: $required. README의 Pi 설치 절차를 확인하세요." >&2
    exit 1
  fi
done
docker compose version >/dev/null || { echo 'Docker Compose plugin을 설치하세요.' >&2; exit 1; }
if ! command -v chromium >/dev/null 2>&1 && ! command -v chromium-browser >/dev/null 2>&1; then
  echo 'sudo apt install chromium 명령으로 브라우저를 설치하세요.' >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo '.env를 생성했습니다. TIKTOK_USERNAME을 수정하거나 COMMENT_SOURCE=mock으로 바꾼 뒤 다시 실행하세요.'
  exit 0
fi
if grep -Eq '^COMMENT_SOURCE=tiktok[[:space:]]*$' .env && grep -Eq '^TIKTOK_USERNAME=@?example_account[[:space:]]*$' .env; then
  echo '.env의 예제 계정을 실제 TikTok 계정으로 수정하세요.' >&2
  exit 1
fi
sudo systemctl enable --now docker
if ! docker info >/dev/null 2>&1; then
  echo "Docker 권한이 없습니다. sudo usermod -aG docker $(id -un) 실행 후 로그아웃/로그인하세요. docker 그룹은 관리자 수준 권한을 가집니다." >&2
  exit 1
fi
docker compose build
docker compose up -d --wait --wait-timeout 120

AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/labwc"
AUTOSTART_FILE="$AUTOSTART_DIR/autostart"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/tiktok-live-monitor"
mkdir -p "$AUTOSTART_DIR" "$STATE_DIR"
if [[ ! -f "$AUTOSTART_FILE" ]] || ! grep -Fq '# tiktok-live-monitor kiosk' "$AUTOSTART_FILE"; then
  if [[ -f "$AUTOSTART_FILE" ]]; then
    cp -p "$AUTOSTART_FILE" "$AUTOSTART_FILE.backup.$(date +%Y%m%d%H%M%S)"
  elif [[ -f /etc/xdg/labwc/autostart ]]; then
    cp /etc/xdg/labwc/autostart "$AUTOSTART_FILE"
  fi
  # labwc reads shell commands. Single-quote arbitrary paths safely.
  quote() { local value="${1//\'/\'\\\'\'}"; printf "'%s'" "$value"; }
  {
    printf '\n# tiktok-live-monitor kiosk\n'
    printf '/bin/bash '
    quote "$PROJECT_ROOT/deploy/wait-for-app.sh"
    printf ' >>'
    quote "$STATE_DIR/kiosk.log"
    printf ' 2>&1 &\n'
  } >> "$AUTOSTART_FILE"
fi
echo '설치 완료. Desktop 자동 로그인과 디스플레이 90도 회전을 설정한 뒤 재부팅하세요.'
echo "kiosk 로그: $STATE_DIR/kiosk.log"
