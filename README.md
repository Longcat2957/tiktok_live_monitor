# TikTok LIVE 세로형 댓글 모니터

**v1.0.0** · Raspberry Pi 4 / Raspberry Pi OS Desktop 64-bit

한 계정의 TikTok LIVE 댓글과 선물·팔로우·공유·구독 알림을 수신 순서대로 표시합니다. 세로 화면, 자동 재연결, 실방송 없이 실행하는 데모를 지원합니다. 댓글은 저장하지 않습니다.

## 빠른 실행

Docker Engine과 Compose plugin이 필요합니다.

```bash
git clone --branch main https://github.com/Longcat2957/tiktok_live_monitor.git
cd tiktok_live_monitor
./scripts/start.sh
```

`http://127.0.0.1:8000`에서 **실제 방송** 또는 **데모 체험**을 선택하고 시작합니다. 공개 Docker Hub 이미지를 사용하며 `.env`가 없으면 기본 파일을 생성합니다. Pi 64-bit에는 ARM64 이미지가 선택됩니다.

## 주요 명령

| 용도 | 명령 |
| --- | --- |
| Pi 설치·kiosk 자동 실행 설정 | `./scripts/install.sh` |
| 운영 이미지 다운로드·실행 | `./scripts/start.sh` |
| 소스와 운영 이미지 업데이트 | `./scripts/update.sh` |
| 로컬 소스로 빌드·실행 | `./scripts/start.sh --build` |
| 개발 서버·브라우저 실행 (`dev`) | `./scripts/dev.sh` |
| 로그 확인 | `docker compose logs --tail=100 app` |
| 중지 | `docker compose stop` |

설치·업데이트에도 `--build`를 사용할 수 있습니다. 상세 옵션은 각 스크립트의 `--help`를 참고하세요. 운영은 단일 컨테이너·non-root·localhost 접속이며 Chromium은 호스트에서 실행합니다.

## CI

| 브랜치 | 자동 실행 |
| --- | --- |
| `dev` | Frontend CI와 Backend CI 각각 검사·테스트 |
| `main` | AMD64/ARM64 Docker 빌드·검증 및 Docker Hub 발행 |

[Docker Hub 이미지](https://hub.docker.com/r/longcat1132/tiktok-live-monitor)는 `latest`와 커밋별 SHA 태그를 제공합니다. CI를 건너뛴 문서·스크립트 커밋에는 새 이미지가 발행되지 않습니다.

## 문서

- [Pi 설치·배포·업데이트](docs/installation-deploy.md)
- [개발 환경·실행·테스트](docs/installation-dev.md)
- [기능·API·CI 설정·장애 진단](docs/reference.md)
- [프로젝트 명세](TIKTOK_LIVE_MONITOR_SPEC.md) · [검증 기록](VALIDATION.md)
