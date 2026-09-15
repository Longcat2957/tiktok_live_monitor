# TikTok LIVE 세로형 댓글 모니터

Raspberry Pi 4 + Raspberry Pi OS Desktop 64-bit에서 실행하는 한 계정 전용 댓글 모니터입니다. 모든 일반 댓글을 받은 순서대로 표시하며, 최신 댓글 30개만 보관합니다. TikTok 연결 및 브라우저 연결은 자동으로 복구됩니다. 댓글 저장, 분류, 로그인, 외부 DB는 없습니다.

## 설치 가이드

- [개발 환경 설치](docs/installation-dev.md): 도구 설치, mock 개발 서버, 테스트와 빌드.
- [배포 환경 설치](docs/installation-deploy.md): Raspberry Pi, Docker Compose, Chromium kiosk와 운영.

## 바로 실행: mock 데모

Docker Engine과 Compose plugin이 있는 환경에서 저장소 루트로 이동합니다.

```bash
test -f .env || cp .env.example .env
# .env에서 COMMENT_SOURCE=mock으로 수정
docker compose up -d --build --wait
```

호스트 브라우저에서 `http://127.0.0.1:8000`을 엽니다. 기존 `.env`가 있다면 복사 단계를 생략하고 해당 파일을 수정하세요. 실제 방송 연결은 `.env`에서 `COMMENT_SOURCE=tiktok`, `TIKTOK_USERNAME=@방송계정`을 설정한 다음 `docker compose up -d`로 컨테이너를 재생성합니다. 환경변수 변경에는 `restart`만으로 충분하지 않습니다.

## 구성과 설정

`TikTokLive/mock → bounded asyncio.Queue → 연결별 전송 큐 → /ws → Svelte 정적 UI`로 동작합니다. 댓글 ID와 UTC 수신 시각은 서버가 생성합니다. 브라우저에 과거 댓글을 재전송하지 않으며, 연결이 끊긴 동안에는 이미 받은 댓글을 유지합니다.

| 설정 | 기본값 / 의미 |
| --- | --- |
| `COMMENT_SOURCE` | `tiktok` 또는 `mock` |
| `TIKTOK_USERNAME` | TikTok 모드에서 필수. `@`는 선택 사항, URL은 불가 |
| `COMMENT_QUEUE_SIZE` | `500`, 수신 큐 최대 크기 |
| `COMMENT_HISTORY_SIZE` | `30`, 브라우저 보관 수, 1–1000 |
| `TIKTOK_RECONNECT_MIN_SECONDS` | `2`, TikTok 재연결 초기 간격 |
| `TIKTOK_RECONNECT_MAX_SECONDS` | `30`, 재연결 최대 간격 |
| `MOCK_INTERVAL_SECONDS` | `1.5`, mock 댓글 간격(초) |
| `LOG_LEVEL` | `INFO`, DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `HOST`, `PORT` | `0.0.0.0`, `8000`. Compose에서는 이 값으로 고정 |
| `STATIC_DIR` | 기본 `frontend/build`; 컨테이너는 `/app/frontend/build` |

설정 오류는 시작 시 Pydantic 검증 오류로 표시됩니다. `.env`는 Git 및 Docker build context에서 제외됩니다. 댓글 보관 수는 `/config`에서 전달하므로 UI 재빌드 없이 바꿀 수 있습니다.

수신 큐가 꽉 차면 가장 오래된 댓글을 버리고 경고합니다. 브라우저별 큐는 100개이며 전송이 5초 이상 지연되거나 큐가 가득 차면 해당 연결만 종료합니다. 정상 수신 시 필터 없이 표시하지만, 이 과부하 상황 또는 네트워크 단절 동안의 전달까지 보장하지는 않습니다. 빈 댓글과 변환 불가능한 이벤트만 건너뜁니다.

`/health`는 프로세스 작업 상태, source 상태, WebSocket 연결 수, 큐 사용량을 반환합니다. 방송 대기는 정상 상태이므로 컨테이너는 healthy입니다. 내부 장기 실행 task가 종료되면 `status=error`로 표시하며 Compose healthcheck가 실패합니다. Docker restart policy는 **프로세스 종료**를 복구하고, unhealthy 상태만으로 컨테이너를 재시작하지는 않습니다.

## 개발

Linux 데스크톱에서 개발 도구와 Chromium을 설치한 뒤 아래 한 명령으로 백엔드, 프론트엔드, Chromium을 함께 실행할 수 있습니다.

```bash
./scripts/dev.sh
```

의존성 설치 후 mock 모드로 `http://127.0.0.1:5173`을 자동으로 엽니다. 종료는 `Ctrl+C`입니다. 브라우저 없이 실행하려면 `DEV_OPEN_BROWSER=0 ./scripts/dev.sh`를 사용하세요. 실제 방송 연결과 옵션은 [개발 서버 실행 가이드](docs/installation-dev.md#4-개발-서버-실행)를 참고하세요.

Python 3.11 이상, uv, Node.js 22.20 이상(22 계열 권장), pnpm 10.20.0이 필요합니다. 버전은 `backend/uv.lock`, `frontend/pnpm-lock.yaml`로 고정합니다. 주요 검증 버전: TikTokLive 7.0.1, FastAPI 0.141.1, Svelte 5.57.0, SvelteKit 2.70.3, TypeScript 6.0.3. TypeScript 7은 현재 SvelteKit peer 지원 범위 밖이라 사용하지 않습니다.

도구가 없다면 먼저 [개발 도구 설치](docs/installation-dev.md#1-개발-도구-설치)를 진행하세요. 아래 명령은 도구 설치 후 저장소 루트에서 시작합니다.

```bash
cd backend
uv sync --frozen
COMMENT_SOURCE=mock uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

별도 터미널:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Vite 개발 URL을 엽니다. `/ws`, `/health`, `/config`는 백엔드로 proxy되며 `BACKEND_URL`로 대상을 변경할 수 있습니다. 운영에서는 `window.location`으로 ws/wss를 선택합니다. CORS wildcard는 사용하지 않습니다.

## 검사와 프로덕션 빌드

```bash
cd backend
uv run pytest
uv run mypy
uv run ruff check app tests
cd ../frontend
pnpm check
pnpm test
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
```

E2E는 정적 빌드가 필요하며 `backend/.venv/bin/python`으로 mock 서버를 `127.0.0.1:18765`에 실행하고 종료합니다. 해당 포트는 비워두세요. 기존 Chromium을 쓰려면 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`를 지정합니다. Linux 브라우저 의존성이 부족하면 Playwright 공식 설치 안내에 따라 `pnpm exec playwright install --with-deps chromium`을 실행합니다.

백엔드 테스트는 health/static route, WebSocket 상태·댓글·disconnect, 큐 drop, 느린 연결 격리, TikTok 이벤트 변환·대기·취소 정리를 확인합니다. 프론트엔드 테스트는 메시지 검증, 10,000개 입력 후 보관 수, 재연결 backoff와 unmount 정리를 확인합니다. E2E는 1080×1920 및 720×1280의 줄바꿈·상태 영역, HTML의 텍스트 표시, 서버 재시작 후 댓글 유지·재연결, 1,000개 burst 수신 순서를 확인합니다.

로컬 정적 빌드를 FastAPI에서 확인하려면 `pnpm build` 이후 백엔드를 시작하고 `http://127.0.0.1:8000`을 엽니다. 빌드 폴더를 새로 만든 경우 백엔드를 재시작하세요.

저장소 루트에서 운영 이미지 빌드:

```bash
./scripts/build.sh
docker compose up -d --wait
```

Node 빌드 단계와 Python 의존성 단계를 분리하며 최종 이미지에는 백엔드, production 가상환경, 정적 UI만 들어갑니다. 비root UID 10001, 읽기 전용 루트, `/tmp` tmpfs, localhost 포트만 사용합니다. Node, pnpm, uv 및 개발 의존성은 최종 이미지에 복사하지 않습니다. Python slim 베이스가 제공하는 pip는 남아 있지만 런타임 패키지 설치에는 사용하지 않습니다.

## GitHub Actions CI

`main` 푸시 및 `main` 대상 PR에서 [CI](https://github.com/Longcat2957/tiktok_live_monitor/actions/workflows/ci.yml)가 실행됩니다.
백엔드 pytest/mypy와 프론트엔드 check/test/build를 한 작업에서 검사합니다. TikTok 인증 없이 mock 모드를 사용합니다.
uv/pnpm 의존성을 lockfile 기준으로 설치하고 다운로드 캐시를 재사용합니다. 같은 브랜치 또는 PR의 새 실행은 이전 실행을 취소하며, 작업 제한 시간은 10분입니다.

현재 자동화 범위는 CI입니다. 이미지 게시와 장비 자동 배포는 없으며, 배포는 기존 `scripts/install.sh`와 `scripts/update.sh`를 사용합니다.

## 새 Raspberry Pi 설치

[배포 환경 설치 가이드](docs/installation-deploy.md)에 OS 준비, Docker 설치, mock 검증, Chromium 자동 실행과 업데이트 절차를 정리했습니다.

## 운영 명령

모든 Compose 명령은 `~/tiktok_live_monitor`에서 실행합니다.

```bash
docker compose ps
docker compose logs -f app
docker compose restart app
docker compose up -d --build
curl http://127.0.0.1:8000/health
tail -f ~/.local/state/tiktok-live-monitor/kiosk.log
```

소스를 업데이트한 다음 `./scripts/update.sh`로 재빌드하고 교체합니다. 이 스크립트는 사용자 파일을 보존하기 위해 Git fetch/pull을 수행하지 않습니다. 별도의 앱 systemd unit은 필요하지 않습니다. `docker compose stop`으로 수동 중지하면 unless-stopped 정책상 다음 부팅에도 중지 상태가 유지되므로 `docker compose up -d`로 다시 시작합니다.

## 장애 진단

| 증상 | 확인할 내용 |
| --- | --- |
| 방송 시작 대기 | `waiting`은 정상입니다. 지정 계정에서 LIVE를 시작하면 자동 재연결합니다. |
| TikTok 연결 오류 | 인터넷/DNS, 계정 아이디, 방송 공개 여부를 확인합니다. `docker compose logs --tail=100 app`의 오류 종류를 확인합니다. 비공식 API 또는 서명 서비스 변경이면 TikTokLive 공식 저장소 이슈를 확인하고 adapter 테스트와 lockfile을 함께 갱신합니다. |
| 계정을 찾지 못함 | `.env`에 프로필 URL이나 표시 이름 대신 unique ID를 지정합니다. 설정 변경 후 `docker compose up -d`를 실행합니다. |
| 인터넷 없음 | Pi 네트워크 설정, `ip route`, `getent hosts www.tiktok.com`을 확인합니다. mock 모드로 로컬 UI를 분리해 진단합니다. |
| Chromium 미실행 | `command -v chromium chromium-browser`, kiosk 로그, Desktop 자동 로그인과 labwc 세션, `~/.config/labwc/autostart` 경로를 확인합니다. |
| 화면이 가로 | OS 디스플레이 회전과 저장 여부를 확인합니다. CSS를 회전시키지 않습니다. |
| UI 404 / build 없음 | 로컬은 `cd frontend && pnpm build` 후 백엔드 재시작. 운영은 `docker compose up -d --build`를 사용합니다. |
| Docker/Compose 없음 | `docker version`, `docker compose version`, `systemctl status docker` 확인 후 공식 설치 절차를 적용합니다. |
| ARM64 빌드 실패 | `uname -m`이 `aarch64`, `dpkg --print-architecture`가 `arm64`인지 확인합니다. 32-bit OS는 대상이 아닙니다. 디스크·RAM·네트워크와 최초 실패 레이어를 확인합니다. x86에서 교차 빌드하려면 별도 ARM builder 또는 QEMU가 필요합니다. |
| unhealthy / 재시작 반복 | `docker compose logs --tail=100 app`, `docker inspect --format '{{json .State.Health}}' "$(docker compose ps -q app)"`로 설정 오류, 포트, 메모리 부족을 확인합니다. TikTok 오프라인 자체는 health 실패가 아닙니다. |
| 댓글 일부 누락 | queue full / slow WebSocket 경고 확인. 처리량을 낮추거나 큐 크기를 조정합니다. 저장·재전송은 하지 않습니다. |

## 외부 의존성과 인수 확인

TikTokLive는 TikTok 공식 API가 아닙니다. 비공식 웹 수신 및 외부 서명 서비스의 변경·제한 때문에 실제 LIVE 연결은 보장할 수 없습니다. 암호, 쿠키, 세션 토큰은 수집하거나 설정하지 않습니다. 추가 인증이 필요한 방송은 현재 구현 범위 밖입니다. 설치한 7.0.1의 `connect()`/`close()`는 내부에서 이벤트 루프 종료 처리를 호출하므로, adapter는 공개 `start()` + `disconnect()` + `web.close()`로 FastAPI 루프와 분리해 정리합니다. [TikTokLive 공식 저장소](https://github.com/isaackogan/TikTokLive)를 기준으로 갱신해야 합니다.

정적 페이지는 [SvelteKit adapter-static](https://svelte.dev/docs/kit/adapter-static), 백엔드 생명주기는 [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)을 사용합니다.

실제 Pi에서 다음 항목을 확인하세요. 개발 PC의 자동 테스트가 하드웨어 검증을 대체하지는 않습니다.

- 전원 재인가 후 Docker와 kiosk 자동 실행, 출력 회전과 화면 절전 해제.
- 실제 LIVE에서 닉네임·아이디 fallback·본문과 댓글 수신 순서.
- mock 모드 수 시간 실행 후 DOM의 `.comment` 수가 설정값 이하이며 메모리가 지속 증가하지 않는지 확인.
- 인터넷 및 컨테이너 재시작 후 새로고침 없이 수신 복구.
