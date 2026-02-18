# #radar 기능 구현 가이드

이 문서만 보고 **#radar(게임위키 AI API)** 기능만 구현할 수 있도록 단계를 정리한 문서입니다.

- **참조 API**: `docs/API_GUIDE.md` (게임위키 AI — 마인크래프트/팰월드/오버워치 RAG)
- **API 키**: 다른 API와 동일하게 `config/api_key.json`에 `name`/`key`로 등록

---

## 1. 제거할 것 (NEW_LLM 뉴커맨드)

이 기능을 넣기 전에, 기존에 추가된 “뉴커맨드(NEW_LLM)”는 제거합니다.

### 1.1 config/DefaultSetting.ini

- **[NEW_LLM] 섹션 전체 삭제**  
  (`[NEW_LLM]` 부터 그 다음 섹션 `[GitHub]` 직전까지)

### 1.2 Lib/dataManager.py

- **NEW_LLM 관련 설정 로드 블록 삭제**  
  `# ─── [NEW_LLM] ...` 부터 `# ─── [NEW_LLM] ───────────────────────` 까지 전부 삭제.
- **NEW_LLM 사용 분기 삭제**  
  `if NEW_LLM_ENABLED:` 와 그 안의 `from Lib import new_llm_api` 삭제.
- **chat_command_Map에 NEW_LLM으로 추가된 항목 삭제**  
  `if NEW_LLM_ENABLED:` 와 그 안의 `chat_command_Map.append([...])` 블록 전부 삭제.  
  (즉, `#radar` 또는 `#새api`가 NEW_LLM으로 등록된 부분 제거)

### 1.3 Lib/new_llm_api.py

- **파일 삭제**  
  `Lib/new_llm_api.py` 파일 전체 삭제.

---

## 2. 추가할 것

### 2.1 config/DefaultSetting.ini

**[RADAR] 섹션 추가** (예: `[GPT_MODEL]` 다음, `[GitHub]` 앞에):

```ini
[RADAR]
baseUrl = https://awhirl-preimpressive-carina.ngrok-free.dev
apiKeyEnv = GAME_WIKI_API_KEY
```

- `baseUrl`: 게임위키 API Base URL (API_GUIDE.md와 동일).
- `apiKeyEnv`: `api_key.json`에 넣을 키 이름. 이 이름으로 환경변수에서 읽음.

### 2.2 Lib/dataManager.py — RADAR 설정 로드

**[GPT_MODEL] 블록 바로 다음**에 아래 추가:

```python
# ─── [RADAR] 게임위키 API (#radar) ───────────────────────
RADAR_BASE_URL = "https://awhirl-preimpressive-carina.ngrok-free.dev"
RADAR_API_KEY_ENV = "GAME_WIKI_API_KEY"
if 'RADAR' in DefaultSettingConfig:
    _radar = DefaultSettingConfig['RADAR']
    RADAR_BASE_URL = _radar.get('baseUrl', RADAR_BASE_URL).strip().rstrip('/')
    RADAR_API_KEY_ENV = _radar.get('apiKeyEnv', RADAR_API_KEY_ENV).strip()
# ─── [RADAR] ───────────────────────
```

### 2.3 Lib/dataManager.py — import 및 명령 등록

- **import 추가** (다른 Lib import 있는 곳에):  
  `from Lib import radar_api`
- **chat_command_Map에 한 줄 추가** (다른 `#...` 명령과 같은 리스트 안에):  
  `['#radar', "#radar (게임) (질문) 또는 (질문)\n 게임위키 AI (마인크래프트/팰월드/오버워치) 질의", radar_api.getData],`

### 2.4 Lib/radar_api.py 신규 생성

아래 내용으로 `Lib/radar_api.py` 파일을 만듭니다.

**역할**

- 채팅에서 `#radar (내용)` 입력 시, 내용을 게임위키 API로 보내고 응답을 반환.
- **query 구성**: 맨 앞 단어가 `minecraft` / `palworld` / `overwatch`(대소문자 무시)이면 한글 게임명(마인크래프트/팰월드/오버워치) + 나머지를 붙여 `query`로 전송. 아니면 사용자 입력 전체를 `query`로 전송. (가이드: `game` 파라미터 제거, 질문에 게임명 명시)
- API 키는 `os.environ[dataManager.RADAR_API_KEY_ENV]`에서 읽음. 없으면 안내 메시지 반환.
- 요청: `POST {baseUrl}/api/chat`, Body `{"query": "마인크래프트 다이아몬드 어디서 구해?", "session_id": "채팅방명 또는 default"}`, Header `X-API-Key`(키가 있을 때만), `Content-Type: application/json`.
- 타임아웃 15초 권장 (API_GUIDE 기준).

**필수 구현 요구사항**

- 함수 시그니처:  
  `def getData(opentalk_name: str, chat_command: str, message: str) -> tuple[str, str]:`  
  반환: `(응답문자열, "text")`.
- `dataManager`에서 `RADAR_BASE_URL`, `RADAR_API_KEY_ENV` 읽어서 사용.
- `requests.post` 사용 시 `timeout=15` 설정.
- 예외/에러 시 사용자에게 보여줄 안내 문자열을 반환 (반환 형식은 동일하게 `(문자열, "text")`).

**요청/응답 (API_GUIDE.md 기준, 2026-02-18 변경)**

- Request: `{"query": "질문 (게임명 포함 권장)", "session_id": "string"}`. (`message`/`game` 제거)
- Response: `{"answer": "답변 내용", "sources": [...], "session_id": "..."}` → `answer` 값을 채팅 응답으로 사용.

---

## 3. API 키 등록 (다른 API와 동일)

사용자가 직접 `config/api_key.json`에 다음 형태로 추가합니다.

```json
{
  "name": "GAME_WIKI_API_KEY",
  "key": "사용자가_입력한_키"
}
```

- `main.py`에서 이미 `json_data_manager.load_api_keys()`를 호출하므로, 이 JSON에 넣으면 환경변수로 로드됨.
- `radar_api`에서는 `os.environ.get(RADAR_API_KEY_ENV)`로만 읽으면 됨.  
  (ini에서 `apiKeyEnv = GAME_WIKI_API_KEY`로 두었으면 위 `name`과 동일하게 맞추면 됨.)

---

## 4. 사용 방법 (구현 후)

- `#radar 다이아몬드 어디서 구해` → query="다이아몬드 어디서 구해" (게임명 없음, 서버 자동 감지 시도).
- `#radar 마인크래프트 다이아몬드 어디서 구해` → query="마인크래프트 다이아몬드 어디서 구해".
- `#radar palworld 팰 번식 어떻게 해` → query="팰월드 팰 번식 어떻게 해".
- `#radar overwatch 겐지 콤보` → query="오버워치 겐지 콤보".

---

## 5. 체크리스트

- [ ] DefaultSetting.ini에서 [NEW_LLM] 삭제, [RADAR] 추가
- [ ] dataManager.py에서 NEW_LLM 로드/사용 분기/append 제거
- [ ] dataManager.py에 RADAR 설정 로드, `radar_api` import, `#radar` 명령 한 줄 추가
- [ ] Lib/new_llm_api.py 삭제
- [ ] Lib/radar_api.py 생성 후 getData 구현 및 (응답, "text") 반환
- [ ] api_key.json에 GAME_WIKI_API_KEY(name/key) 추가

이 순서대로 하면 이 기능만 따로 구현할 수 있습니다.
