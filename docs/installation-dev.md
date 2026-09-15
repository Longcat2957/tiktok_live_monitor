# 개발 환경 설치 가이드

통합 실행 스크립트는 Linux 데스크톱의 Bash 기준입니다. macOS에서는 아래 수동 실행 절차를 사용하세요. WSL2/SSH처럼 그래픽 환경이 없는 경우 서버만 실행할 수 있습니다. Docker나 TikTok 인증 정보는 필요하지 않습니다.

## 1. 개발 도구 설치

| 도구 | 프로젝트 기준 |
| --- | --- |
| Git, curl | 저장소 복제와 설치 파일 다운로드 |
| Python | 3.11 (`uv sync`가 필요 시 설치) |
| uv | CI 검증 버전 0.12.8 |
| Node.js | 22.20.0 (CI와 동일) |
| pnpm | 10.20.0 (`frontend/package.json`에 지정) |

Git/curl은 OS 패키지 관리자로 설치합니다. 이미 사용 중인 uv와 프로젝트 버전에 맞는 Node.js/pnpm이 있다면 해당 설치 단계는 건너뛰세요.

### 백엔드: uv

uv는 Python 버전, 가상환경, Python 패키지를 관리합니다. 아직 없다면 [공식 설치 스크립트](https://docs.astral.sh/uv/getting-started/installation/)로 설치합니다.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

기본 설치 경로에서는 다음 명령으로 현재 터미널의 PATH를 적용하고 설치를 확인합니다. 설치 경로를 따로 지정했다면 설치기가 출력한 안내를 따르세요.

```bash
. "$HOME/.local/bin/env"
uv --version
```

Python은 아래 `uv sync --locked` 단계에서 `backend/.python-version`의 3.11에 맞춰 준비됩니다. 사용할 Python이 없으면 uv가 다운로드하므로 별도 Python 설치 명령은 필요하지 않습니다. [uv의 자동 Python 다운로드](https://docs.astral.sh/uv/guides/install-python/#automatic-python-downloads)

### 프론트엔드: Node.js와 pnpm

[Node.js 공식 다운로드](https://nodejs.org/en/download)에서 22.20.0을 선택해 설치한 뒤 새 터미널을 엽니다. Node.js와 함께 제공되는 npm으로 pnpm을 설치합니다. [pnpm 10 공식 npm 설치 방식](https://pnpm.io/10.x/installation#using-npm)

```bash
node --version
npm --version
npm install --global pnpm@10.20.0
pnpm --version
```

`pnpm --version`이 `10.20.0`인지 확인합니다. Corepack으로 이미 이 버전을 사용 중이라면 그대로 사용하면 됩니다. npm 전역 설치에서 `EACCES`가 발생하면 사용자 계정에서 관리하는 Node.js 설치 환경을 사용하세요.

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

### 한 번에 실행 + Chromium 자동 열기

Linux 데스크톱 터미널에서 실행합니다. `uv`, `pnpm`, Node.js 외에 `curl`, `setsid`(util-linux), Chromium이 필요합니다. Raspberry Pi OS/Debian에서 Chromium이 없다면 `sudo apt install chromium`으로 설치하세요.

```bash
cd ~/tiktok_live_monitor
./scripts/dev.sh
```

스크립트는 다음 순서로 실행합니다.

1. `uv sync --locked`, `pnpm install --frozen-lockfile`로 의존성을 준비합니다. 최초 실행에는 네트워크가 필요할 수 있습니다.
2. 백엔드를 `127.0.0.1:8000`에서 자동 reload로, 프론트엔드를 `127.0.0.1:5173`에서 Vite 개발 모드로 실행합니다.
3. 서버 응답과 Vite의 백엔드 proxy 응답을 확인한 뒤 Chromium으로 `http://127.0.0.1:5173`을 엽니다.

기본값은 **mock**이며 `.env`의 `COMMENT_SOURCE`보다 우선합니다. 가짜 댓글이 계속 나타납니다. `.env`가 없어도 기본 설정으로 실행됩니다. 스크립트는 어느 디렉터리에서든 절대 경로로 호출할 수 있습니다.

로그는 실행한 터미널에 표시됩니다. **`Ctrl+C`를 누르면 두 서버와 전용 Chromium을 함께 종료**합니다. Chromium은 임시 프로필을 사용하며 정상 종료 시 삭제합니다. 브라우저 창만 닫으면 서버는 계속 실행됩니다. 개발용 일반 창이므로 개발자 도구도 사용할 수 있습니다.

실제 방송을 연결하려면 계정을 `.env`에 설정하고 명시적으로 실행합니다.

```bash
COMMENT_SOURCE=tiktok ./scripts/dev.sh
```

Chromium 경로를 직접 지정하거나 브라우저 없이 실행할 수도 있습니다.

```bash
CHROMIUM_BIN=/usr/bin/chromium ./scripts/dev.sh
DEV_OPEN_BROWSER=0 ./scripts/dev.sh
```

서버만 실행한 경우 브라우저에서 `http://127.0.0.1:5173`을 직접 여세요. 원격 SSH에서는 localhost 포트 전달이 필요합니다. 포트 8000 또는 5173이 이미 사용 중이면 스크립트는 중단합니다. 기존 개발 서버를 종료한 뒤 다시 실행하세요. 서버가 종료되거나 준비에 60초 넘게 걸리면 함께 실행한 프로세스를 정리합니다.

### 터미널을 나누어 수동 실행

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
