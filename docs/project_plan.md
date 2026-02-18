# 프로젝트 계획

## 제거 예정: NEW_LLM (뉴커맨드)

- **제거 대상**: 이전에 추가된 “새 API 참조”용 뉴커맨드 전부.
- **제거 내용**:
  - `config/DefaultSetting.ini` [NEW_LLM] 섹션 삭제.
  - `Lib/dataManager.py`: NEW_LLM 설정 로드, `if NEW_LLM_ENABLED` 분기, `new_llm_api` import 및 해당 명령 등록 제거.
  - `Lib/new_llm_api.py` 파일 삭제.
- **대체**: #radar(게임위키 API) 명령으로 대체.

---

## 예정: #radar 게임위키 API 연동

- **목표**: `docs/API_GUIDE.md` 기준 게임위키 AI API를 `#radar` 명령으로 호출. API 키는 다른 API와 동일하게 `config/api_key.json`에 등록.
- **구현**:
  - `Lib/radar_api.py` 신규: `getData(opentalk_name, chat_command, message)` → 게임위키 `POST /api/chat` 호출 후 `(응답문자열, "text")` 반환. 메시지 앞단어가 minecraft/palworld/overwatch면 game으로, 나머지는 message로 파싱.
  - `config/DefaultSetting.ini`: [RADAR] 섹션 추가 (baseUrl, apiKeyEnv=GAME_WIKI_API_KEY).
  - `Lib/dataManager.py`: [RADAR] 설정 로드, `#radar` 명령 및 `radar_api` import 추가.
- **API 키**: `api_key.json`에 `{"name": "GAME_WIKI_API_KEY", "key": "사용자입력키"}` 추가. `load_api_keys()`로 로드되므로 별도 코드 없이 사용.
