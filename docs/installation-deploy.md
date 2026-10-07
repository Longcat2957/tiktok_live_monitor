# 배포 환경 설치 가이드

Raspberry Pi 4 + Raspberry Pi OS Desktop 64-bit용입니다. 아래 명령은 Pi에서 실행합니다. 개발 환경은 [별도 가이드](installation-dev.md)를 참고하세요.

## 1. 배포 구조와 준비물

- 인터넷에 연결된 Pi 4, 세로 모니터, 키보드·마우스 또는 터치 입력, Desktop 사용자 계정이 필요합니다.
- Docker Compose가 FastAPI와 빌드된 Svelte UI를 컨테이너 하나로 실행합니다.
- Chromium은 호스트에서 실행하며 `http://127.0.0.1:8000`에 접속합니다. 다른 PC에서 Pi의 IP로 접근하는 구성은 아닙니다.
- 기본 설치는 공개 Docker Hub의 `longcat1132/tiktok-live-monitor:latest`를 다운로드합니다. Pi 64-bit에는 ARM64 이미지가 선택되며 Docker Hub 로그인은 필요 없습니다. 호스트에 Python/uv/Node/pnpm을 설치할 필요도 없습니다.
- GitHub Actions는 `dev`에서 Frontend CI·Backend CI로 코드·브라우저 테스트를 각각 실행합니다. `main`의 Docker CI는 AMD64/ARM64 운영 컨테이너 빌드·실행을 검증한 뒤 이미지를 발행합니다. Pi에서는 설치·업데이트 스크립트를 직접 실행합니다. [태그와 CI 설정](reference.md#github-actions-ci)을 참고하세요.
- 필요한 경우 `--build`로 현재 소스를 Pi에서 직접 빌드할 수 있습니다.
- 댓글과 안전한 백엔드 진단은 SQLite에 저장합니다. 컨테이너는 non-root, 읽기 전용 루트 파일시스템으로 실행하고 `/data`만 영속 named volume에 연결합니다.

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
git clone --branch main https://github.com/Longcat2957/tiktok_live_monitor.git ~/tiktok_live_monitor
cd ~/tiktok_live_monitor
./scripts/install.sh
```

설치 스크립트는 Docker/Compose/Chromium/labwc와 권한을 확인하고, Docker 부팅 시작, 이미지 다운로드, Compose healthy 대기, labwc autostart 등록을 수행합니다. `.env`가 없으면 기본값으로 만들고 같은 실행에서 설치를 완료합니다. 설정을 먼저 바꾸려면 `.env.example`을 `.env`로 복사해 수정한 뒤 실행하세요. 기존 `.env`는 보존하며 방송·데모는 화면에서 선택합니다.

전체 스크립트를 sudo로 실행하지 마세요. 기존 labwc autostart는 타임스탬프 백업을 남기고 마지막에 실행 항목을 추가합니다. 사용자 autostart에는 앱 실행 항목만 추가합니다. Pi의 `labwc-pi`는 시스템과 사용자 설정을 함께 실행하므로 시스템 autostart를 복사하면 작업 표시줄 등 Desktop 프로그램이 중복 실행됩니다. 반복 실행 시 같은 항목을 중복 추가하지 않습니다. 저장소 경로를 옮겼다면 autostart의 기존 경로도 변경하세요.

5. `sudo raspi-config`에서 Desktop 자동 로그인을 활성화하고 화면 blanking을 비활성화합니다. Wayland/labwc Desktop 세션을 사용합니다. 자동 로그인 사용자는 설치 스크립트를 실행한 사용자와 같아야 합니다.
6. Desktop의 디스플레이 설정(버전에 따라 Screen Configuration 또는 Control Centre → Screens)에서 HDMI 출력 방향을 **90도 또는 270도**로 변경하고 적용·저장합니다. CSS 회전은 없습니다. 1080×1920 viewport가 나오도록 모니터 설치 방향에 맞춰 선택합니다. [Raspberry Pi 디스플레이 설정 문서](https://www.raspberrypi.com/documentation/computers/configuration.html)를 참고하세요.
7. 재부팅합니다. Docker가 기존 컨테이너를 복구하고 labwc 로그인 후 kiosk가 실행됩니다. health와 UI 응답을 기다리므로 서비스 준비나 네트워크 복구에 시간이 걸려도 3초 간격으로 계속 대기합니다. 대기 로그는 30초 간격입니다.

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

`app`이 healthy이면 Pi 브라우저에서 **데모 체험 → 시작**을 눌러 댓글을 확인합니다.

실제 방송은 **모니터 종료 · 처음으로 → 실제 방송**을 선택하고 @아이디 또는 TikTok 프로필·LIVE 주소를 입력한 뒤 시작합니다. `.env` 변경이나 컨테이너 재시작은 필요하지 않습니다. 개발·운영 모두 같은 앱이며 데모 전용 서버나 이미지가 따로 있지 않습니다. 기존 `.env`의 `COMMENT_SOURCE`는 사용하지 않으므로 삭제하세요.

시작 전에는 정상 대기(`idle`)하며, 실제 방송이 꺼져 있으면 방송 시작을 기다립니다. 선택값은 메모리에만 유지되므로 백엔드 재시작 후에는 첫 화면에서 다시 시작해야 합니다. 암호나 세션 쿠키는 필요하지 않습니다.

## 4. 업데이트와 운영

방송이 끝난 뒤 실행하세요. 로컬 변경이 있다면 먼저 커밋하거나 별도로 보관합니다. GitHub에서 dev의 Frontend CI·Backend CI와 발행 대상 main의 Docker CI 결과를 확인하세요. 스크립트가 CI 통과 여부를 대신 검사하지는 않습니다.

```bash
cd ~/tiktok_live_monitor
./scripts/update.sh
```

스크립트는 현재 브랜치의 upstream에서 `git pull --ff-only`로 소스를 받은 뒤 `start.sh`로 운영 이미지를 다운로드하고 컨테이너를 교체하며 최대 120초 동안 healthy를 기다립니다. 일반 설치의 upstream은 `origin/main`입니다. 어느 디렉터리에서든 스크립트의 절대 경로로 실행할 수 있습니다. `--help`로 사용법을 확인합니다.

기본 `latest`는 마지막으로 발행에 성공한 이미지입니다. 문서·스크립트 커밋에 `[skip ci]`를 사용하면 소스의 최신 커밋과 이미지의 발행 커밋이 다를 수 있습니다. 스크립트는 현재 Git HEAD의 이미지 태그를 만들어 조회하지 않습니다.

- 미커밋 변경(추적하지 않는 파일 포함), `.env` 누락, upstream 미설정, Git 이력 분기가 있으면 배포를 중단합니다. 자동 stash·reset·merge는 하지 않습니다.
- Git에서 제외된 `.env`는 보존합니다. 다운로드·빌드 실패 시 기존 컨테이너를 교체하지 않으며, 소스는 이미 새 커밋으로 이동했을 수 있습니다.
- 교체 중에는 잠시 연결이 끊기며 UI가 자동 재연결합니다. 운영 화면은 30초마다 UI 빌드 버전을 확인하고 새 버전일 때만 페이지를 다시 불러옵니다. 서버 단절·버전 확인 실패·같은 버전에는 새로고침하지 않습니다. 이 기능이 없는 구버전 화면은 최초 한 번 Chromium에서 **Ctrl+Shift+R**로 새로고침하세요. 컨테이너가 교체됐다면 첫 화면에서 모드·계정을 선택하고 다시 시작합니다.
- healthy 확인 실패는 오류로 종료합니다. 자동 롤백은 없으므로 로그를 확인하고 원인을 해결한 뒤 다시 실행합니다.
- healthy 확인에 성공한 뒤 이 앱의 라벨(`org.opencontainers.image.title=tiktok-live-monitor`)이 붙은 태그 없는 미사용 이미지를 정리합니다. 라벨 도입 전 이미지도 이번 교체 직전에 앱이 사용하던 이미지라면 태그가 없을 때 삭제를 시도합니다. 이전 이미지가 조회되지 않으면 삭제를 건너뜁니다. 컨테이너가 사용하는 이미지와 별도 태그로 보관한 이미지는 유지합니다. 다운로드·빌드·health 실패 시에는 정리하지 않습니다.
- 마지막에 `docker system df`로 이미지·컨테이너·볼륨·빌드 캐시 사용량을 출력합니다. 공유 빌드 캐시, 다른 앱의 이미지, 볼륨, 소스·`.env`·Chromium 프로필은 자동 삭제하지 않습니다. 더 오래된 무라벨 이미지도 소유자를 확정할 수 없어 자동 삭제하지 않습니다. 정리 실패는 경고로 표시하며 성공한 배포를 실패로 바꾸지는 않습니다.

기존의 재빌드 전용 `update.sh`를 사용 중이라면 최초 한 번은 `git pull --ff-only`로 새 스크립트를 받아야 합니다. 이후부터는 `./scripts/update.sh`만 실행합니다.

### SQLite 기능의 첫 업데이트

SQLite를 포함한 이미지가 발행된 뒤 기존 `./scripts/update.sh`를 실행하면 됩니다. `install.sh`, `start.sh`, `update.sh`의 명령과 기존 `.env`는 바뀌지 않습니다. 새 Compose는 프로젝트별 `monitor-data` volume을 `/data`에 연결하고, 앱이 최초 실행에서 `/data/monitor.sqlite3`와 스키마를 만듭니다. 이미지의 `/data`는 UID/GID 10001 소유이며 앱도 같은 사용자로 DB와 WAL/SHM 파일을 생성합니다. 기존 설치에는 저장 댓글이 없으므로 과거 댓글은 복구되지 않습니다.

이후 컨테이너 재시작·교체·이미지 정리는 같은 volume의 DB를 유지합니다. 저장소 디렉터리 이름이나 Compose project name을 바꾸면 다른 volume을 사용하므로 기존 project name을 유지하세요. 구 SHA/digest에 고정된 `MONITOR_IMAGE`는 SQLite 기능을 포함한 발행 이미지로 선택해야 합니다. 소스만 새로 받고 구 이미지를 계속 실행하면 이 기능이 생기지 않습니다.

`/health`의 `storage.ready`가 true인지 확인합니다. 디스크 부족·권한·스키마 오류이면 `storage.error`와 안전한 stderr 로그를 확인하고 원인을 해결한 뒤 재시작합니다. 저장 오류에서 앱은 API와 화면을 제공하지만 health는 503이므로 설치/업데이트의 healthy 확인은 실패할 수 있습니다. 자동 롤백·자동 저장 재시도·DB 삭제는 하지 않습니다. `docker compose down --volumes`나 volume prune은 운영 기록을 삭제하므로 사용하지 마세요.

### SQLite 보관과 외부 백업

댓글과 진단은 각각 `comments`, `diagnostics` 테이블에 보관합니다. 데모 댓글은 `source=mock`으로 구별됩니다. 화면의 최근 목록 보관 수, 댓글 비우기·재연결·계정 변경은 DB 기록을 지우지 않습니다. 활동·이미지·배지와 원본 이벤트 payload는 저장하지 않고, 저장 댓글을 브라우저에 replay하지 않습니다. 자동 보관 기한 삭제는 없으므로 `docker system df`와 호스트 디스크 여유 공간을 확인하세요.

저장 큐는 2,000개이고 writer는 최대 100개를 한 transaction으로 저장하며, 부분 batch도 약 1초마다 commit합니다. `/health`의 `storage.queued`는 처리 중인 batch까지 포함하고, 저장·누락 카운터는 현재 프로세스의 누적 수입니다. 강제 종료·전원 차단 시 아직 commit하지 않은 큐와 batch는 남지 않을 수 있습니다.

`diagnostics`의 `pipeline_snapshot`은 30초마다, 수신 작업 종료 전에도 기록합니다. `details` JSON의 수신·상위 메시지 카운터는 worker 시도마다 초기화됩니다. `sent_comments`는 모든 WebSocket 연결의 성공한 댓글 송신을 합산한 프로세스 누적 수이므로 수신 수와 직접 비교하지 않습니다. 마지막 수신·송신 시각과 event ID도 함께 기록하며, 송신 성공은 브라우저 표시 확인을 뜻하지 않습니다. `upstream_messages`는 TikTokLive가 전달한 메시지 관찰 수이며 원시 WebSocket frame·ping·빈 응답이나 모든 upstream 변환 오류를 직접 집계하지 않습니다.

실행 중인 `monitor.sqlite3` 파일을 그대로 복사하면 WAL에 commit된 기록이 빠질 수 있습니다. 다음 명령은 SQLite backup API로 snapshot을 만들고 호스트로 반출합니다. source는 readonly로 열며 기존 destination은 덮어쓰지 않습니다. 수신 중에도 실행할 수 있지만 snapshot에는 생성 시점에 commit된 데이터가 포함됩니다. 파일에는 댓글과 작성자 정보가 있으므로 접근 권한을 제한하세요.

```bash
snapshot_name="monitor-$(date -u +%Y%m%dT%H%M%SZ)-$$.sqlite3"
docker compose exec -T app python -m app.services.archive "/data/$snapshot_name"
docker cp "$(docker compose ps -q app):/data/$snapshot_name" "$snapshot_name"
chmod 600 "$snapshot_name"
```

복사한 파일은 외부 PC의 SQLite 도구에서 열 수 있습니다. 복사가 성공한 뒤 임시 snapshot 하나만 제거하려면 `docker compose exec -T app rm -- "/data/$snapshot_name"`을 실행합니다. 원본 `/data/monitor.sqlite3`와 volume은 삭제하지 않습니다. snapshot은 DB 크기만큼 추가 디스크 공간을 사용하므로 여유 공간을 확인하고, 64MiB tmpfs인 `/tmp`에는 큰 DB를 백업하지 않습니다. 오래된 기록의 보관 여부는 외부에서 결정합니다.

시간/하루 조회는 한국 시간의 시작과 종료를 UTC로 변환한 `[시작, 종료)` 범위를 사용합니다. 한국 시간 2026-10-07 하루는 UTC 2026-10-06 15:00부터 2026-10-07 15:00 미만입니다. 외부 snapshot에서 다음과 같이 조회하고 `id`로 수신 순서를 정렬합니다.

```sql
SELECT id, received_at, source, username, nickname, user_id, comment
FROM comments
WHERE received_at >= '2026-10-06T15:00:00.000+00:00'
  AND received_at < '2026-10-07T15:00:00.000+00:00'
ORDER BY id;
```

프로그램에서 범위를 만들 때는 `datetime(2026, 10, 7, tzinfo=ZoneInfo("Asia/Seoul")).astimezone(UTC).isoformat(timespec="milliseconds")`처럼 timezone-aware 값을 사용하고 DB와 같은 밀리초 UTC ISO 문자열로 바꿉니다. naive 시각이나 호스트 timezone에 맡기지 않습니다. 한 시간 조회도 같은 방식으로 시작/종료만 정하며 DB를 시간별 파일로 회전할 필요는 없습니다. `diagnostics.occurred_at`에도 동일한 범위 조건을 적용할 수 있습니다.

### 직접 실행, 버전 고정과 로컬 빌드

Docker만 사용하는 호스트에서는 `./scripts/start.sh`로 이미지 다운로드·실행을 할 수 있습니다. Pi의 Desktop 자동 실행 설정은 `install.sh`가 담당합니다.

발행된 특정 버전을 유지하려면 `.env`의 `MONITOR_IMAGE`를 전체 커밋 SHA 태그 또는 이미지 digest로 지정합니다. 예를 들어 v1.0.0 소스의 발행 이미지는 다음과 같습니다.

```dotenv
MONITOR_IMAGE=longcat1132/tiktok-live-monitor:sha-ae78f7a27796f6187fcdb9ef70a1c64be1ff502e
```

수정 후 `./scripts/start.sh`로 적용합니다. 고정 중에는 `update.sh`도 같은 이미지를 사용합니다. 최신 발행 이미지를 다시 받으려면 값을 `longcat1132/tiktok-live-monitor:latest`로 되돌리세요.

현재 소스를 직접 빌드하려면 다음 명령을 사용합니다. 기본 로컬 태그는 `tiktok-live-monitor:local`이며 `.env`의 운영 이미지 지정은 유지합니다.

```bash
./scripts/build.sh          # 빌드만 수행
./scripts/start.sh --build  # 빌드 후 실행
./scripts/install.sh --build # Pi 자동 실행 설치까지 수행
./scripts/update.sh --build # Git 업데이트 후 빌드·실행
```

별도 로컬 태그가 필요하면 `MONITOR_IMAGE=tiktok-live-monitor:custom ./scripts/start.sh --build`처럼 셸 환경변수로 지정합니다. 로컬 빌드는 의존성·기본 이미지 다운로드에 네트워크가 필요할 수 있습니다.

### 작업 표시줄이 두 개 뜨는 구버전 설치 복구

구버전 설치 스크립트가 복사한 시스템 autostart 때문에 발생할 수 있습니다. 새 설치·업데이트 스크립트는 앱 표시가 있는 사용자 autostart의 시작 부분이 현재 시스템 파일과 정확히 같을 때만 백업 후 그 복사본을 제거합니다. 앱과 추가 사용자 명령은 유지합니다. 수정된 소스를 받은 뒤 Docker 재빌드 없이 복구만 실행할 수도 있습니다.

```bash
cd ~/tiktok_live_monitor
bash deploy/repair-autostart.sh
```

복구 메시지가 나오면 방송 종료 후 로그아웃·로그인하거나 재부팅하세요. 이미 실행된 작업 표시줄은 설정 수정만으로 종료되지 않습니다. OS 업데이트나 직접 편집으로 두 파일의 내용이 달라졌다면 자동 수정하지 않습니다. 이 경우 `~/.config/labwc/autostart`를 백업한 뒤 `/etc/xdg/labwc/autostart`와 비교하여 중복된 Desktop 실행 명령만 제거하고 앱 실행 항목과 사용자 설정은 보존하세요.

### 운영 명령

```bash
docker compose ps
docker compose logs --tail=100 app
docker compose restart app
curl --fail http://127.0.0.1:8000/health
tail -f ~/.local/state/tiktok-live-monitor/kiosk.log
```

수동 중지에는 `docker compose stop`을 사용합니다. 이미 내려받은 운영 이미지를 네트워크 접속 없이 다시 실행하려면 다음 명령을 사용합니다.

```bash
docker compose up -d --no-build --pull never --wait --wait-timeout 120
```

로컬 빌드 이미지를 다시 실행할 때는 앞에 `MONITOR_IMAGE=tiktok-live-monitor:local`을 붙입니다. 수동 중지한 컨테이너는 재부팅만으로 복구되지 않습니다. `unless-stopped`는 프로세스 종료를 복구하며 unhealthy 판정만으로 재시작하지 않습니다.

설치/업데이트가 실패하면 최초 오류와 `docker compose logs --tail=100 app`을 확인합니다. Docker 권한 변경 후에는 다시 로그인하고, Chromium은 Desktop 세션에서 실행하세요. 더 자세한 진단은 [장애 진단](reference.md#장애-진단)을 참고하세요.

## 5. 현장 인수 확인

- 전원을 다시 켜면 Desktop 자동 로그인, 컨테이너, Chromium kiosk가 복구되는지 확인합니다.
- 화면 회전과 절전 설정이 유지되고 댓글/상태 표시가 겹치지 않는지 확인합니다.
- 컨테이너 재시작 후 새로고침 없이 첫 화면으로 돌아가며, 시작을 누르면 댓글이 다시 들어오는지 확인합니다.
- 실제 TikTok LIVE에서 닉네임과 댓글 순서를 확인합니다.

기존 [검증 기록](../VALIDATION.md)은 x86 Docker와 mock 동작 기준입니다. CI는 AMD64·ARM64 컨테이너를 각각 검증합니다. 실제 Pi 장비 실행, 전원 재인가 자동 복구, 실제 LIVE 수신은 현장에서 별도 검증해야 합니다.
