해당 Readme.md는 GPT로 작성되었습니다.

# KakaoBot_2025

## 데스크톱 UI 실행

이 프로젝트는 `DefaultSetting.ini`를 직접 편집하지 않고도 모든 설정을 관리할 수 있는
Windows 데스크톱 UI를 제공합니다.

### 소스에서 실행

```bat
run_gui.bat
```

또는 Python 3.11 환경에서 다음과 같이 실행합니다.

```powershell
python app.py
```

UI에서 채팅방, GPT 모델, Radar, Feather 모니터, Git 설정과 API 키를 관리할 수 있습니다.
설정을 저장하면 실행 중인 봇 워커를 정상 종료한 뒤 새 설정으로 재시작합니다. 기존
콘솔 방식은 계속 `python main.py`로 사용할 수 있습니다.

### Windows 실행파일 빌드

```bat
build_exe.bat
```

최초 빌드는 `.venv-build`에 Python 3.11 전용 빌드 환경을 만들기 때문에 시간이 걸릴 수
있습니다. 결과는 `dist\KakaoBot\KakaoBot.exe`에 생성됩니다. 콘솔 로그가 보이는 진단용
빌드는 `build_exe.bat --console`로 만들 수 있습니다.

배포 형식은 설정·로그·인증 파일을 안전하게 외부에 유지하기 위해 `onedir`를 사용합니다.
`config/api_key.json`, `token.pickle`, `config/youtube_client_secrets.json`, `saved/`는 실행파일에
포함되지 않습니다. EXE 최초 실행 시 안전한 기본 설정을 만들고, 실제 값은 UI에서
입력합니다. 배포 폴더는 바탕화면처럼 쓰기 가능한 위치에 두세요.

상세 설계와 검증 기준은 [UI_EXE_구현_계획.md](docs/UI_EXE_구현_계획.md)를 참고하세요.

## 웹 관리 화면

브라우저에서 봇을 켜고 끄고, 사용자와 기능별 권한을 관리할 수 있습니다.

```bat
run_web.bat
```

`python app.py --web`과 같으며, 브라우저가 `http://127.0.0.1:8765/`로 자동으로 열립니다.
EXE에서는 `KakaoBot.exe --web`으로 실행합니다.

| 탭 | 기능 |
|---|---|
| 대시보드 | 시작·일시정지·재시작·정지, 채팅방 상태, 실시간 로그 |
| 사용자 | 닉네임별 역할(관리자/사용자/차단), 미등록 사용자 정책, 최근 대화한 사람 목록에서 바로 등록 |
| 기능 권한 | 기능별 켜기/끄기, 사용 가능 대상(모든 사용자/등록 사용자/관리자), 허용 채팅방 |
| 봇 설정 | `DefaultSetting.ini`의 모든 항목 (저장 후 봇 재시작) |
| API 키 | 키 등록·교체·삭제 (저장된 값은 화면에 다시 표시되지 않음) |

- 권한은 `config/permissions.json`에 저장되며 봇을 재시작하지 않아도 바로 적용됩니다.
  파일이 없으면 모든 기능이 모두에게 허용됩니다.
- 사용자는 카카오톡 대화 닉네임으로 구분합니다. 오픈채팅에서는 누구나 닉네임을 바꿀 수 있어
  완벽한 보안 수단은 아닙니다.
- 기본적으로 이 PC에서만 접속할 수 있습니다. 같은 네트워크의 휴대폰 등에서 접속하려면
  `run_web.bat --host 0.0.0.0 --password 비밀번호`로 실행하세요 (HTTP 평문이므로 신뢰할 수 있는
  네트워크에서만 사용).
- 기타 옵션: `--port 9000`, `--no-browser`, `--autostart`(웹 서버와 함께 봇 바로 시작).

**KakaoBot_2025**는 카카오톡 PC 버전을 활용하여 자동으로 메시지를 전송하고, 채팅 내용을 분석하며, 특정 명령어를 처리할 수 있는 파이썬 프로젝트입니다. 이 레포지토리에는 여러 `.py` 파일이 포함되어 있으며, 각각 특정 기능을 담당합니다.

---

## 📚 목차
1. [프로젝트 개요](#프로젝트-개요)  
2. [프로젝트 구조](#프로젝트-구조)  
3. [주요 라이브러리](#주요-라이브러리)  
4. [핵심 기능 소개](#핵심-기능-소개) 
   - [채팅 메시지 전송 (`send.py`)](#채팅-메시지-전송-sendpy)  
   - [채팅 메시지 수신 (`receive.py`)](#채팅-메시지-수신-receivepy)  
   - [명령어 체크 (`check.py`)](#명령어-체크-checkpy)  
   - [YouTube & 네이버 지도 (`youtube.py`, `convert_naver_map.py`)](#youtube--네이버-지도-youtubepy-convert_naver_mappy)  
   - [모든 참여자 멘션 (`every_mention.py`)](#모든-참여자-멘션-every_mentionpy)  
5. [주의사항 & 마무리](#주의사항--마무리)

---

## 프로젝트 개요
**KakaoBot_2025**는 파이썬으로 작성된 프로젝트로, 카카오톡 PC 창을 자동 제어하여 다음과 같은 작업을 수행합니다:

- 채팅 메시지를 자동으로 전송  
- 채팅방에서 특정 명령어(`"#all"`, `"#유툽"` 등) 감지 후 대응  
- 네이버 지도 / 유튜브 API를 통해 검색 결과 전송  
- 카카오톡 창 포커스, 키보드/마우스 이벤트 제어 (Windows 환경)

필요에 따라 **확장**할 수 있으며, **Windows**에서의 동작을 가정합니다.

---

## 프로젝트 구조
```plaintext
KakaoBot_2025/
├── main.py                # 메인 실행 파일 (스케줄러, 초기 설정 등)
├── send.py                # 채팅 메시지 전송 로직
├── receive.py             # 채팅 메시지 수신/복사 로직
├── check.py               # 특정 명령어(#all, #유툽, #카카오맵 등) 감지
├── youtube.py             # 유튜브 관련 API/검색 기능
├── convert_naver_map.py   # 네이버 지도 관련 링크 처리
├── every_mention.py       # 카카오톡 모든 참여자 멘션 기능 (#all)
├── kakao_openroom.py      # 채팅방 열기, 포커스 제어
├── kakao_coppaste.py      # 채팅창 텍스트 복사/붙여넣기
├── kakak_send.py          # 메시지 전송 (pyautogui, clipboard 활용)
└── ... (기타 파일)
```

![화면 캡처 2025-04-21 003409](https://github.com/user-attachments/assets/d82365dc-d307-42b5-ab82-30c4a84cde5c)


## 주요 라이브러리
- **pyautogui**  
  키보드·마우스 이벤트 자동화 (Ctrl+V, Enter 등)

- **win32api, win32gui**  
  Windows API 직접 호출 (창 포커스, 메시지 전송 등)

- **re (정규 표현식)**  
  채팅 메시지 파싱

- **pandas**  
  복사된 텍스트를 표 형식으로 변환/분석

- **requests**  
  (유튜브, 네이버 지도 등) 외부 API 요청

---

## 핵심 기능 소개

채팅 메시지 전송 (send.py)
 - pyautogui를 사용하여 메시지를 붙여넣고(Clipboard+Ctrl+V), Enter 키로 전송
 - win32gui.SetForegroundWindow로 카카오톡 창 포커스 제어

채팅 메시지 수신 (receive.py)
  - 채팅창에서 Ctrl+A, Ctrl+C로 전체 메시지를 복사
  - pandas와 정규 표현식을 사용해 사용자명, 메시지 등 파싱

명령어 체크 (check.py)
- #all, [카카오맵], #유툽 등 특정 키워드를 감지해 대응
- 필요한 경우 각 모듈(every_mention.py, youtube.py 등) 호출

YouTube & 네이버 지도 (youtube.py, convert_naver_map.py)
- requests 라이브러리로 YouTube Data API, 네이버 지도 API 호출
- 받은 결과(제목, 주소 등)를 문자열로 만들어 카카오톡에 전송

모든 참여자 멘션 (every_mention.py)
- 인원 수만큼 @이름 태그를 자동 입력
- pyautogui로 @ + 방향키 + Enter 시퀀스를 반복 수행

음성·배경음악 (elevenlabs_api.py, audio_video.py)
- `#tts (내용)`: ElevenLabs로 내용을 읽어 전송
- `#bgm (설명)`: 설명에 맞는 배경음악(가사 없는 연주곡)을 ElevenLabs Music API로 만들어 전송.
  `#bgm 15초 잔잔한 피아노`처럼 맨 앞에 길이(10~20초, 기본 20초) 지정 가능
- 채팅에서 바로 재생되도록 mp3에 커버 이미지를 붙인 동영상(mp4)으로 보냄 (Windows 내장 기능으로 변환, 추가 설치 없음).
  변환에 실패하면 mp3 파일로 전송
- 파일 전송은 카카오톡의 파일 전송 단축키(Ctrl+T) → 열기 창 → 전송 확인 순서로 자동 조작
- API 키: `ELEVENLABS_API_KEY`. 선택 항목 `ELEVENLABS_VOICE_ID`, `ELEVENLABS_TTS_MODEL`, `ELEVENLABS_BGM_SECONDS`, `ELEVENLABS_MUSIC_MODEL`,
  `ELEVENLABS_SEND_AS`(`video` 기본 / `file`은 mp3 첨부)

그림 생성 (image_gen.py, aside_agent.py)
- `#지피티이미지 (설명)` (`#이미지피티`, `#imagegen`도 동일): AI 그림. `#픽셀 (설명)` (`#pxicel`, `#pixel`도 동일): PixelLab 픽셀아트
- 기본 경로는 Aside(AI 브라우저) 채팅: 봇이 Aside CLI(`aside exec --json`)로 Aside 에이전트에게 요청하고,
  만들어진 이미지 파일을 받아 카카오톡으로 전달. API 키가 필요 없고 Aside에 로그인된 계정을 사용
  - 필요한 것: Aside 앱 실행·로그인, Aside CLI 설치(설정 > Developers), `#pxicel`은 Aside 브라우저에서 PixelLab 로그인
  - 걸리는 시간: `#imagegen` 30초~2분, `#pxicel` 3~7분 (Aside가 브라우저로 PixelLab 사이트를 조작)
  - CLI 위치를 못 찾으면 API 키 설정에 `ASIDE_CLI_PATH` 항목으로 지정
- `#pxicel`은 `PIXELLAB_API_KEY`가 있으면 Aside 대신 PixelLab API를 직접 호출 (1분 이내, 선택 `PIXELLAB_IMAGE_SIZE`).
  PixelLab은 영어 묘사만 알아들으므로 요청을 `GEMINI_API_KEY`로 '그림 묘사'로 다시 써서 보냄
  (예: "만렙토끼그려봐" → "A legendary rabbit, glowing with an aura, ..."). 다시 쓰기에 실패하면 생성하지 않고 안내
- `#imagegen`은 Aside CLI가 없는 PC에서만 `OPENAI_API_KEY`로 직접 호출
  (선택 `OPENAI_IMAGE_MODEL`, `OPENAI_IMAGE_QUALITY`, `OPENAI_IMAGE_SIZE`)
- 생성이 오래 걸려 "그리는 중" 안내를 먼저 보내고, 완성되면 이미지를 전송. Aside 작업은 한 번에 하나만 처리
- **주의**: 채팅방 사람이 쓴 글이 내 계정으로 로그인된 브라우저 에이전트에게 전달됩니다. 요청문에서 그림 묘사로만
  다루도록 막고 글 답변은 방에 전달하지 않지만 완전한 차단은 아니므로, "기능 권한"에서 믿을 수 있는 방으로 제한하세요

마인크래프트 접속자 (minecraft_status.py)
- `#마크`: 서버에 지금 접속 중인 사람 목록
- 기본은 `[FeatherMonitor] server_paths`의 서버를 이 PC에서 조회. 서버가 다른 PC에 있으면
  API 키 설정에 `MINECRAFT_SERVER` 항목(값: `주소:포트`)을 추가

위 선택 항목들은 모두 `config/api_key.json`(UI의 API 키 화면)에 같은 이름으로 추가하면 적용됩니다.
새 기능은 기본적으로 모든 방에서 켜져 있으니, 웹 관리 화면의 "기능 권한"에서 방·사용자를 제한하세요.

## 주의사항 & 마무리
- 카카오톡 업데이트 주의
- PC 카카오톡 UI나 동작이 바뀌면 자동화 로직 일부 수정이 필요할 수 있음.
- API 키 관리 (YouTube/네이버 API 키 등은 .gitignore 처리가 권장됨)
- Windows 전용
- pywin32가 Windows용 라이브러리여서 macOS/Linux에서 호환되지 않을 수 있음.

기여 / 문의
버그나 개선 아이디어는 Issues에 남겨 주세요.
