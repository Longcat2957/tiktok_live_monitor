# TikTok LIVE 세로형 댓글 모니터

Raspberry Pi 4 + Raspberry Pi OS Desktop 64-bit에서 실행하는 한 계정 전용 댓글 모니터입니다. 모든 일반 댓글을 받은 순서대로 표시하며, 기본적으로 최신 댓글·활동 알림 30개만 보관합니다. TikTok 연결 및 브라우저 연결은 자동으로 복구됩니다. 댓글 저장, 분류, 로그인, 외부 DB는 없습니다.

## 설치 가이드

- [개발 환경 설치](docs/installation-dev.md): 도구 설치, 자동 reload 개발 서버, 테스트와 빌드.
- [배포 환경 설치](docs/installation-deploy.md): Raspberry Pi, Docker Compose, Chromium kiosk와 운영.

## 실행 방식과 방송 선택

앱은 하나이며 별도의 데모 서버·실방송 서버는 없습니다. **개발·운영은 실행 방식**, **실제 방송·데모는 화면에서 선택하는 데이터 입력**입니다.

| 구분 | 선택 | 차이 |
| --- | --- | --- |
| 실행 방식 | 개발: `./scripts/dev.sh` | Python 자동 reload + Vite, 브라우저 접속은 5173 |
| 실행 방식 | 운영: Docker Compose | 빌드된 UI + FastAPI 단일 컨테이너, 접속은 8000 |
| 방송 선택 | 실제 방송 | 입력한 계정의 TikTok LIVE 수신 |
| 방송 선택 | 데모 체험 | 외부 연결 없이 가짜 댓글·활동 생성 |

어느 실행 방식에서도 두 방송 선택을 모두 사용할 수 있습니다. 서버는 항상 대기 상태로 시작하며 첫 화면에는 **실제 방송**이 선택되어 있습니다. 데모는 **데모 체험 → 시작**으로 실행합니다. 모드 변경은 **모니터 종료 · 처음으로**에서 하며, 재빌드나 `.env` 변경은 필요하지 않습니다.

`.env`는 큐 크기·보관 수·재연결 간격 같은 서버 시작 설정만 담습니다. 기존 `COMMENT_SOURCE`는 제거되었으며 남아 있어도 무시됩니다. 기존 `.env`에서 해당 줄을 삭제하세요. 서버 재시작 후에는 모드·계정을 다시 선택하고 시작해야 합니다.

## Docker로 실행

Docker Engine과 Compose plugin이 있는 환경에서 저장소 루트로 이동합니다.

```bash
test -f .env || cp .env.example .env
docker compose up -d --build --wait
```

호스트 브라우저에서 `http://127.0.0.1:8000`을 열고 **데모 체험 → 시작**을 누릅니다. 기존 `.env`가 있다면 복사 단계를 생략하세요. 실제 방송은 **모니터 종료 · 처음으로 → 실제 방송**을 선택하고 계정을 입력한 뒤 시작합니다.

### LIVE 정보 데모

첫 화면에서 **데모 체험 → 시작**을 선택하면 다음 항목을 모두 확인할 수 있습니다.

- 댓글: 로컬 프로필 이미지, 사진 없는 작성자의 기본 표시, 구독자·팬 배지와 레벨.
- 상단: 방송 아이디·시청자 수·좋아요 수. 푸터 왼쪽에는 방송 중·일시정지·종료, 오른쪽에는 서버 연결 상태를 표시합니다.
- 목록: 선물(장미 × 5), 팔로우, 공유, 구독 알림. 댓글과 알림을 합쳐 설정된 보관 수까지만 유지합니다.
- 24단계 순환: 12단계 방송 → 2단계 일시정지 → 6단계 방송 → 2단계 종료 → 2단계 새 방송. 정지·종료 구간에는 댓글이 나오지 않습니다.

기본 간격 1.5초에서는 한 주기가 약 36초입니다. **모니터 설정 → 데모 댓글 간격**을 0.5초로 바꾸면 약 12초 안에 모두 확인할 수 있습니다. 데모 이미지는 앱에 포함되어 인터넷이나 TikTok 인증이 필요 없습니다.

실방송은 제공되는 필드만 표시하며, 수신 전 통계는 `—`로 표시합니다. 연결이 끊기면 마지막 통계를 흐리게 표시합니다. 배지는 TikTokLive 7.0.1의 실제 v3 필드에서 읽으며, 레벨 누락 시 배지 이름만 표시합니다. 선물 연속 전송은 마지막 수량만 표시하고 금액으로 환산하지 않습니다. 새로고침은 댓글·활동·통계를 초기화하고 현재 계정에 다시 연결합니다.

## 방송 계정 선택

모든 모드에서 시작 버튼을 누르기 전까지 백엔드가 정상 대기(`idle`)합니다. 첫 화면에서 실제 TikTok 방송 또는 mock 데모를 선택합니다. Pi의 키보드·마우스 또는 터치 입력을 사용해 `@아이디`, `https://www.tiktok.com/@아이디`, `https://www.tiktok.com/@아이디/live`를 입력하고 **시작**을 누릅니다. 방송 전이라면 자동으로 방송 시작을 기다립니다. 주소는 아이디 추출에만 사용하며 단축 링크는 지원하지 않습니다.

**모니터 설정**은 댓글 화면 위에 모달로 열립니다. 현재 모드에 맞춰 실제 방송 설정 또는 데모 설정을 표시합니다. 기본 항목은 **목록 보관 수**(댓글과 활동 알림의 합계)이며 데모에서는 생성 간격도 바로 조절합니다. **고급 설정**을 펼치면 수신 대기 큐 크기와 로그 수준을, 실제 방송에서는 재연결 최소·최대 간격도 조절할 수 있습니다. 모드·계정은 모니터를 종료한 뒤 첫 화면에서 변경합니다. 취소는 변경을 버리고, 적용은 이전 연결을 종료하고 모든 연결 화면의 댓글을 비운 뒤 새 설정으로 시작합니다. 선택 계정은 메모리에만 보관하므로 새로고침에는 유지되고 백엔드 재시작 후에는 다시 입력합니다. 기존 `TIKTOK_USERNAME` 환경변수는 사용하지 않습니다. mock 데모는 계정 입력 없이 시작 버튼으로 실행합니다.

댓글 화면 오른쪽 위의 +/− 버튼은 댓글 본문과 닉네임 크기를 20~200% 범위에서 누를 때마다 5%씩 조정합니다. 기본 크기는 100%이며 버튼 사이에 현재 배율을 표시합니다. 선택은 현재 브라우저에 저장되어 새로고침·재접속 후에도 유지됩니다. 잘못된 저장값은 100%로 복원합니다. 조절 아이콘은 **모니터 설정**, 원형 화살표 아이콘은 **댓글 비우기 · 다시 연결**, 문 밖으로 나가는 화살표 아이콘은 **모니터 종료 · 처음으로**입니다. 마우스를 올리거나 키보드로 포커스하면 설명이 표시됩니다. 새로고침은 현재 실행 중인 모드·계정을 유지한 채 기존 댓글을 비우고 연결을 다시 시작합니다. 실제 방송의 접속 초기 이벤트는 건너뛰며, 데모는 생성 순번을 이어갑니다. 데모 샘플 문구는 반복되지만 각 새 댓글에 고유한 데모 순번을 표시합니다. 초기화는 수신을 중지하고 모든 연결 화면의 댓글과 선택 계정을 비운 뒤 첫 화면으로 돌아갑니다. 첫 화면에는 실제 방송이 선택됩니다. 시작 버튼을 누르기 전까지 방송에 연결하지 않습니다.

## 세션 API와 장애 처리

모든 변경 요청은 현재 `session_id`를 JSON 본문에 포함합니다. 이 값은 `GET /config` 또는 WebSocket 상태 메시지에서 얻습니다. 성공한 변경은 새 세션 ID를 반환하며 기존 댓글을 비웁니다.

| API | 요청 본문 | 동작 |
| --- | --- | --- |
| POST /account | `{session_id, source, username?}` | 대기 상태에서만 시작 |
| POST /refresh | `{session_id}` | 현재 모드·계정을 유지하고 재연결 |
| PATCH /config | `{session_id, settings: {변경할 필드: 값}}` | 현재 모드의 설정만 부분 변경 |
| DELETE /account | `{session_id}` | 종료 후 첫 화면으로 복귀 |

브라우저의 변경 요청은 15초, 설정·상태 조회는 5초의 응답 제한 시간을 사용합니다. 응답이 끊기면 변경 요청을 재전송하지 않고 `/health`의 세션 및 `pending_commands`를 확인합니다. 서버가 처리 중이면 변경 조작을 막고 3초 간격으로 다시 확인하며, 설정창은 확인 요청의 제한 시간이 지나면 닫을 수 있습니다. HTTP 조회는 댓글 목록을 직접 바꾸지 않고 WebSocket의 세션 경계를 따릅니다.

오래된 세션 요청은 409, 잘못된 값은 422, 종료 실패나 서버 종료 중 요청은 503입니다. 설정창을 열어 둔 사이 다른 화면에서 종료하거나 설정을 바꾸면 이전 설정창은 적용할 수 없습니다. 클라이언트 연결이 끊겨도 이미 수락한 전환은 완료하므로 재접속 후 현재 세션을 다시 조회합니다.

로컬 Host(`localhost`, `127.0.0.1`, `::1`)만 허용합니다. 브라우저의 변경 요청과 WebSocket은 같은 출처만 허용하며 WS는 Origin 헤더가 필수입니다. localhost 배포를 전제로 하며 외부 네트워크용 인증 서비스는 아닙니다. 실행은 **한 프로세스/한 worker**로 유지해야 합니다.

구현 요구사항은 [명세서](TIKTOK_LIVE_MONITOR_SPEC.md), 완료된 작업의 검증 결과는 [검증 기록](VALIDATION.md)을 참고하세요.

## UI 디자인

최신 댓글을 자동으로 따라가다가 위로 스크롤하면 읽던 위치를 유지합니다. **최신 댓글로**를 누르거나 목록에서 End 키를 누르면 다시 최신 항목을 따라갑니다. 방향키와 Page Up/Down으로도 읽을 수 있습니다. 읽는 중 새 항목 수는 현재 보관 범위 내에서 표시하며, 읽던 항목이 보관 수를 벗어나 삭제되면 안내합니다. 설정 적용·재연결로 새 세션이 시작되면 자동 따라가기로 돌아갑니다.

선물·팔로우·공유·구독은 댓글보다 작은 1–2줄 알림으로 표시합니다. 잘못된 사진 주소나 배지는 제외하고 정상 댓글은 유지합니다. 스크린 리더에는 전체 댓글을 계속 낭독하는 대신 초당 한 번 새 항목 수를 요약합니다.

댓글이 없을 때는 서버 연결 확인·방송 연결·방송 시작 대기·댓글 대기·일시정지·종료·오류에 맞는 안내를 표시합니다. 기존 댓글이 있으면 목록을 유지하고 푸터 상태를 갱신합니다.

첫 화면과 댓글 화면의 상단 해·달 아이콘으로 라이트/다크 테마를 전환합니다. 기본은 다크이며 선택은 브라우저에 저장됩니다. 테마 변경은 수신 연결이나 댓글 목록에 영향을 주지 않습니다.

입력창과 버튼은 [m3-svelte](https://github.com/KTibow/m3-svelte) 7.2.0의 `TextFieldOutlined`, `Button`, `ConnectedButtons`를 사용합니다. `frontend/src/app.css`의 `--m3c-*` 색상으로 검정 배경·핑크레드 주요 동작·시안 선택 상태를 통일합니다. 한글 폰트는 호스트의 Noto Sans 계열을 사용하며 외부 폰트 요청은 없습니다.

필수 CSS 변환 플러그인 `vite-plugin-functions-mixins` 0.4.1은 Vite 7 peer 범위를 선언하므로 현재 Vite 8.3.0 설치 시 경고가 있습니다. 현재 조합의 타입 검사·개발 서버·정적 빌드·브라우저 E2E를 검증하며, 업데이트 시 이 호환성을 다시 확인해야 합니다. CSS의 `@function` 정의를 수정한 경우 기존 컴포넌트의 변환 결과를 갱신하도록 개발 서버를 재시작하세요.

## 구성과 설정

`TikTokLive/mock → bounded asyncio.Queue → 연결별 전송 큐 → /ws → Svelte 정적 UI`로 동작합니다. 댓글 ID와 UTC 수신 시각은 서버가 생성합니다. 브라우저에 과거 댓글을 재전송하지 않으며, 연결이 끊긴 동안에는 이미 받은 댓글을 유지합니다.

| 설정 | 기본값 / 의미 |
| --- | --- |
| `COMMENT_QUEUE_SIZE` | `500`, 수신 큐 최대 크기 (1–10,000) |
| `COMMENT_HISTORY_SIZE` | `30`, 브라우저 댓글·활동 보관 수, 1–1000 |
| `TIKTOK_RECONNECT_MIN_SECONDS` | `2`, TikTok 재연결 초기 간격 |
| `TIKTOK_RECONNECT_MAX_SECONDS` | `30`, 재연결 최대 간격 |
| `MOCK_INTERVAL_SECONDS` | `1.5`, mock 댓글 간격(초) |
| `LOG_LEVEL` | `INFO`, DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `HOST`, `PORT` | `0.0.0.0`, `8000`. Compose에서는 이 값으로 고정 |
| `STATIC_DIR` | 기본 `frontend/build`; 컨테이너는 `/app/frontend/build` |

설정 오류는 시작 시 Pydantic 검증 오류로 표시됩니다. `.env`는 Git 및 Docker build context에서 제외됩니다. 현재 편집 가능한 설정은 `/config`에서 조회합니다. 목록 보관 수는 WebSocket 상태 메시지에 포함해 모든 브라우저에 동기화합니다. 모달 변경은 메모리에만 반영하며 `.env`를 쓰지 않습니다. 새로고침·모니터 종료에도 숫자 설정은 유지되고, 백엔드 재시작 시 `.env` 초기값으로 돌아갑니다. `HOST`, `PORT`, `STATIC_DIR`은 런타임 변경 대상이 아닙니다.

수신 큐가 꽉 차면 가장 오래된 댓글·활동 이벤트를 버리고 누락 수를 집계합니다. 기존 `dropped_comments` 카운터에는 활동 알림 누락도 포함됩니다. 과부하 로그는 누적 수가 1, 2, 4, 8…일 때만 출력합니다. 브라우저별 큐는 100개이며 전송이 5초 이상 지연되거나 큐가 가득 차면 해당 연결만 종료합니다. 정상 수신 시 필터 없이 표시하지만, 이 과부하 상황 또는 네트워크 단절 동안의 전달까지 보장하지는 않습니다. 빈 댓글, 변환 불가능한 이벤트, 본문 10,000자 또는 이름·아이디 256자를 초과한 이벤트는 건너뜁니다. 브라우저 연결은 최대 16개입니다.

`/health`는 프로세스 작업 상태, source 상태, WebSocket 연결 수, 큐 사용량을 반환합니다. 방송 대기는 정상 상태이므로 컨테이너는 healthy입니다. 수신·소비 작업이 비정상 종료되면 HTTP 503/`status=error`와 화면 오류로 알리고 제한된 지수 간격으로 자동 복구합니다. `fault`, `recoveries`, `dropped_comments`, `slow_disconnects`로 장애와 과부하를 진단합니다. 외부 라이브러리가 종료를 거부하면 새 연결을 차단하고 `shutdown_timeout`을 표시합니다. 이때 `docker compose restart app`으로 재시작합니다. Docker restart policy는 **프로세스 종료**를 복구하고, unhealthy 상태만으로 컨테이너를 재시작하지는 않습니다.

## 백엔드 코드 구조

| 경로 (`backend/app/`) | 책임 |
| --- | --- |
| `main.py`, `__main__.py` | 앱 조립·lifespan과 서버 실행 |
| `api/routers/` | 모니터 동작·설정·상태 HTTP API와 WebSocket 접속 |
| `api/dependencies.py`, `security.py`, `exception_handlers.py` | 서비스 주입·로컬 출처 검사·오류 응답 |
| `schemas/` | API 요청·응답과 댓글·활동·방송 상태 계약 |
| `services/monitor.py` | `MonitorService`: 세션 전환·작업 종료·복구, 상태·설정 조회 |
| `services/demo.py`, `event_sink.py` | 데모 생성과 세션별 수신 이벤트 전달 |
| `integrations/tiktok.py` | `TikTokStream`: TikTokLive 연결·이벤트 변환·재연결 |
| `realtime/broadcaster.py` | `WebSocketBroadcaster`: 연결별 송신 큐·느린 브라우저 격리 |

라우터는 공통 `get_monitor` 의존성으로 서비스 인스턴스를 받습니다. 시작·종료·재연결·설정 변경은 서비스의 공개 메서드로 요청하며, 내부 잠금과 작업 정리 경로는 공유합니다. `/health`와 `/config`는 명시적인 응답 모델을 반환합니다. 새 API는 `api/routers/`, 외부 이벤트 변환은 `integrations/tiktok.py`, 세션 전환 규칙은 `services/monitor.py`에서 수정합니다. 테스트도 `backend/tests/` 아래 같은 책임별로 구분합니다.

## 프론트엔드 코드 구조

| 경로 (`frontend/src/`) | 책임 |
| --- | --- |
| `routes/+page.svelte` | 화면 조립, 설정창 열림·글자 배율, 시작·종료 후 포커스 전환 |
| `lib/components/MonitorHeader.svelte` | 제목과 테마·배율·설정·재연결·종료 도구 |
| `lib/components/AccountSetup.svelte` | 모드·계정 입력 초안과 시작 요청 오류 |
| `lib/components/LiveSummary.svelte`, `RequestFeedback.svelte` | 방송 통계와 요청 복구 안내 |
| `lib/components/CommentList.svelte`, `CommentItem.svelte` | 댓글·활동 표시와 읽기 위치 유지 |
| `lib/components/SettingsDialog.svelte` | 설정 초안·검증·적용 |
| `lib/monitor/session.svelte.ts` | WebSocket 연결, 세션 경계, 보관 상한과 프레임별 목록 반영 |
| `lib/monitor/commands.svelte.ts` | 시작·종료·재연결·설정 변경, 불확실한 응답의 결과 확인 |
| `lib/api.ts`, `websocket.ts`, `types.ts`, `monitor-state.ts` | HTTP 제한 시간, WS 재연결, 메시지 검증과 상태 표현 |
| `app.css` | 테마 변수·기본 리셋·reduced motion; 영역별 스타일은 각 컴포넌트에 위치 |

반응형 상태는 페이지마다 생성합니다. 입력과 설정 초안은 해당 컴포넌트가 소유하며, 화면을 닫으면 요청·복구 타이머·WebSocket·예약 프레임을 정리합니다. HTTP 상태 조회는 요청 완료 여부만 확인하고, 댓글 목록의 세션 경계는 WebSocket 수신만 적용합니다. 화면 기능을 추가할 때 페이지에 요청 처리나 입력 폼을 다시 모으지 않고 해당 컴포넌트와 상태 모듈을 수정합니다.

## 개발

Linux 데스크톱에서 개발 도구와 Chromium을 설치한 뒤 아래 한 명령으로 백엔드, 프론트엔드, Chromium을 함께 실행할 수 있습니다.

```bash
./scripts/dev.sh
```

의존성 설치 후 `http://127.0.0.1:5173`을 자동으로 엽니다. 실제 방송·데모는 열린 화면에서 선택합니다. 종료는 `Ctrl+C`입니다. 브라우저 없이 실행하려면 `DEV_OPEN_BROWSER=0 ./scripts/dev.sh`를 사용하세요. 실제 방송 연결과 옵션은 [개발 서버 실행 가이드](docs/installation-dev.md#4-개발-서버-실행)를 참고하세요.

Python 3.11 이상, uv, Node.js 22.20 이상(22 계열 권장), pnpm 10.20.0이 필요합니다. 버전은 `backend/uv.lock`, `frontend/pnpm-lock.yaml`로 고정합니다. 주요 검증 버전: TikTokLive 7.0.1, FastAPI 0.141.1, Svelte 5.57.0, SvelteKit 2.70.3, TypeScript 6.0.3. TypeScript 7은 현재 SvelteKit peer 지원 범위 밖이라 사용하지 않습니다.

도구가 없다면 먼저 [개발 도구 설치](docs/installation-dev.md#1-개발-도구-설치)를 진행하세요. 아래 명령은 도구 설치 후 저장소 루트에서 시작합니다.

```bash
cd backend
uv sync --frozen
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

별도 터미널:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Vite 개발 URL을 엽니다. `/ws`, `/health`, `/config`, `/account`, `/refresh`는 Host/Origin을 보존해 백엔드로 proxy되며 `BACKEND_URL`로 대상을 변경할 수 있습니다. 운영에서는 `window.location`으로 ws/wss를 선택합니다. CORS wildcard는 사용하지 않습니다.

## 검사와 프로덕션 빌드

```bash
cd backend
uv run pytest
uv run mypy
uv run ruff check app tests
cd ../frontend
pnpm lint
pnpm format:check
pnpm check
pnpm test
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
```

`pnpm lint`는 JavaScript·TypeScript·Svelte의 ESLint 권장 규칙을 검사합니다. `pnpm format:check`는 Prettier의 공백 4칸 들여쓰기를 포함한 서식을 확인합니다. 자동 수정은 `frontend`에서 `pnpm lint:fix`, 서식 적용은 `pnpm format`으로 실행합니다.

E2E는 정적 빌드가 필요하며 `backend/.venv/bin/python`으로 테스트용 서버를 `127.0.0.1:18765`, 접근성 검사용 `18768`에 실행하고 종료합니다. 테스트가 API 또는 화면에서 데모를 명시적으로 시작합니다. Vite 프록시 검사는 `18766`을 사용합니다. 해당 포트는 비워두세요. 기존 Chromium을 쓰려면 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`를 지정합니다. Linux 브라우저 의존성이 부족하면 Playwright 공식 설치 안내에 따라 `pnpm exec playwright install --with-deps chromium`을 실행합니다.

백엔드 테스트는 health/static route, WebSocket 상태·댓글·disconnect, 큐 drop, 느린 연결 격리, TikTok 이벤트 변환·대기·취소 정리를 확인합니다. 프론트엔드 테스트는 메시지 검증, 10,000개 입력 후 보관 수, 재연결 backoff와 unmount 정리를 확인합니다. E2E는 1080×1920 및 720×1280의 줄바꿈·상태 영역, HTML의 텍스트 표시, 연결 단절 중 댓글 유지, 서버 재시작 후 선택 화면 복귀, 1,000개 burst 수신 순서, 읽기 위치 보존, 요청 시간 초과·결과 확인, 테마·글자 크기 저장을 확인합니다. 390·320px 화면과 키보드 설정창 조작도 검사합니다.

화면 갱신 부하를 다시 측정하려면 다음을 실행합니다. 기존 빌드를 사용하므로 코드 변경 후 먼저 빌드합니다. 자체 임시 포트의 서버를 시작하고 종료하며 TikTok에 연결하지 않습니다.

```bash
cd frontend
pnpm build
pnpm benchmark ../docs/frontend-benchmark-local.json
```

보관 수 30/1,000개, 각 3회, 1,000건 입력, 4배 CPU 지연 조건에서 프레임 간격과 수신 순서를 기록합니다. Raspberry Pi의 시스템 Chromium은 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium`으로 지정할 수 있습니다. 로컬 측정 결과와 실제 Pi에서 확인할 항목은 [검증 기록](VALIDATION.md)에 정리했습니다.

로컬 정적 빌드를 FastAPI에서 확인하려면 `pnpm build` 이후 백엔드를 시작하고 `http://127.0.0.1:8000`을 엽니다. 빌드 폴더를 새로 만든 경우 백엔드를 재시작하세요.

저장소 루트에서 운영 이미지 빌드:

```bash
./scripts/build.sh
docker compose up -d --wait
```

Node 빌드 단계와 Python 의존성 단계를 분리하며 최종 이미지에는 백엔드, production 가상환경, 정적 UI만 들어갑니다. 비root UID 10001, 읽기 전용 루트, `/tmp` tmpfs, localhost 포트만 사용합니다. Node, pnpm, uv 및 개발 의존성은 최종 이미지에 복사하지 않습니다. Python slim 베이스가 제공하는 pip는 남아 있지만 런타임 패키지 설치에는 사용하지 않습니다.

## GitHub Actions CI

`main` 푸시 및 `main` 대상 PR에서 [CI](https://github.com/Longcat2957/tiktok_live_monitor/actions/workflows/ci.yml)가 실행됩니다.
수동 실행(`workflow_dispatch`)도 지원하며 다음 순서로 검사합니다.

1. **checks:** 백엔드 pytest/mypy/Ruff, 셸 문법·업데이트 스크립트 안전성, 프론트엔드 lint/format:check/check/test/build, mock 브라우저 E2E 전체.
2. **Container:** checks 성공 후 AMD64(`ubuntu-24.04`)와 ARM64(`ubuntu-24.04-arm`)에서 각각 운영 이미지를 빌드하고 격리된 컨테이너로 실행합니다. UI 정적 파일, health, HTTP/WebSocket 수신, 설정·재연결·종료 및 실행 권한을 검증합니다.

브라우저 HTML 보고서와 실패 trace·스크린샷은 Actions의 `browser-results` artifact에 7일간 보관합니다. TikTok 인증 없이 mock만 사용하며 테스트 컨테이너는 사용자의 `.env`와 기존 8000번 서비스를 건드리지 않습니다. ARM64 검증은 [GitHub의 ARM64 runner](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)에서 실행하며 실제 Pi의 GUI·부팅 복구 검증은 현장에서 진행합니다.

uv/pnpm 의존성을 lockfile 기준으로 설치하고 다운로드 캐시를 재사용합니다. 같은 브랜치 또는 PR의 새 실행은 이전 실행을 취소하며, 각 작업의 제한 시간은 20분입니다. 실패한 검사는 자동 재시도로 숨기지 않습니다.

Pi 업데이트는 기존 `scripts/install.sh`와 `scripts/update.sh`를 사용합니다. 이미지 레지스트리 발행이나 Pi 자동 배포는 수행하지 않습니다. 업데이트할 커밋의 checks와 두 Container 작업이 모두 통과했는지 확인하세요.

운영 컨테이너 검증은 로컬에서도 실행할 수 있습니다(Docker Engine, Compose 2.24.4 이상, curl 필요).

```bash
./scripts/test-container.sh
```

별도 프로젝트·이미지·임시 localhost 포트를 사용하며 완료 후 해당 테스트 자원을 정리합니다. 실패 로그는 스크립트가 안내하는 임시 디렉터리에 남습니다. CPU 지연 벤치마크는 측정 환경에 민감하므로 CI 성공 조건에 넣지 않으며 `pnpm benchmark`로 별도 실행합니다.

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

`./scripts/update.sh`가 현재 브랜치의 upstream에서 `git pull --ff-only`로 소스를 받고 재빌드·교체·healthy 확인까지 수행합니다. 미커밋 변경이나 이력 분기가 있으면 중단하며 `.env`는 보존합니다. 방송이 끝난 뒤 실행하세요. 빌드 실패 시 기존 컨테이너를 유지하지만, 교체 후 health 실패에 대한 자동 롤백은 없습니다. 기존 재빌드 전용 스크립트 사용자는 최초 한 번 `git pull --ff-only`로 새 스크립트를 받으세요. 별도의 앱 systemd unit은 필요하지 않습니다. `docker compose stop`으로 수동 중지하면 unless-stopped 정책상 다음 부팅에도 중지 상태가 유지되므로 `docker compose up -d`로 다시 시작합니다.

## 장애 진단

| 증상 | 확인할 내용 |
| --- | --- |
| 방송 시작 대기 | `waiting`은 정상입니다. 지정 계정에서 LIVE를 시작하면 자동 재연결합니다. |
| TikTok 연결 오류 | 인터넷/DNS, 계정 아이디, 방송 공개 여부를 확인합니다. `docker compose logs --tail=100 app`의 오류 종류를 확인합니다. 비공식 API 또는 서명 서비스 변경이면 TikTokLive 공식 저장소 이슈를 확인하고 adapter 테스트와 lockfile을 함께 갱신합니다. |
| 계정을 찾지 못함 | 모니터를 종료한 뒤 첫 화면에서 @아이디 또는 TikTok 프로필·LIVE 주소를 입력합니다. 표시 이름과 단축 공유 링크는 지원하지 않습니다. |
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
- 인터넷 단절 후 자동 재연결. 컨테이너 재시작 후 선택 화면으로 돌아와 시작 버튼으로 다시 실행.
