#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == --help && $# == 1 ]]; then
  echo '사용법: ./scripts/build.sh'
  echo '소스에서 로컬 이미지를 빌드합니다. 실행하려면 ./scripts/start.sh --build를 사용하세요.'
  exit 0
fi
if (( $# != 0 )); then
  echo '지원하지 않는 인자입니다. ./scripts/build.sh --help를 확인하세요.' >&2
  exit 1
fi
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export MONITOR_IMAGE="${MONITOR_IMAGE:-tiktok-live-monitor:local}"
docker compose build
