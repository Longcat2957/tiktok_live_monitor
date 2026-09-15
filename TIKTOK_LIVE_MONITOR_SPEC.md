# TikTok LIVE 세로형 댓글 모니터 — Codex 구현 명세서

> 이 문서는 구현 담당 Codex에게 그대로 전달하는 프로젝트 명세서다. 아래의 목표, 범위, 기술 선택, 제약사항과 완료 조건을 기준으로 실제 동작하는 저장소 전체를 작성하라. 설명용 의사 코드만 만들지 말고, 설치·개발·빌드·배포·자동 실행까지 가능한 결과물을 완성하라.

## 1. 프로젝트 목적

TikTok LIVE 방송 중 들어오는 **모든 일반 댓글을 수신 순서대로** 큰 글씨로 표시하는 전용 모니터를 만든다.

장비는 Raspberry Pi 4이며 모니터를 물리적으로 세로로 세운다. Raspberry Pi OS에서 화면 출력을 90도 회전하여 브라우저에는 약 `1080 × 1920` 크기의 세로 viewport가 제공된다고 가정한다.

최종 사용자는 키보드나 마우스를 조작하지 않는다. 장비에 전원을 넣으면 백엔드와 전체화면 브라우저가 자동으로 실행되고, 방송 댓글 화면이 나타나야 한다.

핵심 사용자 경험은 다음과 같다.

1. Raspberry Pi 전원을 켠다.
2. 네트워크가 연결된다.
3. 댓글 수신 서비스가 자동으로 실행된다.
4. Chromium이 kiosk 모드로 자동 실행된다.
5. TikTok LIVE가 시작되거나 연결 가능해지면 댓글이 자동으로 나타난다.
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

### MVP에서 제외할 기능

- 댓글 분류, 질문 탐지, 키워드 필터링
- LLM 또는 AI 기능
- 데이터베이스와 댓글 영구 저장
- Redis 및 외부 메시지 큐
- 사용자 로그인과 권한 관리
- 운영자용 대시보드
- 좋아요, 선물, 팔로우 등 댓글 외 이벤트 표시
- 프로필 사진, 배지, 애니메이션 중심 UI
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
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models.py
│   │   ├── websocket.py
│   │   └── sources/
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── tiktok.py
│   │       └── mock.py
│   ├── tests/
│   │   ├── test_health.py
│   │   └── test_websocket.py
│   ├── pyproject.toml
│   ├── uv.lock
│   └── .python-version
├── frontend/
│   ├── src/
│   │   ├── app.html
│   │   ├── app.css
│   │   ├── lib/
│   │   │   ├── components/
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

구현 도중 더 좋은 이유가 있으면 작은 구조 변경은 가능하지만, 백엔드·프론트엔드·배포 파일의 책임은 명확히 분리한다.

## 6. 환경 설정

루트 `.env.example`에 최소한 다음 값을 둔다.

```dotenv
TIKTOK_USERNAME=@example_account
COMMENT_SOURCE=tiktok
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
- `COMMENT_SOURCE=mock`이면 TikTok 연결 없이 가짜 댓글을 주기적으로 생성한다.
- 누락되거나 잘못된 환경값은 조용히 무시하지 말고 시작 시 이해 가능한 오류를 출력한다.
- `TIKTOK_USERNAME`의 `@` 유무는 내부에서 정규화한다.
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
- 과도한 그림자, 카드 장식, 프로필 이미지, 복잡한 애니메이션 제외
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
- `COMMENT_SOURCE=mock`으로 실제 TikTok 방송 없이 전체 흐름을 시험할 수 있어야 한다.

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
- `.env`가 없을 때 `.env.example` 복사 후 사용자에게 수정 필요 안내
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

1. `COMMENT_SOURCE=mock`으로 실행하면 별도 조작 없이 댓글이 계속 표시된다.
2. 브라우저 개발자 도구에서 WebSocket 연결을 끊으면 상태가 변경되고 자동 재연결된다.
3. backend 컨테이너를 재시작해도 kiosk 페이지를 새로고침하지 않고 다시 댓글을 받는다.
4. 한글, 영문, 이모지, 매우 긴 댓글이 화면 밖으로 가로 overflow되지 않는다.
5. 1080 × 1920 및 720 × 1280 viewport에서 최신 댓글과 상태 표시가 겹치지 않는다.
6. 수 시간 mock 부하 후 DOM 댓글 수와 메모리 사용량이 계속 증가하지 않는다.
7. Raspberry Pi 재부팅 후 Compose 컨테이너와 Chromium kiosk가 자동으로 복구된다.
8. 실제 TikTok LIVE에서 댓글 순서와 닉네임/본문이 정상 표시된다.

## 13. 완료 조건

다음 조건을 모두 만족해야 구현 완료로 간주한다.

- 저장소의 모든 필수 파일에 실제 구현이 들어 있다.
- placeholder, TODO-only 파일, 동작하지 않는 의사 코드를 남기지 않는다.
- `.env.example`만 수정하면 TikTok 계정을 바꿀 수 있다.
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
