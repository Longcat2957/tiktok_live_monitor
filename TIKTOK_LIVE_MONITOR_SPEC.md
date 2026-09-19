# TikTok LIVE 세로형 댓글 모니터 — Codex 구현 명세서

> 이 문서는 구현 담당 Codex에게 그대로 전달하는 프로젝트 명세서다. 아래의 목표, 범위, 기술 선택, 제약사항과 완료 조건을 기준으로 실제 동작하는 저장소 전체를 작성하라. 설명용 의사 코드만 만들지 말고, 설치·개발·빌드·배포·자동 실행까지 가능한 결과물을 완성하라.

## 1. 프로젝트 목적

TikTok LIVE 방송 중 들어오는 **모든 일반 댓글을 수신 순서대로** 큰 글씨로 표시하는 전용 모니터를 만든다.

장비는 Raspberry Pi 4이며 모니터를 물리적으로 세로로 세운다. Raspberry Pi OS에서 화면 출력을 90도 회전하여 브라우저에는 약 `1080 × 1920` 크기의 세로 viewport가 제공된다고 가정한다.

최종 사용자에게 기본 입력 수단(키보드·마우스 또는 터치)이 있다고 가정한다. 전원을 넣으면 서비스와 브라우저가 자동 실행되고, 화면에서 계정을 입력하면 방송에 연결한다.

핵심 사용자 경험은 다음과 같다.

1. Raspberry Pi 전원을 켠다.
2. 네트워크가 연결된다.
3. 댓글 수신 서비스가 자동으로 실행된다.
4. Chromium이 kiosk 모드로 자동 실행된다.
5. 화면에서 계정을 입력한다. TikTok LIVE가 시작되거나 연결 가능해지면 댓글이 자동으로 나타난다.
6. 연결이 끊겨도 화면이나 서비스를 수동으로 재시작할 필요가 없다.

## 2. 확정 기술 스택

| 영역 | 기술 |
| --- | --- |
| 하드웨어 | Raspberry Pi 4, 권장 RAM 4GB |
| 운영체제 | Raspberry Pi OS Desktop 64-bit |
| Python 관리 | `uv` |
| 백엔드 | Python 3.11 이상, FastAPI, Uvicorn |
| TikTok 수신 | Python `TikTokLive` 패키지 |
| 실시간 전달 | FastAPI WebSocket |
| 프론트엔드 | SvelteKit, Svelte 5, TypeScript |
| 패키지 관리 | `pnpm` |
| 운영 빌드 | `@sveltejs/adapter-static` 정적 빌드 |
| 정적 파일 제공 | FastAPI `StaticFiles` |
| 컨테이너 | Docker Engine, Docker Compose plugin |
| 서비스 관리 | Docker Compose `restart: unless-stopped` |
| 표시 | Chromium kiosk, 세로형 HDMI 모니터 |

SvelteKit을 사용하되 MVP에서는 `/` 한 페이지만 사용한다. 운영 환경에서 SvelteKit Node 서버를 상시 실행하지 않는다. multi-stage Docker build의 Node 단계에서 프론트엔드를 정적으로 빌드하고, 최종 Python 이미지의 FastAPI가 결과물을 제공한다.

운영 애플리케이션은 컨테이너 하나로 실행한다. Chromium과 Raspberry Pi Desktop은 호스트에서 실행한다. GUI와 HDMI까지 컨테이너에 넣지 않는다.

## 3. MVP 범위

### 반드시 구현할 기능

- 설정된 TikTok 계정의 LIVE에 연결한다.
- 모든 `CommentEvent`를 별도 분류나 필터 없이 받는다.
- 닉네임, TikTok 고유 아이디, 댓글 본문을 WebSocket 메시지로 전달한다.
- 댓글을 수신 순서대로 화면 아래쪽에 쌓는다.
- 새 댓글이 나타나면 기존 댓글이 위로 밀려난다.
- 브라우저 메모리와 DOM이 무한히 증가하지 않도록 최근 댓글만 유지한다.
- 댓글이 길면 가로로 넘치지 않고 여러 줄로 표시한다.
- 백엔드 및 TikTok 연결 상태를 화면에 작고 명확하게 표시한다.
- WebSocket과 TikTok 연결이 끊기면 자동으로 재연결한다.
- 실방송 없이 프론트엔드와 WebSocket 흐름을 시험할 수 있는 mock 댓글 모드를 제공한다.
- Docker Compose가 백엔드를 부팅 시 자동 실행하고 비정상 종료 시 재시작한다.
- Raspberry Pi Desktop 로그인 후 Chromium이 자동으로 kiosk 모드로 열린다.
- README만 보고 새 Raspberry Pi에 설치할 수 있어야 한다.

### 추가 확정 범위: LIVE 정보와 활동 알림

- 댓글 작성자 프로필 사진, 구독자·팬 배지와 제공되는 레벨을 표시한다. 사진 로딩 실패와 정보 누락은 대체 표시로 처리한다.
- 상단에 방송 아이디, 현재 시청자 수와 좋아요 합계를 표시한다. 푸터 왼쪽에는 방송 중·일시정지·종료 상태, 오른쪽에는 서버 연결 상태를 표시한다.
- 일반 댓글 UI는 유지한다. 선물·팔로우·공유·구독 알림은 각각 핑크·초록·파랑·보라 배경, 이벤트 이름과 일반 댓글보다 큰 굵은 글씨로 구분한다. 다크·라이트 테마와 글자 배율을 따르고 긴 내용은 줄바꿈한다. 댓글과 같은 수신 순서를 유지하며 목록 보관 수는 댓글과 활동을 합친 수다.
- 선물 연속 전송은 마지막 누적 수량만 표시하며 금액으로 환산하지 않는다.
- 상태 메시지에 `live: {state, viewers, likes}` 스냅샷을 포함한다. 통계는 최대 초당 한 번 모아 전달하고, 방송 상태 변경은 즉시 전달한다. 아직 수신하지 않은 통계는 `null`이다.
- 댓글·활동은 replay하지 않는다. 새 브라우저에는 최신 상태·통계만 전달한다. 새로운 세션에서는 통계와 목록을 초기화한다.
- mock은 외부 네트워크 없이 프로필·배지·네 가지 활동 및 일시정지→재개→종료→새 방송을 반복한다.
- 계정 하나, 영구 저장 없음, bounded queue와 느린 브라우저 격리는 유지한다.

### MVP에서 제외할 기능

- 댓글 분류, 질문 탐지, 키워드 필터링
- LLM 또는 AI 기능
- 데이터베이스와 댓글 영구 저장
- Redis 및 외부 메시지 큐
- 사용자 로그인과 권한 관리
- 운영자용 대시보드
- 애니메이션 중심 UI
- 클라우드 서버 또는 외부 managed WebSocket
- TikTok 계정 여러 개 동시 연결

범위 밖 기능을 미리 추상화하거나 과도하게 일반화하지 않는다. 다만 파일 구조와 타입은 향후 `/admin` 같은 페이지를 추가할 수 있을 정도로 정돈한다.

## 4. 전체 구조

```text
TikTok LIVE
    │
    │ CommentEvent
    ▼
TikTokLive client
    │
    ▼
내부 asyncio queue
    │
    ▼
FastAPI WebSocket (/ws)
    │
    ▼
SvelteKit static UI (/)
    │
    ▼
Chromium kiosk
    │
    ▼
1080 × 1920 세로 모니터
```

백엔드 내부에는 bounded `asyncio.Queue`를 둔다. TikTok 이벤트 콜백에서 느린 WebSocket 클라이언트로 직접 전송하지 말고 큐에 넣은 뒤 별도의 broadcast task가 소비하도록 한다. 큐가 가득 찬 극단적인 상황에서는 서비스 전체를 멈추지 말고 가장 오래된 항목을 제거한 뒤 최신 댓글을 넣고 경고 로그를 남긴다.

브라우저 연결이 없어도 TikTok 수신 루프는 정상 동작해야 한다. 한 WebSocket 클라이언트의 오류나 지연이 다른 클라이언트 또는 TikTok 수신을 막으면 안 된다.

## 5. 권장 저장소 구조

```text
tiktok-live-monitor/
├── backend/
│   ├── app/
│   │   ├── main.py                 # 앱 조립과 lifespan
│   │   ├── __main__.py             # 서버 실행
│   │   ├── config.py
│   │   ├── api/
│   │   │   ├── dependencies.py
│   │   │   ├── security.py
│   │   │   ├── exception_handlers.py
│   │   │   └── routers/
│   │   │       ├── monitor.py
│   │   │       ├── settings.py
│   │   │       ├── health.py
│   │   │       └── websocket.py
│   │   ├── schemas/
│   │   │   ├── monitor.py
│   │   │   ├── settings.py
│   │   │   ├── health.py
│   │   │   └── events.py
│   │   ├── services/
│   │   │   ├── monitor.py
│   │   │   ├── demo.py
│   │   │   ├── event_sink.py
│   │   │   └── errors.py
│   │   ├── integrations/
│   │   │   └── tiktok.py
│   │   └── realtime/
│   │       └── broadcaster.py
│   ├── tests/
│   │   ├── api/
│   │   ├── services/
│   │   ├── integrations/
│   │   └── realtime/
│   ├── pyproject.toml
│   ├── uv.lock
│   └── .python-version
├── frontend/
│   ├── src/
│   │   ├── app.html
│   │   ├── app.css
│   │   ├── lib/
│   │   │   ├── monitor/
│   │   │   │   ├── session.svelte.ts
│   │   │   │   └── commands.svelte.ts
│   │   │   ├── components/
│   │   │   │   ├── MonitorHeader.svelte
│   │   │   │   ├── AccountSetup.svelte
│   │   │   │   ├── LiveSummary.svelte
│   │   │   │   ├── RequestFeedback.svelte
│   │   │   │   ├── SettingsDialog.svelte
│   │   │   │   ├── CommentItem.svelte
│   │   │   │   ├── CommentList.svelte
│   │   │   │   └── ConnectionStatus.svelte
│   │   │   ├── config.ts
│   │   │   ├── types.ts
│   │   │   └── websocket.ts
│   │   └── routes/
│   │       ├── +layout.svelte
│   │       └── +page.svelte
│   ├── static/
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── svelte.config.js
│   ├── tsconfig.json
│   └── vite.config.ts
├── deploy/
│   ├── kiosk-autostart
│   └── wait-for-app.sh
├── scripts/
│   ├── install.sh
│   ├── build.sh
│   └── update.sh
├── Dockerfile
├── compose.yaml
├── .dockerignore
├── .env.example
├── .gitignore
├── AGENTS.md
└── README.md
```

Python 패키지별 `__init__.py`는 위 목록에서 생략했다. 백엔드·프론트엔드·배포 파일의 책임을 분리한다.

- `main.py`는 앱 생성, lifespan, 보안·예외 처리·라우터 등록과 정적 파일 연결을 담당한다.
- HTTP·WebSocket 라우터는 공통 `get_monitor` 의존성으로 `MonitorService`를 받는다. HTTP 라우터는 내부 큐·작업 집합을 직접 조회하지 않는다.
- `MonitorService`의 시작·종료·재연결·설정 변경은 명시적인 공개 메서드로 제공하며 내부의 단일 직렬 전환 경로를 공유한다. 상태·설정 조회는 명시적 응답 모델을 반환한다.
- TikTokLive API는 `integrations/tiktok.py`에 격리한다. `services/demo.py`는 같은 앱 이벤트 계약으로 데모를 생성하고, `EventSink`는 이전 세션의 늦은 이벤트를 차단한다.
- `realtime/broadcaster.py`는 브라우저별 송신 큐와 느린 연결 격리를 담당한다.
- 잘못된 런타임 설정은 서비스의 `InvalidSettingsError`를 통해 422로 변환한다. 내부 Pydantic 오류를 일괄적으로 사용자 입력 오류로 처리하지 않는다.
- API 경로·JSON·WebSocket 계약과 `app.main:app`, `python -m app` 실행 방식은 유지한다.

## 6. 환경 설정

루트 `.env.example`에 최소한 다음 값을 둔다.

```dotenv
COMMENT_QUEUE_SIZE=500
COMMENT_HISTORY_SIZE=30
TIKTOK_RECONNECT_MIN_SECONDS=2
TIKTOK_RECONNECT_MAX_SECONDS=30
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
```

규칙:

- `.env`는 Git에 포함하지 않는다.
- 모드·계정은 화면에서만 선택한다. 서버는 항상 idle로 시작하고 첫 화면에는 실제 방송이 선택된다. 사용자가 데모를 선택하고 시작하면 TikTok 연결 없이 가짜 댓글을 주기적으로 생성한다. 모드별 환경변수나 별도 서버는 없다.
- 누락되거나 잘못된 환경값은 조용히 무시하지 말고 시작 시 이해 가능한 오류를 출력한다.
- TikTok 계정은 화면에서 입력한다. `POST /account`는 @아이디 또는 TikTok 프로필·LIVE 주소를 검증해 아이디로 정규화한다. 기존 `TIKTOK_USERNAME` 환경변수는 사용하지 않는다.
- 컨테이너 내부에서는 `0.0.0.0:8000`에 bind하고, 외부 노출 범위는 Compose port mapping `127.0.0.1:8000:8000`으로 제한한다.

## 7. 백엔드 요구사항

### 7.1 생명주기

FastAPI의 lifespan context manager를 사용한다. deprecated된 startup/shutdown decorator에 새 구현을 의존하지 않는다.

시작 시 다음 장기 실행 task를 생성한다.

- 선택된 comment source 실행 task
- queue consumer 및 WebSocket broadcast task

종료 시 task를 cancel하고 `asyncio.gather(..., return_exceptions=True)` 등으로 정리하여 종료 경고가 남지 않게 한다. TikTok 연결 함수는 장기 실행이므로 애플리케이션 startup에서 직접 `await`하여 서버 시작을 막지 않는다.

### 7.2 댓글 데이터 모델

서버에서 프론트로 전달하는 댓글 메시지는 다음 형식을 따른다.

```json
{
  "type": "comment",
  "id": "server-generated-unique-id",
  "received_at": "2026-09-12T10:30:00.000Z",
  "user": {
    "nickname": "민수",
    "unique_id": "minsu123"
  },
  "comment": "검정색도 있나요?"
}
```

연결 상태 메시지는 다음처럼 명시적으로 구분한다.

```json
{
  "type": "status",
  "source": "tiktok",
  "state": "connecting",
  "message": "TikTok LIVE 연결 중"
}
```

`state`는 최소한 `connecting`, `connected`, `waiting`, `disconnected`, `error`를 지원한다. 방송이 아직 시작되지 않은 정상적인 대기 상태와 실제 오류를 구분한다.

### 7.3 TikTok source

- 현재 설치되는 `TikTokLive` 버전의 공개 API를 확인하여 구현한다.
- 패키지 버전을 lockfile에 고정한다.
- `CommentEvent`에서 닉네임, unique ID, 댓글 본문을 안전하게 추출한다.
- 비공식/reverse-engineered 연동이므로 API 변경, 방송 종료, 네트워크 단절을 정상 운영 상황으로 간주한다.
- 재연결은 exponential backoff와 상한을 사용한다.
- 인증 정보나 전체 이벤트 객체를 로그에 출력하지 않는다.
- 빈 댓글 또는 변환할 수 없는 이벤트는 경고 후 건너뛴다.

### 7.4 WebSocket manager

- endpoint는 `/ws`이다.
- 연결 수락, 연결 제거, JSON broadcast를 담당한다.
- 전송 실패한 소켓은 즉시 제거한다.
- 한 연결의 예외가 전체 broadcast loop를 종료시키지 않는다.
- 같은 연결의 중복 등록을 막는다.
- 브라우저 연결 직후 현재 source 상태를 한 번 전송한다.
- 현재 MVP에서는 과거 댓글 replay를 요구하지 않는다.

### 7.5 HTTP endpoint

최소한 다음 endpoint를 제공한다.

- `GET /health`: 프로세스 생존, source 상태, WebSocket 연결 수, queue 사용량을 JSON으로 반환
- `GET /`: 빌드된 SvelteKit UI 반환
- `GET /ws`: WebSocket upgrade endpoint

API 및 WebSocket route를 등록한 뒤 마지막에 정적 파일을 `/`에 mount한다. 정적 파일 mount가 `/health`나 `/ws`를 가리지 않도록 route 순서 또는 명시적 구조를 검증한다.

운영은 same-origin이므로 wildcard CORS를 기본으로 켜지 않는다. 개발 서버에서만 필요한 origin을 명시적으로 허용하거나 Vite proxy를 사용한다.

## 8. 프론트엔드 요구사항

### 8.1 SvelteKit 구성

- SvelteKit과 Svelte 5 문법을 사용한다.
- TypeScript strict 설정을 유지한다.
- `@sveltejs/adapter-static`을 사용한다.
- 현재 페이지는 `/` 하나뿐이다.
- SSR이 필요 없는 kiosk UI이므로 정적 prerender가 가능하도록 구성한다.
- WebSocket 객체는 브라우저에서만 생성한다.
- 운영 WebSocket URL은 `window.location`을 기준으로 `ws:` 또는 `wss:`를 자동 선택한다.
- 운영 UI는 SvelteKit 기본 버전 확인을 30초 간격으로 사용하고 새 빌드를 감지한 경우에만 페이지를 다시 불러온다. 동일 버전·네트워크 실패에는 새로고침하지 않는다. 구버전 화면의 최초 수동 새로고침을 배포 문서에 안내한다.
- 개발 환경은 Vite proxy 또는 공개 환경변수로 backend 주소를 정한다. 코드에 `localhost:8000`을 여러 군데 하드코딩하지 않는다.

### 8.2 WebSocket 재연결

`websocket.ts`는 다음을 책임진다.

- connect/disconnect 상태 제공
- 수신 JSON 검증 및 예상하지 못한 메시지 무시
- 재연결 exponential backoff와 최대 대기 시간
- 연결 성공 시 backoff 초기화
- 컴포넌트 unmount 시 timer와 socket 정리
- 수동 종료와 장애 종료를 구분하여 unmount 이후 재연결하지 않기

연결이 잠시 끊겨도 기존 댓글은 화면에 유지한다.

### 8.3 댓글 표시 정책

- 수신된 모든 일반 댓글을 동일한 중요도로 표시한다.
- 화면에는 닉네임과 댓글 본문이 중심이 된다.
- unique ID는 기본적으로 숨기거나 닉네임이 없을 때 fallback으로만 쓴다.
- 기본 보관량은 최근 30개이되 환경 설정 또는 상수 한 곳에서 조정 가능하게 한다.
- 실제 화면에는 viewport 높이에 맞는 최신 댓글이 자연스럽게 보이면 된다.
- keyed each block에는 서버가 생성한 `id`를 사용한다.
- 댓글 HTML은 일반 텍스트로 렌더링하여 script나 markup이 실행되지 않게 한다.
- 긴 영문 문자열, URL, 이모지, 한글 줄바꿈을 모두 견뎌야 한다.

### 8.4 세로형 UI

목표 viewport는 `1080 × 1920`이지만 특정 픽셀 크기에만 맞추지 말고 반응형으로 작성한다.

디자인 원칙:

- 검은색 또는 매우 어두운 배경, 흰색 본문
- 높은 명암비
- 상단의 넓은 빈 공간보다 최신 댓글 가독성을 우선
- 댓글 목록은 화면 하단 정렬
- 닉네임은 본문보다 작고 약한 색
- 본문은 멀리서 읽을 수 있는 큰 글씨와 충분한 행간
- 댓글 사이에는 단순한 간격 또는 얇은 구분선
- 과도한 그림자, 카드 장식, 복잡한 애니메이션 제외
- 새 댓글 애니메이션은 없거나 매우 짧게 유지
- 스크롤바와 마우스 커서가 시선을 끌지 않게 처리
- 브라우저 기본 margin과 overflow로 인해 화면 밖으로 밀리지 않게 처리
- `prefers-reduced-motion`을 존중

화면 한쪽 구석에는 작은 상태 표시를 둔다.

- 연결됨: 눈에 거슬리지 않는 녹색 점과 짧은 문구
- 연결 중/방송 대기: 노란색 계열
- 오류/연결 끊김: 빨간색 계열과 짧은 원인

상태 표시는 댓글을 가리면 안 된다.

### 8.5 화면 회전 원칙

CSS `transform: rotate(90deg)`로 페이지를 회전하지 않는다. Raspberry Pi OS의 display 설정에서 출력 전체를 회전한다. 프론트엔드는 처음부터 세로 viewport를 받는다고 가정한다.

## 9. 개발과 운영 실행 방식

### 개발 모드

- Backend: `uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- Frontend: `pnpm dev`
- 화면에서 데모 체험을 선택해 실제 TikTok 방송 없이 전체 흐름을 시험할 수 있어야 한다. 개발 실행과 운영 Docker 실행 모두 두 데이터 모드를 지원한다.

### 운영 빌드

1. `docker compose build`가 multi-stage Dockerfile을 빌드한다.
2. Node build stage에서 `pnpm install --frozen-lockfile`과 SvelteKit 정적 빌드를 수행한다.
3. Python runtime stage에서 backend 의존성을 설치하고 `frontend/build` 결과만 복사한다.
4. Compose가 FastAPI/Uvicorn 컨테이너 하나를 실행한다.
5. 호스트 Chromium은 `http://127.0.0.1:8000`을 연다.

운영 컨테이너 안에는 Node.js, pnpm, frontend source와 빌드 cache를 남기지 않는다. 빌드 스크립트는 실행 위치에 의존하지 않도록 자신의 파일 위치를 기준으로 저장소 루트를 계산한다. 오류 발생 시 즉시 종료하며 실패를 숨기지 않는다.

## 10. Raspberry Pi 배포 요구사항

### Dockerfile

루트 `Dockerfile`은 Raspberry Pi 4의 ARM64에서 빌드 및 실행 가능한 multi-stage 이미지여야 한다.

- Node build stage: corepack/pnpm을 사용해 lockfile 기반으로 프론트엔드를 빌드
- Python dependency stage: `uv.lock`을 기준으로 production 의존성 설치
- Python runtime stage: backend 코드, 가상환경, `frontend/build`만 포함
- Debian/Ubuntu 계열의 ARM64 지원 slim 이미지를 기본으로 사용
- floating `latest` tag를 사용하지 않고 major/minor 또는 digest 수준으로 재현성을 확보
- 컨테이너 내부에서 앱을 root로 실행하지 않음
- 불필요한 compiler, package manager cache 및 개발 의존성을 최종 이미지에서 제외
- Uvicorn은 컨테이너 내부 `0.0.0.0:8000`에 bind
- `PYTHONUNBUFFERED=1`로 로그를 즉시 출력
- exec-form `CMD`를 사용하여 종료 신호가 Uvicorn에 전달되게 함

`uv.lock`과 `pnpm-lock.yaml`을 저장소에 포함하고 Docker build가 두 lockfile을 엄격히 사용해야 한다.

### Docker Compose

루트 `compose.yaml`에는 애플리케이션 서비스 하나만 둔다.

- source bind mount 없이 빌드된 이미지를 실행
- 루트 `.env`를 `env_file`로 전달
- `127.0.0.1:8000:8000`으로만 publish하여 LAN에 기본 노출하지 않음
- `restart: unless-stopped`
- `/health`를 사용하는 healthcheck. 최종 이미지에 `curl`을 넣지 않는다면 Python 표준 라이브러리로 검사
- `init: true` 또는 동등한 정상적인 PID 1/signal 처리
- `read_only: true`를 우선 적용하고 필요한 임시 쓰기 경로만 `tmpfs`로 제공
- privileged mode, host network, Docker socket mount를 사용하지 않음
- DB가 없으므로 volume을 억지로 추가하지 않음
- Raspberry Pi에서 별도 registry 없이 `docker compose build`가 동작해야 함

Docker daemon 자체는 OS 부팅 시 시작되도록 `sudo systemctl enable --now docker`를 사용한다. Compose의 restart policy가 생성된 컨테이너를 복구하므로 애플리케이션용 systemd unit을 별도로 중복 생성하지 않는다.

### 업데이트 스크립트

`scripts/update.sh`는 현재 브랜치의 upstream에서 `git pull --ff-only` 후 이미지 빌드와 Compose 교체, 최대 120초 healthy 대기를 수행한다. 미커밋 변경·추적하지 않는 파일, `.env` 누락, upstream 미설정 또는 분기된 Git 이력은 중단한다. `.env`는 보존하고 자동 stash/reset/merge는 하지 않는다. 빌드 실패 시 기존 컨테이너를 유지하며 교체 후 자동 롤백은 구현하지 않는다. 방송 종료 후 실행하고 CI 통과 여부는 운영자가 먼저 확인한다. 정상 배포 후 앱 라벨(`org.opencontainers.image.title=tiktok-live-monitor`)이 있는 태그 없는 미사용 이미지를 정리하며 라벨 도입 전의 직전 앱 이미지도 태그가 없을 때 강제 옵션 없이 삭제한다. 사용 중·별도 태그 이미지는 보존한다. 빌드·health 실패 시 정리하지 않으며 정리 실패는 경고로 처리한다. 공유 빌드 캐시·볼륨은 삭제하지 않고 `docker system df`로 사용량을 표시한다. `python3 scripts/test-update.py`는 로컬 임시 Git 저장소와 가짜 Docker로 업데이트·중단 경로를 검사한다.

### Chromium kiosk

Raspberry Pi OS Desktop의 labwc autostart를 기준으로 한다. 제공할 실행 항목에는 최소한 다음 의도가 반영되어야 한다.

```text
chromium http://127.0.0.1:8000
  --kiosk
  --noerrdialogs
  --disable-infobars
  --no-first-run
  --start-maximized
```

실제 Chromium 실행 파일명이 OS 버전에 따라 다를 수 있으므로 설치 스크립트에서 `chromium`과 `chromium-browser`를 확인하거나 README에 진단법을 제공한다. `deploy/wait-for-app.sh`는 `http://127.0.0.1:8000/health`가 성공할 때까지 제한된 간격으로 기다린 다음 Chromium을 실행한다. Docker 이미지 다운로드나 재빌드가 길어질 수 있으므로 너무 짧은 고정 timeout으로 포기하지 않되, 대기 상태를 로그로 확인할 수 있게 한다.

### 설치 스크립트

`scripts/install.sh`는 최소한 다음을 수행하거나 명확히 안내한다.

- 지원 OS와 필수 명령 확인
- Docker Engine, Docker Compose plugin, Chromium 존재 확인
- 현재 사용자가 Docker를 실행할 권한이 있는지 확인하고 필요한 설정 안내
- `.env`가 없을 때 `.env.example` 복사 후 기본값 사용 또는 설정 수정 안내
- Docker daemon enable/start
- `docker compose build`와 `docker compose up -d` 실행
- labwc autostart 설치 또는 설치 명령 안내

사용자 파일을 덮어쓸 가능성이 있는 작업은 백업하거나 확인을 요구한다. 설치 스크립트를 여러 번 실행해도 치명적인 중복 설정이 생기지 않게 가능한 범위에서 idempotent하게 만든다.

## 11. 로깅과 장애 처리

- 로그는 Python 표준 `logging`을 기반으로 한다.
- 정상 연결, 방송 대기, 연결 종료, 재연결 대기, 재연결 성공을 구분한다.
- 같은 오류가 반복될 때 매 순간 stack trace를 쏟아내지 않는다.
- 알 수 없는 예외는 stack trace를 남기되 프로세스가 복구 가능한지 판단한다.
- WebSocket client disconnect는 일반적인 사건으로 처리한다.
- TikTok 연결 실패로 FastAPI의 `/health`와 UI 정적 제공까지 같이 죽지 않아야 한다.
- UI에는 기술적인 traceback을 표시하지 않고 짧은 사용자용 상태만 표시한다.

## 12. 테스트와 품질 기준

### Backend 자동 테스트

- `/health`가 200과 예상 schema를 반환한다.
- WebSocket 연결 직후 상태 메시지를 받는다.
- mock source가 만든 댓글이 WebSocket에 전달된다.
- 댓글 payload schema가 맞다.
- 끊긴 WebSocket client가 manager에서 제거된다.
- queue 최대 크기를 넘을 때 정의한 drop 정책이 작동한다.

### Frontend 검사

- TypeScript/Svelte type check 통과
- production build 성공
- malformed WebSocket message가 UI를 죽이지 않음
- 댓글 수가 제한값을 넘으면 가장 오래된 댓글이 제거됨
- WebSocket 연결 해제 후 재연결하며 기존 댓글이 유지됨

### 수동 인수 테스트

1. 첫 화면에서 mock 데모를 선택하고 시작하면 댓글이 계속 표시된다.
2. 브라우저 개발자 도구에서 WebSocket 연결을 끊으면 상태가 변경되고 자동 재연결된다.
3. backend 재시작 후 새로고침 없이 첫 화면으로 돌아오고 모드·계정을 선택해 다시 시작한다.
4. 한글, 영문, 이모지, 매우 긴 댓글이 화면 밖으로 가로 overflow되지 않는다.
5. 1080 × 1920 및 720 × 1280 viewport에서 최신 댓글과 상태 표시가 겹치지 않는다.
6. 수 시간 mock 부하 후 DOM 댓글 수와 메모리 사용량이 계속 증가하지 않는다.
7. Raspberry Pi 재부팅 후 Compose 컨테이너와 Chromium kiosk가 자동으로 복구된다.
8. 실제 TikTok LIVE에서 댓글 순서와 닉네임/본문이 정상 표시된다.

## 13. 완료 조건

다음 조건을 모두 만족해야 구현 완료로 간주한다.

- 저장소의 모든 필수 파일에 실제 구현이 들어 있다.
- placeholder, TODO-only 파일, 동작하지 않는 의사 코드를 남기지 않는다.
- 화면에서 모니터를 종료한 뒤 실제 방송을 선택하고 TikTok 계정을 바꿀 수 있다.
- mock 모드로 end-to-end 데모가 된다.
- backend 테스트가 통과한다.
- frontend check와 production build가 통과한다.
- FastAPI에서 빌드된 SvelteKit 화면을 열 수 있다.
- multi-stage Dockerfile, Compose healthcheck/restart policy와 kiosk autostart가 실제로 동작한다.
- README에 개발 실행, production build, Pi 설치, 화면 회전, 로그 확인, 서비스 재시작, 일반적인 장애 해결이 포함된다.
- 사용자가 전원을 켠 뒤 댓글 화면을 보기 위해 터미널 명령을 입력할 필요가 없다.

## 14. README에 반드시 포함할 운영 명령

README에는 실제 프로젝트 경로와 서비스명을 기준으로 다음 종류의 명령을 제공한다.

```bash
docker compose ps
docker compose logs -f app
docker compose restart app
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

추가로 다음 문제의 진단법을 짧게 적는다.

- TikTok LIVE가 아직 시작되지 않음
- TikTokLive 패키지/API 변경으로 연결 실패
- 계정 아이디 오타 또는 잘못된 형식
- 인터넷 연결 없음
- Chromium이 실행되지 않음
- 화면이 가로로 나옴
- 프론트엔드 build 디렉터리가 없음
- Docker daemon 또는 Compose plugin이 없음
- ARM64 이미지 빌드 실패
- 컨테이너 healthcheck 실패 또는 재시작 반복

## 15. Codex 구현 지시

구현 시 다음 순서로 작업하라.

1. 현재 작업 디렉터리와 기존 파일을 먼저 조사하고 사용자 변경사항을 보존한다.
2. 최신 안정 버전과 해당 버전의 공식 문서를 기준으로 SvelteKit/Svelte/FastAPI API를 사용한다.
3. TikTokLive는 비공식 연동이므로 설치된 정확한 버전의 API를 확인하여 adapter 내부에 격리한다.
4. 먼저 mock source로 backend WebSocket과 UI의 end-to-end 흐름을 완성한다.
5. 그 다음 TikTok source와 재연결을 연결한다.
6. production static build와 FastAPI 제공을 검증한다.
7. 자동 테스트, type check, build를 실행하고 실패 원인을 수정한다.
8. multi-stage Dockerfile, Compose 배포와 host kiosk 파일을 작성하고 ARM64 호환성과 부팅 후 복구를 검증한다.
9. 마지막에 README를 실제 구현과 일치하도록 갱신한다.
10. 완료 보고에는 변경한 핵심 파일, 실행한 검증, 남은 외부 의존 위험만 간결하게 적는다.

보안상 계정 암호, 쿠키, 세션 토큰을 코드나 예제에 넣지 않는다. TikTokLive 동작을 위해 추가 인증이 꼭 필요하다는 것이 확인된 경우에도 임의로 자격 증명을 수집하거나 우회하지 말고, 필요한 설정과 위험을 README에 명시한다.

## 16. 향후 확장 방향 — 현재는 구현하지 않음

MVP 검증 이후에만 다음을 고려한다.

- `/admin` 운영자 화면
- 특정 댓글 고정 및 읽음 표시
- 질문/구매 의도 댓글 강조
- 금칙어 또는 spam 필터
- 여러 화면 또는 원격 태블릿 연결
- 댓글 통계와 영구 저장
- managed LIVE WebSocket 공급자 전환

현재 구현은 이 기능을 위해 불필요한 DB, 인증 계층 또는 범용 플러그인 시스템을 만들지 않는다. 확장은 기존 comment source → queue → WebSocket → UI 경계를 유지하는 방식으로 진행한다.

## 계정 입력 방식 변경 (2026-09-15)

이 절은 위의 환경변수 기반 계정 선택 요구사항을 대체한다.

- 모든 모드는 시작 전까지 `idle` 상태로 웹 서버와 WebSocket만 실행한다. health는 정상이다.
- 프론트엔드 입력 폼과 `POST /account`의 source, username으로 모드·계정을 선택·변경한다. 기본 입력 수단은 있다고 가정한다.
- @아이디 또는 HTTPS TikTok 프로필·LIVE 주소만 받는다. 입력 URL로 직접 요청하거나 단축 링크를 따라가지 않는다.
- 전환 요청은 순차 처리하며 이전 source 종료 후 큐를 비우고 새 source를 시작한다.
- status의 `session_id`, `username`으로 모든 브라우저에 선택 계정과 전환 경계를 전달한다. 새 세션에서는 댓글을 비운다.
- 계정은 메모리에만 보관한다. 새로고침에는 유지되고 백엔드 재시작에는 초기화된다. 댓글 영구 저장은 없다.
- 모드 선택 환경변수는 사용하지 않는다. mock도 시작 버튼을 눌러야 실행한다. 모드 변경은 모니터를 종료한 뒤 첫 화면에서 한다.
- API는 same-origin 사용과 localhost 배포를 유지한다.

## UI 디자인 시스템 변경

- 내부 입력 컴포넌트는 m3-svelte를 사용한다. 모드 선택은 ConnectedButtons와 라디오 입력, 계정 입력은 TextFieldOutlined, 동작은 Button으로 구현한다.
- 검정 배경, 핑크레드 주요 동작, 시안 강조의 색상을 M3 CSS 변수로 일관되게 적용한다.
- 사용자 화면의 mock 모드 이름은 데모 체험이다. 실행 중 DEMO 표시를 유지한다.
- 세로 모니터용 큰 댓글 글자, plain text, 키보드 조작과 reduced motion을 유지한다.

## 댓글 화면 도구 버튼

- 모드·계정 변경과 강제 초기화는 M3 아이콘 버튼으로 표시한다. 접근 가능한 이름과 hover/focus 설명을 제공하고 Escape로 설명을 닫을 수 있다.
- `DELETE /account`는 계정 전환과 같은 잠금·취소·큐 정리 경로를 사용해 수신을 중지한다.
- 초기화 시 새 세션의 idle 상태를 모든 브라우저에 전달해 댓글과 계정을 비우고 첫 화면으로 돌아간다. 첫 화면에는 실제 방송이 선택되며 시작 전에는 연결하지 않는다.
- 초기화 실패는 화면에 표시하며 성공 응답 전에 댓글을 임의로 지우지 않는다.

## 런타임 설정 모달

- 조절 아이콘은 모니터 설정 모달을 연다. 모달 뒤의 댓글 수신·표시는 계속 유지한다.
- 모달에서는 모드·계정을 변경하지 않는다. 모니터 종료 후 첫 화면에서 선택·입력한다.
- 공통 변경 항목: COMMENT_HISTORY_SIZE, COMMENT_QUEUE_SIZE, LOG_LEVEL. 실제 방송 설정에는 TIKTOK_RECONNECT_MIN_SECONDS, TIKTOK_RECONNECT_MAX_SECONDS만, 데모 설정에는 MOCK_INTERVAL_SECONDS만 추가한다. HOST, PORT, STATIC_DIR은 제외한다.
- GET /config는 편집 가능한 현재 설정을 반환한다. PATCH /config의 settings 객체로 현재 모드·계정을 유지한 채 설정을 부분 적용한다. 모든 변경 요청은 현재 session_id를 필수로 포함한다. API와 환경변수는 같은 값 검증 규칙을 사용한다.
- 취소/Escape는 변경하지 않는다. 적용 시 기존 source와 필요 시 queue consumer를 정리하고, 새 설정으로 큐·수신을 재시작한다. 댓글은 새 세션 경계에서 비운다.
- status.comment_history_size로 모든 브라우저의 보관량을 동기화한다. 설정 변경은 메모리 전용이며 백엔드 재시작 후 환경변수 초기값으로 복원된다.

## 재연결 후 댓글 범위

- 다시 연결하면 기존 댓글을 비우고 이후 수신 댓글만 표시한다. TikTokLive 접속 초기 이벤트는 처리하지 않는다.
- 데모 재연결은 생성 순번을 처음으로 되돌리지 않는다. 샘플 문구가 반복되어도 데모 순번으로 새 댓글을 구별한다. 순번은 프로세스 메모리에만 유지한다.


## 백엔드 안정화
- 단일 MonitorService가 세션 전환과 수신/소비/감시 태스크를 소유한다. 검증 결과와 남은 외부 검증은 `VALIDATION.md`를 참고한다.
- 시작은 idle에서만 허용한다. 재연결은 POST /refresh, 설정 변경은 PATCH /config, 종료는 DELETE /account로 구분한다.
- 현재 session_id와 불일치한 요청은 상태를 변경하지 않고 409를 반환한다.
- 이전 수신 시도의 늦은 이벤트는 EventSink에서 차단한다. 종료를 거부하는 작업이 남으면 새 연결을 시작하지 않는다.
- HTTP Host와 변경 요청 Origin, WS Origin을 검사한다. WS Origin은 필수다.
- 순간 배치에서도 송신 기회를 보장한다. 실제 지연/큐 초과인 브라우저만 독립적으로 닫는다.
- 내부 작업 장애는 health 503과 오류 상태로 알리고 자동 재시도한다. 종료 시간 초과는 명시적 서버 재시작 대상이다.
- 수신 큐 1–10,000개, 댓글 본문 10,000자, 이름/아이디 256자, 브라우저 16개, 대기 변경 요청 16개로 제한한다.
- DEBUG는 앱 로거에만 적용하고 외부 예외 본문·payload를 로그에 남기지 않는다.


## 프론트엔드 읽기·복구 개선 (2026-09-15)

- 검증 결과와 성능 측정은 `VALIDATION.md`를 참고한다.
- 댓글과 활동은 보관 수를 공유한다. 손상된 선택적 사진·배지는 제거하고 유효한 댓글을 유지한다.
- 위로 이동하면 읽던 항목의 위치를 보존하며 최신 이동 버튼과 키보드 조작을 제공한다. 보관 상한은 읽는 동안에도 유지한다.
- 첫 화면에서도 테마를 바꿀 수 있다. 테마와 20–200%/5% 단위 글자 배율만 브라우저에 저장한다.
- 설정은 기본과 고급 항목으로 나누고 모드·아이디는 첫 화면에서만 바꾼다.
- HTTP 변경 응답이 불확실하면 상태 조회로 확인한다. 댓글 목록의 세션 경계는 WebSocket만 적용한다.
- 수신 댓글은 프레임마다 묶어 반영하고, 숨겨진 탭의 대기 배치도 보관 수 이내로 제한한다. 새 세션에서는 대기 배치를 지운다.

## 프론트엔드 책임 분리

- `+page.svelte`는 화면 조립, 설정창 열림·글자 배율, 시작·종료 후 포커스 전환만 담당한다. 폼의 입력 초안과 오류는 `AccountSetup`, 설정 초안은 `SettingsDialog`가 소유한다.
- `MonitorHeader`, `LiveSummary`, `RequestFeedback`은 필요한 값과 콜백을 받는다. 페이지가 자식 DOM을 전역 검색하지 않으며 포커스 대상은 해당 컴포넌트가 관리한다.
- `lib/monitor/session.svelte.ts`는 WebSocket 상태·수신 순서·보관 상한·프레임 배치와 세션 경계를, `commands.svelte.ts`는 명시적인 변경 동작과 불확실한 응답의 결과 확인을 담당한다.
- 상태는 페이지별 인스턴스로 생성한다. 페이지 종료 시 연결, 요청, 재확인 타이머, 예약 프레임을 정리하며 전역 싱글턴을 두지 않는다.
- 테마·리셋·reduced motion만 전역 CSS로 유지하고 화면 영역과 댓글 스타일은 담당 컴포넌트에 둔다. 기능·디자인·API 계약은 유지한다.
