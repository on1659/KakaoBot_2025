해당 Readme.md는 GPT로 작성되었습니다.

# KakaoBot_2025

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
pyautogui를 사용하여 메시지를 붙여넣고(Clipboard+Ctrl+V), Enter 키로 전송

win32gui.SetForegroundWindow로 카카오톡 창 포커스 제어

채팅 메시지 수신 (receive.py)
채팅창에서 Ctrl+A, Ctrl+C로 전체 메시지를 복사

pandas와 정규 표현식을 사용해 사용자명, 메시지 등 파싱

명령어 체크 (check.py)
#all, [카카오맵], #유툽 등 특정 키워드를 감지해 대응

필요한 경우 각 모듈(every_mention.py, youtube.py 등) 호출

YouTube & 네이버 지도 (youtube.py, convert_naver_map.py)
requests 라이브러리로 YouTube Data API, 네이버 지도 API 호출

받은 결과(제목, 주소 등)를 문자열로 만들어 카카오톡에 전송

모든 참여자 멘션 (every_mention.py)
인원 수만큼 @이름 태그를 자동 입력

pyautogui로 @ + 방향키 + Enter 시퀀스를 반복 수행

## 주의사항 & 마무리
카카오톡 업데이트 주의

PC 카카오톡 UI나 동작이 바뀌면 자동화 로직 일부 수정이 필요할 수 있음.

API 키 관리

YouTube/네이버 API 키 등은 .gitignore 처리가 권장됨.

Windows 전용

pywin32가 Windows용 라이브러리여서 macOS/Linux에서 호환되지 않을 수 있음.

기여 / 문의
버그나 개선 아이디어는 Issues에 남겨 주세요.

PR(Pull Request)도 언제든 환영합니다!

