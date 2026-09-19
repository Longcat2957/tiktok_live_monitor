#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

# Load the whole operation before pull can replace this script on disk.
main() {
  if [[ "${1:-}" == --help && $# == 1 ]]; then
    echo '사용법: ./scripts/update.sh'
    echo '현재 브랜치의 upstream에서 fast-forward 업데이트 후 Docker 빌드·교체·healthy 확인.'
    echo '미커밋 변경이 있으면 중단합니다. .env는 보존합니다. 방송이 끝난 뒤 실행하세요.'
    return
  fi
  if (( $# != 0 )); then
    echo '지원하지 않는 인자입니다. ./scripts/update.sh --help를 확인하세요.' >&2
    return 1
  fi
  cd "$PROJECT_ROOT"
  for tool in git docker; do
    command -v "$tool" >/dev/null || { echo "필수 명령 없음: $tool" >&2; return 1; }
  done
  if [[ ! -f .env ]]; then
    echo '.env가 없습니다. 먼저 ./scripts/install.sh로 설치하세요.' >&2
    return 1
  fi
  if [[ -n "$(git status --porcelain)" ]]; then
    echo '미커밋 변경 또는 추적하지 않는 파일이 있습니다. 먼저 커밋하거나 별도로 보관하세요.' >&2
    return 1
  fi
  if ! git rev-parse --verify '@{upstream}' >/dev/null 2>&1; then
    echo '현재 브랜치에 upstream이 없습니다. 원격 추적 브랜치를 설정하세요.' >&2
    return 1
  fi
  docker compose version >/dev/null
  docker info >/dev/null
  local previous
  previous="$(git rev-parse --short HEAD)"
  git pull --ff-only
  echo "배포: $previous → $(git rev-parse --short HEAD)"
  ./scripts/build.sh
  if ! docker compose up -d --wait --wait-timeout 120; then
    echo '배포 상태 확인 실패. 자동 롤백하지 않습니다. docker compose logs --tail=100 app으로 확인하세요.' >&2
    return 1
  fi
  echo '업데이트 완료. 컨테이너가 교체되었다면 화면에서 방송·데모를 선택하고 다시 시작하세요.'
}

main "$@"
