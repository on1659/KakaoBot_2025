"""
#radar: 게임위키 AI API 연동.
docs/API_GUIDE.md 기준 POST /api/chat 호출.
- 요청: query, session_id (game 파라미터 제거, 질문에 게임명 명시)
- 응답: answer
API 키는 config/api_key.json에 GAME_WIKI_API_KEY 로 등록.
"""
import os
import requests
from . import dataManager
from . import Helper

RADAR_BASE_URL = dataManager.RADAR_BASE_URL
RADAR_API_KEY_ENV = dataManager.RADAR_API_KEY_ENV

# 앞 단어가 영문이면 한글 게임명으로 변환해 query에 붙임
GAME_TO_QUERY_PREFIX = {
    "minecraft": "마인크래프트",
    "palworld": "팰월드",
    "overwatch": "오버워치",
}
GAMES = tuple(GAME_TO_QUERY_PREFIX.keys())


def _build_query(message: str) -> str:
    """
    사용자 입력을 API 규격 query로 변환.
    앞 단어가 minecraft/palworld/overwatch면 한글 게임명 + 나머지, 아니면 전체를 query로.
    """
    msg = (message or "").strip()
    if not msg:
        return ""
    parts = msg.split(maxsplit=1)
    first = parts[0].lower()
    rest = (parts[1].strip() if len(parts) > 1 else "").strip()
    if first in GAMES:
        prefix = GAME_TO_QUERY_PREFIX[first]
        return f"{prefix} {rest}" if rest else prefix
    return msg


def getData(opentalk_name: str, chat_command: str, message: str) -> tuple[str, str]:
    """
    #radar (내용) → 게임위키 API 질의 후 (응답문자열, "text") 반환.
    가이드: query, session_id 사용 / 응답 answer 사용.
    """
    api_key = os.environ.get(RADAR_API_KEY_ENV)
    if not api_key or not api_key.strip():
        Helper.CustomPrint(
            f"게임위키 API를 사용하려면 config/api_key.json에 '{RADAR_API_KEY_ENV}'를 등록해주세요."
        )
        return "지금은 사용하실 수 없습니다.", "text"

    query = _build_query(message)
    if not query:
        return "질문을 입력해주세요. 예: #radar 마인크래프트 다이아몬드 어디서 구해", "text"

    url = f"{RADAR_BASE_URL}/api/chat"
    headers = {"Content-Type": "application/json", "X-API-Key": api_key}
    payload = {"query": query, "session_id": opentalk_name or "default"}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # 가이드: 응답 필드 answer (구 response 대체)
        answer = (
            data.get("answer")
            or data.get("response")
            or data.get("content")
            or data.get("text")
            or data.get("result")
            or data.get("message")
            or ""
        )
        if isinstance(answer, dict):
            answer = answer.get("text") or answer.get("content") or str(answer)
        if isinstance(answer, list):
            answer = "".join(str(x) for x in answer)
        answer = (answer or "").strip()
        if not answer:
            Helper.CustomPrint(f"[radar] 응답이 비어 있음. 수신 JSON 키: {list(data.keys())}")
            return "응답 내용이 비어 있습니다.", "text"
        return answer, "text"
    except requests.exceptions.Timeout:
        return "게임위키 API 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.", "text"
    except requests.exceptions.RequestException as e:
        return f"게임위키 API 오류: {str(e)}", "text"
    except Exception as e:
        return f"오류: {str(e)}", "text"
