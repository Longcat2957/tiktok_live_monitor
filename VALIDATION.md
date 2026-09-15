# 검증 결과 — 2026-09-13

실행 환경: Linux x86_64, Python 3.11.14 (Docker 3.11.16), Node 22.20.0, pnpm 10.20.0, Docker 29.7.2 / Compose 2.32.4.

| 검증 | 결과 |
| --- | --- |
| `cd backend && uv run pytest -q` | 18 passed |
| `uv run mypy` | 10개 소스 파일, 오류 없음 |
| `uv run ruff check app tests` | 통과 |
| `uv lock --check` | 통과 |
| `cd frontend && pnpm check` | 오류 0, 경고 0 |
| `pnpm test` | 13 passed |
| `pnpm build` | adapter-static이 `frontend/build` 생성 |
| `pnpm test:e2e` (기존 Chromium 경로 지정) | 4 passed |
| `bash -n` 배포·설치·빌드·업데이트 스크립트 | 통과 |
| `docker build -t tiktok-live-monitor:local .` | 성공 |
| `docker compose -p tiktok-live-monitor-check up -d --build --wait` | 최종 수정본 이미지 빌드 및 healthy 확인 |
| 실행 컨테이너 검사 | UID 10001, read-only, unless-stopped, 127.0.0.1:8000, Node/pnpm/uv 미포함 |
| 컨테이너 `/health`, `/` | 정상 JSON 및 정적 UI 제공 |
| Compose restart 후 `/ws` | 상태 메시지 및 mock 댓글 수신 확인 |
| Node/Python/uv 베이스 이미지 manifest | 세 이미지 모두 ARM64 변형 존재 |

E2E에서 1080×1920 및 720×1280 화면 넘침·footer 겹침 없음, HTML 텍스트 처리, 댓글 DOM 30개 제한, 백엔드 재시작 후 페이지 새로고침 없이 재연결 및 기존 댓글 유지, 잘못된 메시지 무시, 1,000개 burst 수신 순서를 확인했습니다. 화면 캡처는 로컬 `frontend/test-results/monitor-1080.png`, `monitor-720.png`에 있으며 Git에는 포함하지 않습니다.

백엔드 테스트에는 Starlette/AnyIO 및 TikTokLive의 websockets legacy 사용에 관한 외부 패키지 deprecation warning 4개가 있습니다. 테스트 실패나 종료 task 경고는 없습니다. 초기 제한된 샌드박스에서는 TestClient의 스레드 통신이 멈춰, 일반 실행 권한으로 재실행한 결과 위 테스트가 통과했습니다.

검증용 Compose 프로젝트는 테스트 후 `down`으로 정리했습니다. 소스와 빌드 이미지는 유지됩니다. 로컬 `.env`는 mock 데모로 설정되어 있으며 `.gitignore` 대상입니다. `docker compose up -d --build`로 다시 실행할 수 있습니다.

## 아직 검증하지 못한 항목

- ARM64 이미지의 실제 빌드·실행: 현재 Docker builder는 x86만 지원하며 Pi/QEMU가 없습니다. 베이스 이미지의 ARM64 제공 여부만 확인했습니다.
- Pi 전원 재인가 후 Desktop 로그인, 화면 회전, labwc Chromium 자동 실행. 스크립트 구문 검사와 설정 구현만 완료했습니다.
- 실제 TikTok LIVE 수신: 방송 계정과 진행 중인 LIVE가 제공되지 않았습니다. 설치된 TikTokLive 7.0.1 실제 이벤트 타입과 모의 연결 수명주기는 테스트했습니다.
- 수 시간 동안의 실제 브라우저 메모리 추이: 10,000개 입력의 보관 제한 및 짧은 브라우저 부하 검증까지만 수행했습니다.

Pi 설치와 현장 인수 절차는 README.md에 있습니다.
