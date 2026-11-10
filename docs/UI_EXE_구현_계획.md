# KakaoBot 데스크톱 UI · EXE 구현 계획

## 1. 목표

PyCharm에서 `main.py`를 직접 실행하고 `config/DefaultSetting.ini`를 편집하던 흐름을 다음과 같이 바꾼다.

1. 사용자는 `KakaoBot.exe` 또는 `run_gui.bat`만 실행한다.
2. 기존 INI 설정은 모두 UI에서 조회·수정한다.
3. 봇은 UI와 분리된 워커 프로세스에서 실행한다.
4. UI에서 시작, 일시정지, 재개, 재시작, 정상 종료를 수행한다.
5. 카카오톡 자동화와 클립보드 전송은 워커의 단일 실행 흐름에서만 수행한다.
6. 설정, API 키, 로그, OAuth 토큰, Instagram 세션은 실행파일 내부에 넣지 않는다.
7. 기존 `main.py` 실행 방식도 유지한다.

## 2. 확정한 기술 선택

### 2.1 UI

- Python 기본 포함인 `tkinter`/`ttk`를 사용한다.
- 초기 배포 크기와 PyInstaller 복잡도를 최소화한다.
- UI 메인 스레드는 화면 갱신만 담당한다.
- 봇의 카카오톡 자동화는 별도 워커 프로세스에서 수행한다.

### 2.2 프로세스 구조

```text
KakaoBot UI 프로세스
├─ 대시보드 / 전체 설정 / 실시간 로그
├─ 워커 시작·정지·재시작 관리
└─ 표준입출력 기반 제어·상태 채널
    └─ KakaoBot 워커 프로세스
       ├─ 채팅방 순회 및 카카오톡 자동화
       ├─ Feather 로그 모니터 스레드
       └─ 기존 명령 처리 및 전송 큐
```

- 워커가 오류로 종료되어도 UI는 유지한다.
- 설정 적용은 파일 저장 후 워커를 재시작하는 방식으로 일관되게 처리한다.
- 워커만 카카오톡 포커스, 키보드 이벤트, 클립보드를 사용한다.
- 종료 요청은 먼저 정상 종료를 시도하고, 제한 시간 초과 시 프로세스 종료를 사용한다.

### 2.3 배포

- 1차 배포 형식은 PyInstaller `onedir + windowed`로 한다.
- 디버깅을 위한 콘솔 빌드 방법도 문서화한다.
- `onefile`은 외부 데이터 경로가 안정화된 뒤 선택 사항으로 남긴다.
- Python 3.11 x64를 기준 빌드 환경으로 고정한다.

## 3. UI 범위

### 3.1 대시보드

- 전체 상태: 정지 / 시작 중 / 실행 중 / 일시정지 / 종료 중 / 오류
- 카카오톡 프로세스 상태
- 시작, 일시정지, 재개, 재시작, 종료 버튼
- 설정 폴더, 로그 폴더 열기
- 가동 시간과 워커 PID
- 채팅방별 초기화 상태와 최근 오류
- 새 로그만 이어 붙이는 실시간 로그 창
- 로그 자동 스크롤, 화면 지우기, 오류만 보기

### 3.2 기본 설정

| UI 필드 | INI 위치 |
|---|---|
| 봇 이름 | `[BotName] name` |
| 전체 멘션 기본 지연 | `[EveryMentionDefaultDelayTime] value` |
| API 키 파일 | `[APIKey] path` |
| 채팅방 데이터 파일 | `[ChattingRoomSetting] path` |

### 3.3 채팅방 관리

- `[RoomList]`의 방을 표 형태로 표시한다.
- 방 추가, 수정, 삭제, 위/아래 순서 변경을 지원한다.
- 빈 이름과 중복 이름은 저장하지 않는다.
- 저장 후 워커 재시작 시 새 목록을 적용한다.

### 3.4 GPT 설정

| UI 필드 | INI 위치 |
|---|---|
| 최대 토큰 | `[GPT] maxToken` |
| 기본 모델 | `[GPT] defaultModel` |
| 답변 길이 지시문 | `[GPT] answerLengthLimit` |
| 모델명·비용 비율 표 | `[GPT_MODEL]` |

- 기본 모델은 모델 표에 존재해야 한다.
- 모델명은 중복될 수 없다.
- 최대 토큰과 비용 비율은 숫자로 검증한다.

### 3.5 Radar 설정

| UI 필드 | INI 위치 |
|---|---|
| Base URL | `[RADAR] baseUrl` |
| API 키 환경변수 이름 | `[RADAR] apiKeyEnv` |

### 3.6 Feather 모니터 설정

| UI 필드 | INI 위치 |
|---|---|
| 사용 여부 | `[FeatherMonitor] enabled` |
| 알림 채팅방 | `[FeatherMonitor] notification_room` |
| 로그 파일명 | `[FeatherMonitor] log_filename` |
| 서버 이름·경로 표 | `server_names`, `server_paths` |

- 서버 이름과 경로를 한 행으로 묶어 관리한다.
- 쉼표 문자열의 개수 불일치가 생기지 않도록 UI가 직렬화한다.
- 알림 채팅방은 등록된 채팅방 목록에서 선택할 수 있게 한다.

### 3.7 고급 설정

| UI 필드 | INI 위치 |
|---|---|
| Git 자동 업데이트 | `[GitHub] autoUpdate` |
| Git 브랜치 | `[GitHub] branch` |

- 소스 실행에서는 기존 Git 업데이트 설정을 유지한다.
- 패키징된 실행파일에서는 Git 업데이트를 실행하지 않고 UI에 비활성 상태를 표시한다.

### 3.8 API 키 관리

- `config/api_key.json`의 키를 이름/설정 여부 표로 표시한다.
- 값은 기본적으로 마스킹한다.
- 키 추가, 수정, 삭제와 표시/숨김을 지원한다.
- 실제 키 값은 로그에 기록하지 않는다.
- 배포 산출물에는 `api_key.json`을 포함하지 않고 빈 예제만 포함한다.

### 3.9 인증·운영 파일

- YouTube 토큰과 Instagram 세션 존재 여부를 진단한다.
- 인증 파일이 있는 데이터 폴더를 여는 기능을 제공한다.
- 브라우저 로그인이나 쿠키 입력 자동화는 이번 범위에서 제외하고 기존 도구를 유지한다.

## 4. 설정 저장 정책

1. UI는 설정을 타입이 있는 데이터 객체로 읽는다.
2. 저장 전에 모든 필드를 검증한다.
3. 기존 INI를 백업한다.
4. 임시 파일에 UTF-8로 기록한 뒤 원자적으로 교체한다.
5. API 키 JSON도 동일한 방식으로 저장한다.
6. 실행 중 저장하면 워커를 정상 종료한 뒤 새 설정으로 다시 시작한다.
7. UI가 작성하더라도 기존 `main.py`와 `configparser`가 읽을 수 있는 INI 형식을 유지한다.

## 5. 런타임 경로 정책

- 소스 실행: 저장소 루트를 애플리케이션 데이터 루트로 사용한다.
- EXE 실행: 실행파일이 있는 배포 폴더를 데이터 루트로 사용한다.
- 환경변수 `KAKAOBOT_DATA_DIR`이 있으면 그 경로를 우선한다.
- 다음 경로는 한 모듈에서 일관되게 계산한다.

```text
config/DefaultSetting.ini
config/api_key.json
config/chatrooms.json
config/api_usage.json
config/youtube_client_secrets.json
saved/log.log
saved/instagram/
token.pickle
```

- 배포 폴더는 사용자가 쓰기 가능한 위치에 둔다.
- 실행 위치(CWD)에 따라 파일을 잃어버리지 않도록 모든 경로를 절대 경로로 변환한다.

## 6. 로그 정책

- `log.log`와 회전 대상 이름 불일치를 수정한다.
- 시작 시 크기 기반 회전을 수행한다.
- 백업 개수를 제한한다.
- UI는 기존 대형 로그 전체를 읽지 않고 실행 중 발생한 로그 이벤트만 받는다.
- `Helper.CustomPrint`에 로그 구독자를 추가하되 기존 콘솔·파일 로그는 유지한다.

## 7. 안전성 정책

- API 키, 토큰, 세션 파일은 PyInstaller 데이터로 포함하지 않는다.
- 실제 키 값과 전체 설정 내용을 로그에 출력하지 않는다.
- 카카오톡 포커스·클립보드·키 입력은 동시에 둘 이상 실행하지 않는다.
- 일시정지는 다음 채팅방 순회 지점에서 적용한다.
- 종료 시 Feather 모니터, 명령 워커, 로그 파일을 정리한다.
- UI 종료 시 실행 중인 봇을 남기지 않는다.

## 8. 변경 대상

### 신규 파일

- `app.py`: UI/워커 공용 진입점
- `Lib/runtime_paths.py`: 실행·데이터 경로 통합
- `Lib/settings_manager.py`: INI/API 키 로드·검증·저장
- `Lib/bot_engine.py`: 시작·일시정지·종료 가능한 실행 엔진
- `Lib/desktop_ui.py`: Tkinter UI
- `KakaoBot.spec`: PyInstaller onedir 빌드
- `run_gui.bat`: 소스 UI 실행
- `build_exe.bat`: 재현 가능한 EXE 빌드
- `requirements-build.txt`: 빌드 도구 버전
- 설정/엔진/UI 단위 테스트

### 수정 파일

- `main.py`: `BotEngine` 기반 기존 콘솔 진입 유지
- `Lib/dataManager.py`: 통합 설정 경로 사용
- `Lib/json_data_manager.py`: 절대 경로와 안전 저장 사용
- `Lib/Helper.py`: 통합 로그 경로, 회전, 로그 구독
- `Lib/gpt_api.py`: API 키 로드 순서와 사용량 파일 경로 수정
- `Lib/insta.py`: 통합 세션·로그 경로 사용
- `Lib/youtube.py`: 통합 OAuth 파일 경로 사용
- `Lib/log_monitor.py`: 종료 시 정리 확인
- `.gitignore`: 빌드·개인 데이터 제외 확인
- `README.md`: UI 실행 및 배포 사용법 추가

## 9. 검증 계획

### 자동 검증

- 기존 테스트 전체 통과
- 모든 INI 섹션 왕복 저장 테스트
- 잘못된 숫자, 중복 방, 잘못된 기본 모델 검증 테스트
- API 키가 마스킹되고 원자적으로 저장되는지 테스트
- BotEngine 시작·일시정지·재개·종료 테스트(가짜 ChatProcess 사용)
- UI 모듈 import 및 주요 위젯 생성 스모크 테스트
- 패키징 분석 시 누락 import 확인

### 수동 검증

- 소스 UI 실행
- 설정 조회·수정·저장·재로드
- 워커 시작·일시정지·재개·종료
- 카카오톡 미실행 상태에서 자동 실행
- 다중 채팅방 초기화
- 텍스트/이미지 전송
- Feather 모니터 시작·종료
- Python/PyCharm/Git이 없는 환경에서 EXE 실행

## 10. 완료 조건

- [ ] 사용자가 INI를 직접 편집하지 않고 모든 기존 설정을 변경할 수 있다.
- [ ] UI가 멈추지 않은 채 봇을 시작·일시정지·재개·종료할 수 있다.
- [ ] 설정 저장 후 워커 재시작으로 변경사항이 반영된다.
- [ ] 기존 `python main.py` 실행이 유지된다.
- [ ] API 키·세션·대형 로그가 EXE에 포함되지 않는다.
- [ ] `run_gui.bat`로 소스 UI를 실행할 수 있다.
- [ ] `build_exe.bat`로 `dist/KakaoBot/KakaoBot.exe`를 만들 수 있다.
- [ ] 자동 테스트와 EXE 스모크 테스트가 통과한다.

## 11. 구현 체크리스트

- [ ] 런타임 경로 통합
- [ ] INI/API 키 설정 관리자
- [ ] 안전한 로그 회전·구독
- [ ] BotEngine 및 워커 제어 채널
- [ ] 대시보드
- [ ] 전체 INI 설정 UI
- [ ] API 키 UI
- [ ] 저장·검증·백업·재시작
- [ ] PyInstaller spec
- [ ] 실행/빌드 BAT
- [ ] 테스트와 문서 갱신
