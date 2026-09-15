# 배포 환경 설치 가이드

Raspberry Pi 4 + Raspberry Pi OS Desktop 64-bit용입니다. 아래 명령은 Pi에서 실행합니다. 개발 환경은 [별도 가이드](installation-dev.md)를 참고하세요.

## 1. 배포 구조와 준비물

- 인터넷에 연결된 Pi 4, 세로 모니터, Desktop 사용자 계정이 필요합니다.
- Docker Compose가 FastAPI와 빌드된 Svelte UI를 컨테이너 하나로 실행합니다.
- Chromium은 호스트에서 실행하며 `http://127.0.0.1:8000`에 접속합니다. 다른 PC에서 Pi의 IP로 접근하는 구성은 아닙니다.
- Pi가 소스를 직접 빌드합니다. 호스트에 Python/uv/Node/pnpm을 설치할 필요는 없습니다.
- GitHub Actions는 테스트만 수행합니다. 이미지 레지스트리나 자동 배포는 사용하지 않습니다.
- 댓글은 영구 저장하지 않습니다. 컨테이너는 non-root, 읽기 전용 루트 파일시스템으로 실행됩니다.

## 2. 장비 설치

1. Raspberry Pi Imager로 **Raspberry Pi OS Desktop 64-bit**를 설치합니다. Wi-Fi/유선 네트워크와 Desktop 사용자를 설정합니다. Pi 4 RAM 4GB, 정상 전원 공급장치를 권장합니다.
2. Pi에서 다음 기본 패키지를 설치합니다.

```bash
sudo apt update
sudo apt install -y ca-certificates curl git chromium fonts-noto-cjk fonts-noto-color-emoji
```

3. Docker 공식 Debian 저장소를 설정합니다. Pi OS 64-bit에는 [Docker Debian 설치 문서](https://docs.docker.com/engine/install/debian/)를 적용합니다. 이미 Docker를 설치했다면 저장소를 중복 설정하지 말고 `docker compose version`부터 확인하세요.

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

로그아웃 후 다시 로그인하고 `docker info`, `docker compose version`을 확인합니다. docker 그룹 권한은 관리자 수준입니다. 운영 호스트에는 uv/Node/pnpm을 별도로 설치할 필요가 없습니다.

4. Desktop에 자동 로그인할 일반 사용자로 저장소를 복제합니다. 이미 복제했다면 `git clone`은 생략합니다.

```bash
git clone https://github.com/Longcat2957/tiktok_live_monitor.git ~/tiktok_live_monitor
cd ~/tiktok_live_monitor
./scripts/install.sh
# 최초 실행은 .env를 만들고 종료합니다.
nano .env
# 최초 검증은 COMMENT_SOURCE=mock으로 설정
./scripts/install.sh
```

설치 스크립트는 Docker/Compose/Chromium/labwc와 권한을 확인하고, Docker 부팅 시작, 이미지 빌드, Compose healthy 대기, labwc autostart 등록을 수행합니다. 전체 스크립트를 sudo로 실행하지 마세요. 기존 labwc autostart는 타임스탬프 백업을 남기고 마지막에 실행 항목을 추가합니다. 사용자 autostart가 없으면 시스템 autostart를 먼저 복사해 Desktop 기본 실행 항목을 보존합니다. 반복 실행 시 같은 항목을 중복 추가하지 않습니다. 저장소 경로를 옮겼다면 autostart의 기존 경로도 변경하세요.

5. `sudo raspi-config`에서 Desktop 자동 로그인을 활성화하고 화면 blanking을 비활성화합니다. Wayland/labwc Desktop 세션을 사용합니다. 자동 로그인 사용자는 설치 스크립트를 실행한 사용자와 같아야 합니다.
6. Desktop의 디스플레이 설정(버전에 따라 Screen Configuration 또는 Control Centre → Screens)에서 HDMI 출력 방향을 **90도 또는 270도**로 변경하고 적용·저장합니다. CSS 회전은 없습니다. 1080×1920 viewport가 나오도록 모니터 설치 방향에 맞춰 선택합니다. [Raspberry Pi 디스플레이 설정 문서](https://www.raspberrypi.com/documentation/computers/configuration.html)를 참고하세요.
7. 재부팅합니다. Docker가 기존 컨테이너를 복구하고 labwc 로그인 후 kiosk가 실행됩니다. health와 UI 응답을 기다리므로 초기 빌드나 네트워크 복구에 시간이 걸려도 3초 간격으로 계속 대기합니다. 대기 로그는 30초 간격입니다.

수동 kiosk 확인:

```bash
cd ~/tiktok_live_monitor
./deploy/wait-for-app.sh
```

SSH만 있는 세션에서는 GUI 환경변수가 없으므로 Desktop 터미널에서 실행합니다. Chromium은 호스트에서 실행하며 컨테이너에는 넣지 않습니다. `chromium`과 `chromium-browser`를 자동 탐색하고 독립 프로필을 사용합니다. 브라우저를 직접 강제 종료한 경우에는 스크립트를 다시 실행하거나 재로그인합니다. 서버 단절은 페이지 안에서 자동 복구합니다.

## 3. 설치 확인과 실제 계정 전환

```bash
cd ~/tiktok_live_monitor
docker compose ps
curl --fail http://127.0.0.1:8000/health
curl --fail --output /dev/null http://127.0.0.1:8000/
```

`app`이 healthy이고 Pi 브라우저에서 mock 댓글이 표시되는지 확인합니다. `.env`를 다음처럼 바꾸면 실제 방송에 연결합니다.

```dotenv
COMMENT_SOURCE=tiktok
TIKTOK_USERNAME=@실제계정아이디
```

```bash
docker compose up -d --wait
```

환경값 변경은 컨테이너 재생성이 필요하므로 `restart`만으로 적용되지 않습니다. 방송이 꺼져 있으면 대기 상태가 정상입니다. 암호나 세션 쿠키는 필요하지 않습니다.

## 4. 업데이트와 운영

로컬 변경이 있다면 먼저 커밋하거나 보관합니다. GitHub의 해당 커밋 CI가 통과했는지 확인한 뒤 실행하세요.

```bash
cd ~/tiktok_live_monitor
git pull --ff-only
./scripts/update.sh
```

업데이트 스크립트는 이미지를 빌드하고 컨테이너를 교체한 다음 최대 120초 동안 healthy를 기다립니다. Git pull은 스크립트가 대신 수행하지 않습니다. 교체 중에는 잠시 연결이 끊기며 UI가 자동 재연결합니다.

```bash
docker compose ps
docker compose logs --tail=100 app
docker compose restart app
curl --fail http://127.0.0.1:8000/health
tail -f ~/.local/state/tiktok-live-monitor/kiosk.log
```

수동 중지에는 `docker compose stop`, 재시작에는 `docker compose up -d --wait`를 사용합니다. 수동 중지한 컨테이너는 재부팅만으로 복구되지 않습니다. `unless-stopped`는 프로세스 종료를 복구하며 unhealthy 판정만으로 재시작하지 않습니다.

설치/업데이트가 실패하면 최초 오류와 `docker compose logs --tail=100 app`을 확인합니다. Docker 권한 변경 후에는 다시 로그인하고, Chromium은 Desktop 세션에서 실행하세요. 더 자세한 진단은 [README의 장애 진단](../README.md#장애-진단)을 참고하세요.

## 5. 현장 인수 확인

- 전원을 다시 켜면 Desktop 자동 로그인, 컨테이너, Chromium kiosk가 복구되는지 확인합니다.
- 화면 회전과 절전 설정이 유지되고 댓글/상태 표시가 겹치지 않는지 확인합니다.
- 컨테이너 재시작 후 페이지 새로고침 없이 댓글이 다시 들어오는지 확인합니다.
- 실제 TikTok LIVE에서 닉네임과 댓글 순서를 확인합니다.

기존 [검증 기록](../VALIDATION.md)은 x86 Docker와 mock 동작 기준입니다. 실제 Pi ARM64 빌드·실행, 전원 재인가 자동 복구, 실제 LIVE 수신은 현장에서 별도 검증해야 합니다.
