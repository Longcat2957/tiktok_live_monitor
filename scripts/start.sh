#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == --help && $# == 1 ]]; then
  echo '사용법: ./scripts/start.sh [--build]'
  echo '기본: Docker Hub 이미지를 받아 앱을 시작합니다.'
  echo '--build: 소스에서 로컬 이미지를 빌드해 시작합니다.'
  exit 0
fi
if (( $# > 1 )) || { (( $# == 1 )) && [[ "$1" != --build ]]; }; then
  echo '지원하지 않는 인자입니다. ./scripts/start.sh --help를 확인하세요.' >&2
  exit 1
fi

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

command -v docker >/dev/null || { echo 'Docker가 필요합니다.' >&2; exit 1; }
docker compose version >/dev/null || { echo 'Docker Compose plugin이 필요합니다.' >&2; exit 1; }
docker info >/dev/null || { echo 'Docker daemon 또는 현재 사용자의 권한을 확인하세요.' >&2; exit 1; }

if [[ ! -e .env ]]; then
  cp .env.example .env
  echo '.env를 기본값으로 생성했습니다. 필요한 설정은 이 파일에서 수정하세요.'
elif [[ ! -f .env ]]; then
  echo '.env가 일반 파일이 아닙니다.' >&2
  exit 1
fi

if [[ "${1:-}" == --build ]]; then
  export MONITOR_IMAGE="${MONITOR_IMAGE:-tiktok-live-monitor:local}"
fi
docker compose config --quiet

if [[ "${1:-}" == --build ]]; then
  ./scripts/build.sh
else
  docker compose pull app
fi
docker compose up -d --no-build --pull never --wait --wait-timeout 120
