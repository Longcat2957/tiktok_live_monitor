#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

# Load the whole operation before pull can replace this script on disk.
main() {
  if [[ "${1:-}" == --help && $# == 1 ]]; then
    echo '사용법: ./scripts/update.sh'
    echo '현재 브랜치의 upstream에서 fast-forward 업데이트 후 Docker 빌드·교체·healthy 확인.'
    echo '성공 후 이 앱의 태그 없는 미사용 이미지를 정리하고 Docker 디스크 사용량을 표시합니다.'
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
  local previous previous_image current_image
  previous="$(git rev-parse --short HEAD)"
  git pull --ff-only
  echo "배포: $previous → $(git rev-parse --short HEAD)"
  previous_image="$(docker compose images -q app)"
  ./scripts/build.sh
  if ! docker compose up -d --wait --wait-timeout 120; then
    echo '배포 상태 확인 실패. 자동 롤백하지 않습니다. docker compose logs --tail=100 app으로 확인하세요.' >&2
    return 1
  fi
  # Also handle the previously deployed image from before we added the image label.
  current_image="$(docker compose images -q app)" || current_image=""
  if [[ -n "$previous_image" && -n "$current_image" && "$previous_image" != "$current_image" ]]; then
    if [[ "$(docker image inspect --format '{{len .RepoTags}}' "$previous_image")" == 0 ]]; then
      docker image rm "$previous_image" || echo '이전 이미지 정리 실패. 사용 중인 이미지는 유지합니다.' >&2
    fi
  fi
  # No --all: preserve tagged images and every image referenced by a container.
  docker image prune --force --filter label=org.opencontainers.image.title=tiktok-live-monitor || \
    echo '앱 이미지 정리 실패. 배포는 완료되었지만 디스크 사용량을 확인하세요.' >&2
  # Build cache is shared with other projects; report it without a global prune.
  docker system df || echo 'Docker 디스크 사용량을 조회하지 못했습니다.' >&2
  echo '업데이트 완료. 컨테이너가 교체되었다면 화면에서 방송·데모를 선택하고 다시 시작하세요.'
}

main "$@"
