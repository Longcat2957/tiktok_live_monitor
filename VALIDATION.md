# 검증 기록

완료된 백엔드 안정화와 프론트엔드 개선 작업의 검증 기록을 모았다. 아래 결과는 당시 실행 결과이며 현재 커밋에서 재실행한 결과가 아니다. 검사 명령은 [개발 환경 설치 가이드](docs/installation-dev.md#5-검사와-빌드)를 따른다.

## 배포 후 열린 화면 갱신 (2026-09-19)

- 컨테이너 교체 후 WebSocket만 재연결되어 열린 브라우저가 기존 UI 코드를 유지하던 경로를 보완했다. SvelteKit 기본 버전 확인을 30초 간격으로 켜고 새 빌드 감지 시 루트 레이아웃에서 페이지를 다시 불러온다. 구버전 화면에는 최초 한 번 Ctrl+Shift+R이 필요하다.
- 업데이트 스크립트의 이전 이미지 조회 실패는 삭제 대상 없음으로 처리한다. 배포 완료 안내와 설치 문서에 최초 새로고침 절차를 추가했다.
- Frontend lint·format:check·check, 단위 테스트 **44개**, build 통과. 기존 E2E **24개**와 신규 배포 갱신 E2E **1개** 통과: 버전 확인 503·동일 버전에는 갱신하지 않고 새 버전에 한 번 갱신, 서버 세션 보존, 재로딩 반복 없음 확인.
- Backend pytest **42개**, mypy 및 업데이트 스크립트 검사·Ruff·셸 문법·diff 검사 통과.

## 특별 이벤트 UI 강조 (2026-09-19)

- 일반 댓글의 마크업·스타일은 유지했다. `CommentItem.svelte`의 활동 알림에 선물 핑크·팔로우 초록·공유 파랑·구독 보라 배경을 적용하고 본문·작성자 글자를 키웠다. 종류 이름을 유지하며 긴 내용은 줄바꿈한다. 테마·글자 배율은 기존 값을 따른다.
- Frontend lint·format:check·check(오류·경고 0개), 단위 테스트 **44개**, build, E2E **24개** 통과. Backend pytest **42개**, mypy 통과.
- Chromium에서 두 테마, 720px/320px, 글자 배율 100%/200%의 8개 조합을 확인했다. 배경색 네 가지 구분, 일반 댓글보다 큰 이벤트 본문, 텍스트 대비 4.5:1 이상, 긴 작성자 이름의 가로 넘침 없음과 본문 잘림 없음을 확인했다. 두 테마의 화면 캡처도 육안 확인했다.

## 업데이트 후 이미지 정리 (2026-09-19)

- 운영 이미지에 앱 식별 라벨을 추가했다. `update.sh`는 healthy 확인 성공 후에만 이 앱의 태그 없는 미사용 이미지를 정리하며, 라벨 도입 전의 직전 앱 이미지도 태그가 없을 때 강제 옵션 없이 삭제한다. 별도 태그·컨테이너 참조 이미지는 유지하고 공유 빌드 캐시·볼륨은 삭제하지 않는다. 마지막에 `docker system df`를 출력한다.
- 업데이트 검사에 정리 순서, 태그 보존, 이미지 불변·기존 이미지 없음, 사용 중 이미지 삭제 거부·prune 실패 후 배포 성공 유지 검증을 추가했다. `python3 scripts/test-update.py`, 셸 문법, 새 검사 Ruff, `git diff --check` 통과.
- x86_64 운영 이미지 빌드와 앱 식별 라벨·HTTP·정적 파일·mock WebSocket·non-root·read-only·localhost·정상 종료 검증 통과. 다른 앱의 기존 Docker 자원은 정리하지 않았다.

## Pi 업데이트 스크립트 (2026-09-19)

- 기존 재빌드 전용 `scripts/update.sh`에 upstream fast-forward 소스 업데이트, `.env`·작업트리·Docker 사전 검사, 배포 커밋 표시, 빌드·교체·healthy 확인을 연결했다. 로컬 변경을 자동으로 덮어쓰거나 보관하지 않는다.
- `python3 scripts/test-update.py` 통과: 로컬 임시 Git remote/checkout과 가짜 Docker로 도움말·잘못된 인자, untracked/unstaged/staged 변경, `.env` 누락·보존, detached HEAD, 스크립트 자체 업데이트와 새 build.sh 실행, 빌드·health 실패, Git 이력 분기 시 중단을 검증했다. 실제 원격 저장소나 실행 중 컨테이너는 이 검사에서 변경하지 않는다.
- 셸 문법, 새 Python 검사의 Ruff, `git diff --check` 통과. CI에 업데이트 검사를 추가하고 README·Pi 설치 가이드·명세의 실행 방법을 갱신했다. 앱·이미지 검증은 아래 같은 날의 결과를 따른다.

## 실행 방식과 방송 선택 정리 (2026-09-19)

- `COMMENT_SOURCE` 설정을 제거했다. 개발·운영은 실행 방식이고 실제 방송·데모는 화면에서 선택하는 데이터 모드다. 서버 시작·모니터 종료 시 실제 방송이 선택된 idle 상태이며 자동 연결하지 않는다. 기존 환경변수는 무시한다.
- 개발·설치 스크립트, CI, 환경변수 예제와 설치 문서·명세를 일치시켰다. 브라우저 테스트도 환경변수 대신 화면에서 데모를 선택한다.
- Backend pytest **42개**, mypy, Ruff 통과. 제거한 환경변수의 값 검증 1건을 없애고 기존 세션 테스트에 이전 환경변수 무시·idle 기본값·종료 후 기본값 검증을 추가했다.
- Frontend lint·format:check·check(오류·경고 0개), 단위 테스트 **44개**, build, E2E **24개** 통과. 첫 화면 캡처도 확인했다.
- x86_64 운영 컨테이너 빌드·HTTP·정적 파일·mock WebSocket 생명주기·정상 종료 및 non-root/read-only/localhost 검증 통과. 실제 Pi·TikTok LIVE는 이번 검증 범위에 포함하지 않았다.

## 프론트엔드 린트·4칸 포맷 적용 (2026-09-17)

- ESLint의 JavaScript·TypeScript·Svelte 권장 규칙과 Prettier·Svelte 포맷 플러그인을 개발 의존성으로 추가하고 `pnpm-lock.yaml`을 갱신했다. Svelte 스크립트·스타일을 포함한 소스·테스트·설정 파일을 공백 4칸으로 포맷했다. 생성물과 패키지 매니저가 관리하는 lockfile은 포맷 대상에서 제외했다.
- 린터가 지적한 배지 목록의 key 누락, 반응성 의존성 읽기의 표현 방식, 벤치마크 시작 대기의 빈 catch를 수정했다. 코드 규칙 검사와 서식 검사를 분리하고 충돌하는 서식 규칙만 Prettier에 맡겼다.
- `pnpm lint`, `lint:fix`, `format`, `format:check`를 추가했다. CI에는 lint와 format:check를 연결했다. VS Code의 기존 CSS 설정을 유지하면서 저장 시 포맷·린트 수정과 4칸 들여쓰기를 설정했다. 로컬 ESLint 확장 3.0.34 설치도 완료했다.
- 독립 검사에서 JS·TS·MJS·Svelte·rune 모듈에 의도적인 오류를 넣어 린트 검출을 확인했다. 생성물 제외와 실제 TS·Svelte의 4칸 출력도 검사했다.
- `pnpm install --frozen-lockfile`, lint·자동 수정·format:check, check 오류·경고 **0개**, `tsc --noEmit`, 단위 테스트 **44개**, 정적 build, E2E **24개** 통과. Backend pytest **43개**와 mypy도 통과했다. 기존 Vite CSS 플러그인 peer 경고와 백엔드 외부 패키지 deprecation 경고는 남아 있다.

## 프론트엔드 전수 점검 (2026-09-17)

- 페이지·레이아웃, 컴포넌트 12개, 통신·상태·검증 모듈, 테스트, 설정, 벤치마크, CSS·HTML·정적 SVG를 점검했다.
- 기존 `pnpm check`에서 빠져 있던 E2E·벤치마크·설정 파일을 SvelteKit의 생성 설정에 추가했다. 벤치마크의 타입 오류 **14개**를 수정했다. 표준 타이머와 Playwright의 객체 핸들을 사용하고, 포트·소켓 준비 상태를 검사한다. 검사 제외나 타입 오류 억제는 추가하지 않았다.
- 이벤트 enum 검증에서 배열을 문자열로 승인하거나 잘못된 객체 변환이 예외를 일으키던 문제를 수정했다. 잘못된 프레임 이후에도 정상 댓글을 받는 회귀 테스트를 추가했다.
- 문자열 제한을 백엔드와 같은 Unicode 코드포인트 기준으로 맞춰, 허용 길이의 이모지 댓글·이름·선물명이 버려지던 문제를 수정했다.
- 세션 전환 뒤 이전 툴바 오류가 남거나 늦은 응답이 계정 폼의 오류를 되살리는 문제를 수정했다. 창 크기 변경 시 새 이벤트가 없어도 최신 댓글 위치를 유지하며, 이전 댓글을 읽는 동안에는 이동시키지 않는다.
- 편집기: 설치된 Svelte 언어 서버에서 **14개 Svelte 파일**, TypeScript 서버와 Svelte 플러그인에서 **19개 TS·JS·MJS 파일**, 기본 CSS·HTML 서버에서 `app.css`와 `app.html`의 진단 **0건**을 확인했다. `.vscode/`에 빌드용 `@function` 문법만 등록했다. 잘못된 CSS 규칙과 속성값은 여전히 진단되는 것도 확인했다.
- Frontend: 확대된 check 오류·경고 **0개**, `tsc --noEmit`, 단위 테스트 **44개**, 정적 production build, 브라우저 E2E **24개** 통과.
- 벤치마크 스크립트를 실제 실행했다. 로컬 x86_64 Chromium에서 보관 수 30·1,000개 각각 3회, 회당 댓글 1,000개의 수신 순서·보관 상한을 확인했다. 기존 성능 측정 기록은 덮어쓰지 않았다.
- Backend 회귀 검사: pytest **43개**, mypy **27개 파일**, ruff 통과. 기존 외부 패키지 deprecation 경고 4개는 남아 있다. 의존성·lockfile·실행 중인 서비스는 변경하지 않았다.

## 프론트엔드 구조 리팩토링 (2026-09-17)

- `+page.svelte`를 275줄에서 90줄로 줄였다. 헤더·계정 입력·방송 정보·요청 안내를 컴포넌트로 분리하고 페이지에는 화면 조립과 포커스 전환을 남겼다.
- `lib/monitor/session.svelte.ts`는 WebSocket·목록·프레임 배치를, `commands.svelte.ts`는 HTTP 변경과 불확실한 응답의 결과 확인을 담당한다. 기존 전송·검증 함수를 재사용하며 상태는 페이지별로 생성한다.
- 영역별 CSS를 담당 컴포넌트로 옮겼다. `app.css`는 테마·리셋·reduced motion만 유지한다. 기존 기능·디자인·API 계약과 의존성·lockfile은 유지했다.
- 새 단위 테스트 4개로 인스턴스 간 상태 격리, 수신 순서·보관 상한, 세션 전환 시 예약 프레임 폐기, 불확실한 변경의 중복 차단·조회 복구, 오래된 HTTP 응답 무시, 종료 시 요청·타이머 정리를 검사했다.
- 리뷰에서 발견한 대기 화면 세션 변경 시 입력 포커스 유실을 수정했다. 계정 폼을 유지하면서 새 세션에만 입력·오류를 초기화한다. 같은 세션의 초안·오류 유지와 입력·테마 버튼의 포커스 보존을 브라우저 회귀 테스트로 검사했다.
- Frontend: check 오류·경고 **0개**, 단위 테스트 **41개**, 정적 production build, 브라우저 E2E **22개** 통과. 설정·복구·다중 화면·테마·배율·읽기 위치와 320/390/720/1080px 화면 검사를 포함한다.
- VS Code 후속 점검: 상태 모듈 임포트를 명시적인 `.svelte.js` 경로로 변경했다. 설치된 Svelte 언어 서버에서 페이지·tsconfig 진단 0개와 `status: StatusMessage` 추론을 확인했다. check·tsc·단위 테스트 41개·build·브라우저 검사 2개를 다시 통과했다. 변경 전 경로도 새 언어 서버에서는 통과하므로 기존 편집기 세션의 캐시 문제가 원인인지는 확정하지 않았다.
- Backend 회귀 검사: pytest **43개**, mypy **27개 파일**, ruff 통과. 기존 외부 패키지 deprecation 경고 4개는 남아 있다.
- README·명세서·AGENTS의 구조 설명을 갱신했다. 실제 TikTok LIVE 및 Raspberry Pi 하드웨어 검증이나 실행 중인 서비스 배포는 하지 않았다.

## 백엔드 구조 리팩토링 (2026-09-17)

- 앱 조립, API 라우터·의존성·보안·예외 처리, 요청·응답·이벤트 스키마를 분리했다. `MonitorService`는 시작·종료·재연결·설정 변경과 상태 조회를 공개 메서드로 제공한다.
- TikTok 연동은 `integrations/tiktok.py`, 데모와 이벤트 경계는 `services/`, 브라우저 송신은 `realtime/broadcaster.py`로 이동했다. 기존 모듈과 호환용 재노출 파일은 남기지 않았다.
- URL·JSON·WebSocket 계약, 단일 세션 전환, 취소 보호, 큐 상한·수신 순서, 느린 브라우저 격리와 실행 명령은 유지했다. 설정 입력 검증 실패만 422로 처리하며 내부 검증 오류는 500으로 구분한다.
- Backend: pytest **43개**, mypy **27개 파일**, ruff와 `uv lock --check` 통과. 기존 테스트를 책임별로 이동하고 HTTP/WS 공통 의존성 교체, 응답/OpenAPI 스키마, 422/500 오류 경계를 검사했다.
- Frontend: check 오류·경고 **0개**, 단위 테스트 **37개**, 정적 production build, 브라우저 E2E **21개** 통과.
- `scripts/test-container.sh`: 로컬 **x86_64** 이미지 빌드·healthy·정적 자산·mock HTTP/WS·설정·세션 충돌·종료 확인. UID 10001, read-only, localhost 포트와 활성 수신 중 SIGTERM 정상 종료를 검사했다. 테스트 컨테이너·이미지·네트워크는 정리됐다.
- README·명세서·AGENTS 지침 및 문서 링크를 갱신했다. 의존성·lockfile 변경이나 실행 중인 서비스 배포는 하지 않았다.
- 기존 외부 패키지 deprecation 경고 4개는 남아 있다. 실제 TikTok LIVE와 Raspberry Pi/ARM64 하드웨어 검증은 이번 작업에 포함하지 않았다.

## TikTokLive 이벤트 연동 재점검 (2026-09-17)

[TikTokLive 이벤트 문서](https://github.com/isaackogan/TikTokLive#events)와 GitHub의 이벤트 정의·클라이언트 파서를 설치된 TikTokLive 7.0.1 / TikTokLiveProto 0.2.2와 대조했다. 의존성은 변경하지 않았다.

- 프로젝트 범위인 댓글, 선물, 팔로우, 공유, 구독, 시청자 수, 좋아요 합계, 연결·방송 상태와 프로필·배지의 매핑을 확인했다.
- 원본 protobuf 메시지를 실제 라이브러리 파서와 등록된 리스너에 전달하는 회귀 테스트를 추가했다. 수신 순서, 연속 선물 중간 이벤트 제외·최종 수량, 통계와 상태 전환을 TikTok 연결 없이 검사한다.
- 라이브러리의 파싱 실패 로그가 원본 payload를 출력하지 않도록 `ignore_broken_payload`를 활성화하고 테스트했다.
- 브라우저 검사에서 발견한 목록 제거 후 늦은 스크롤 이벤트의 null 참조를 수정했다.
- 입장, 전용 이모트, 질문, 투표, 배틀, 메시지 삭제·고정, SuperFan 전용 이벤트 등은 현재 프로젝트 범위 밖이며 구현하지 않았다. 라이브러리 전체 이벤트를 지원한다는 의미는 아니다.
- 실제 LIVE payload나 네트워크 연결은 이번 검증에 사용하지 않았다.
- 재검증: backend pytest 41개, mypy, ruff 통과. frontend check 오류·경고 0개, 단위 테스트 37개, 정적 빌드, 브라우저 E2E 21개 통과. 외부 패키지 deprecation 경고 4개는 남아 있다.

## 백엔드 안정화 (2026-09-15)

세션 전환, 이벤트 경계, 송신, API·출처 검사를 구현했다. 현재 파일 위치는 [README의 백엔드 코드 구조](README.md#백엔드-코드-구조)를 참고한다.
프론트엔드와 Vite 프록시도 분리된 API 및 session_id 계약으로 함께 전환했다.

- Backend: pytest **35개**, mypy, ruff 통과.
- Frontend: check 오류/경고 0, 단위 테스트 **13개**, production build 통과.
- Browser: E2E **9개** 통과. 오래된 설정창의 재시작 차단 및 별도 Vite 개발 서버 경로 포함.
- 실제 Uvicorn HTTP/WebSocket에서 2개 브라우저에 500개 댓글 순서 전달,
  출처 거부, 동시 변경 200/409, 작업 정리를 검증했다.
- Docker 이미지 빌드와 별도 검증용 컨테이너의 UID 10001, 읽기 전용 파일시스템,
  localhost 포트, static UI, mock WS, 설정/재연결/충돌/종료를 확인했다.
- 실행 중인 mock 수신이 있는 상태에서 SIGTERM 종료 후
  `Application shutdown complete` 및 `Finished server process` 로그를 확인했다.
  해당 Uvicorn은 SIGTERM을 다시 전달해 종료 코드 143을 반환하며 강제 종료(137)는 아니었다.
- Compose 구성은 .env.example을 사용해 검증했다. 사용자의 .env를 생성하거나 수정하지 않았다.
- 테스트용 컨테이너·임시 Vite 서버는 종료했다. 기존 실행 서비스에 배포하지 않았다.
- 의존성 버전은 유지했다. 이미 사용하던 httpx를 직접 런타임 의존성으로 명시하고 uv.lock을 갱신했다.

## 프론트엔드 개선

- Backend: pytest 40개, mypy, ruff(app/tests).
- Frontend: strict TypeScript/Svelte check 오류·경고 0개, 단위 테스트 37개, static production build.
- Browser: E2E 21개. 선택·설정·재연결·다른 화면의 상태 변경, 응답 유실/시간 초과, 테마·배율 저장, 부가정보, 1,000건 순서·보관 상한을 검사한다.
- 읽기 모드: 보관 목록 앞부분 삭제와 글자 확대 후 기준 항목의 위치 오차 ≤1px, 기준 항목 퇴출 안내, 새 항목 수 상한, 키보드/버튼 최신 복귀, 세션 변경 시 대기 프레임 폐기를 검사한다.
- 접근성: 1080×1920, 720×1280 모니터 및 390/320px 너비, 키보드 설정창 개폐·포커스 복귀, 접힌 입력 오류 공개를 검사한다. 스크린 리더 낭독 자체는 실제 보조기기에서 별도 확인해야 한다.

## 성능 측정

실행: `cd frontend && pnpm build && pnpm benchmark ../docs/frontend-benchmark-local.json`.
Python 가상환경과 Playwright Chromium을 사용한다. 스크립트가 임시 localhost 서버를 시작·종료하며 TikTok 연결 없이 브라우저 WebSocket에 샘플을 주입한다. 각 회차의 마지막 보관 항목 ID와 순서를 검사한다. 메모리 무제한 증가 방지는 목록과 대기 배치 상한으로 보장하며, 이 짧은 측정은 장시간 힙 측정을 대신하지 않는다.

환경: Linux x64, Intel i9-14900HX, Chromium 153.0.8010.12, 1080×1920, CDP CPU 4배 지연. 보관 수별 1,000건을 목표 500건/초로 보내고 3회 측정했다. 실제 주입 간격에는 Node/CDP 처리 시간이 포함된다. 아래 값은 3회 결과의 중앙값이다.

| 보관 수 | 개선 전 프레임 간격 p95 | 개선 후 프레임 간격 p95 | 마지막 항목 표시까지 전 → 후 |
| --- | --- | --- | --- |
| 30 | 16.8ms | 16.8ms | 2.23초 → 2.26초 |
| 1,000 | 116.7ms | 33.4ms | 5.18초 → 2.30초 |

원본: [개선 전](docs/frontend-benchmark-before.json), [개선 후](docs/frontend-benchmark-after.json). 기본 보관 수의 한 회차에 64ms long task가 1회 기록되었으며 나머지 회차에는 없었다. 기본 크기는 안정적으로 유지하고, 1,000개 보관의 높은 수신량에서는 약 30fps 수준의 프레임 간격으로 개선했다. DOM 가상화나 별도 상태 라이브러리는 추가하지 않았다.

## 장비 검증의 범위

위 수치는 로컬 CPU 지연 실험이며 Raspberry Pi 성능 수치가 아니다. Pi의 Chromium은 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium pnpm benchmark ...`로 지정해 같은 시나리오를 실행할 수 있다. 실제 Pi의 장시간 메모리·온도·터치 조작, 실방송 수신은 이번 로컬 검증에 포함하지 않았다. 기능 구현과 mock 검증 완료 여부와 이 장비 검증 범위는 구분한다.

## 남은 외부 검증과 운영상 한계

- 실제 Raspberry Pi/ARM64 이미지 실행, 전원 재인가 후 Desktop·화면 회전·kiosk 자동 복구.
- 실제 TikTok LIVE 수신과 장시간 부하·네트워크 장애 실험.
- 실제 보조기기에서 스크린 리더 낭독 확인.
- Starlette/httpx 및 TikTokLive/websockets의 외부 패키지 deprecation 경고는 백엔드 안정화 검증 당시 남아 있었다.
- 외부 라이브러리가 협력적 종료를 거부하면 새 연결을 차단한다. `shutdown_timeout`은 명시적 컨테이너 재시작 대상이며 Docker는 health 503만으로 재시작하지 않는다.

현장 인수 절차는 [배포 환경 설치 가이드](docs/installation-deploy.md#5-현장-인수-확인)를 따른다.
