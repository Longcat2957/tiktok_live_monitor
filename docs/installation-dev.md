# 개발 환경 설치 가이드

Linux/macOS의 Bash 기준입니다. Windows에서는 WSL2 안에서 같은 절차를 사용하세요. 백엔드와 프론트엔드를 각각 실행하며 Docker나 TikTok 인증 정보는 필요하지 않습니다.

## 1. 개발 도구 설치

| 도구 | 프로젝트 기준 |
| --- | --- |
| Git, curl | 저장소 복제와 설치 파일 다운로드 |
| Python | 3.11 (`uv`로 설치) |
| uv | 0.12.8 (CI와 동일) |
| Node.js | 22.20.0 (CI와 동일) |
| pnpm | 10.20.0 (`frontend/package.json`에 지정) |

Git/curl은 OS 패키지 관리자로 설치합니다. [Node.js 공식 다운로드](https://nodejs.org/en/download)에서 22.20.0을 선택해 설치한 뒤 새 터미널을 여세요.

[uv 공식 설치 방식](https://docs.astral.sh/uv/getting-started/installation/)으로 CI와 같은 버전을 설치합니다.

```bash
curl -LsSf https://astral.sh/uv/0.12.8/install.sh | sh
```

설치 안내에 따라 PATH를 적용하거나 터미널을 다시 열고 실행합니다.

```bash
uv python install 3.11
corepack enable
corepack prepare pnpm@10.20.0 --activate
git --version
uv --version
node --version
pnpm --version
```

`corepack enable`에서 권한 오류가 나면 사용자 계정에 설치한 Node.js 환경에서 실행하세요.

## 2. 저장소와 설정 준비

```bash
git clone https://github.com/Longcat2957/tiktok_live_monitor.git ~/tiktok_live_monitor
cd ~/tiktok_live_monitor
test -f .env || cp .env.example .env
```

루트 `.env`를 편집해 다음 값을 설정합니다. 기존 설정 파일은 덮어쓰지 않습니다.

```dotenv
COMMENT_SOURCE=mock
```

mock 모드는 계정이나 진행 중인 방송 없이 댓글을 생성합니다. `.env`는 Git에서 제외되며, 실행 시 셸 환경변수가 `.env`보다 우선합니다.

## 3. 의존성 설치

```bash
cd ~/tiktok_live_monitor/backend
uv sync --locked
cd ../frontend
pnpm install --frozen-lockfile
```

`backend/.venv`는 uv가 관리합니다. 별도로 가상환경을 활성화할 필요는 없습니다. 설치가 lockfile 불일치로 실패하면 오류를 확인하고, 단순 설치 목적으로 lockfile을 삭제하거나 재생성하지 마세요.

## 4. 개발 서버 실행

터미널 1 — 백엔드:

```bash
cd ~/tiktok_live_monitor/backend
COMMENT_SOURCE=mock uv run --locked uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

터미널 2 — 프론트엔드:

```bash
cd ~/tiktok_live_monitor/frontend
pnpm dev --host 127.0.0.1
```

브라우저에서 Vite가 출력한 주소(기본 `http://127.0.0.1:5173`)를 엽니다. 댓글이 계속 추가되고 연결 상태가 표시되면 정상입니다. `/ws`, `/health`, `/config`는 Vite가 백엔드로 전달합니다. 종료는 각 터미널에서 `Ctrl+C`입니다.

```bash
curl --fail http://127.0.0.1:8000/health
```

백엔드 포트 8000이 이미 사용 중이면 기존 프로세스를 확인하거나 백엔드의 `--port`를 바꾸고 프론트엔드를 `BACKEND_URL=http://127.0.0.1:8001 pnpm dev --host 127.0.0.1`처럼 실행합니다. 백엔드 `/`는 정적 빌드가 없으면 UI를 제공하지 않으므로 개발 중에는 Vite 주소를 사용하세요.

## 5. 검사와 빌드

저장소의 최소 CI와 같은 검사입니다.

```bash
cd ~/tiktok_live_monitor/backend
uv run --locked pytest -q
uv run --locked mypy
cd ../frontend
pnpm check
pnpm test
pnpm build
```

브라우저 E2E까지 확인하려면 위 빌드 후 실행합니다. Linux에서는 Playwright가 지원하는 배포판에서 `--with-deps`로 시스템 의존성도 설치할 수 있습니다.

```bash
cd ~/tiktok_live_monitor/frontend
pnpm exec playwright install chromium
pnpm test:e2e
```

E2E는 포트 `18765`에 별도의 mock 백엔드를 실행하고 종료하므로 해당 포트를 비워두세요. 정적 빌드는 `frontend/build`에 생성됩니다. 빌드 후 개발 백엔드를 재시작하면 `http://127.0.0.1:8000`에서도 UI를 확인할 수 있습니다.

## 6. 소스 업데이트

작업 중인 변경을 커밋하거나 보관한 뒤 실행합니다.

```bash
cd ~/tiktok_live_monitor
git pull --ff-only
cd backend
uv sync --locked
cd ../frontend
pnpm install --frozen-lockfile
```

실제 방송을 시험하려면 `.env`의 `COMMENT_SOURCE=tiktok`, `TIKTOK_USERNAME=@실제계정아이디`를 설정하고, 백엔드 실행 명령에서 `COMMENT_SOURCE=mock`을 제거합니다. 실제 장비 설치는 [배포 환경 설치 가이드](installation-deploy.md)를 참고하세요.
