# -*- coding: utf-8 -*-
"""
생성형 명령(#tts, #bgm, #pxicel, #imagegen)이 함께 쓰는 도구 모음.

- API 키 조회: config/api_key.json → load_api_keys()가 os.environ에 넣어 둔 값을 읽는다.
  키 이름을 조금 다르게 저장해도(예: ELEVENLABSI_API_KEY) 찾을 수 있게 느슨하게 찾는다.
- 느린 작업의 백그라운드 실행: 명령 핸들러는 폴링 루프 안에서 동기로 불리므로, 수십 초
  걸리는 생성을 그대로 돌리면 그동안 모든 방이 멈춘다. run_in_background()는 안내문을
  바로 돌려주고, 결과는 ChatProcess.add_message_to_queue()로 넘겨 메인 스레드가 전송한다.
  (클립보드·키 입력은 메인 스레드만 만진다 — 워커 스레드는 HTTP와 이미지 변환만 한다.)
- 반환 계약은 기존 핸들러와 같다: (payload, type). type은 "text" | "image" | "file".
"""
import os
import re
import threading
from datetime import datetime
from io import BytesIO

from Lib import Helper, runtime_paths

MEDIA_KEEP_FILES = 40          # saved/media 에 남겨 둘 최근 파일 수 (mp3와 mp4가 함께 쌓인다)
MIN_SEND_IMAGE_SIDE = 512      # 이보다 작은 그림은 카카오톡에서 너무 작게 보여 정수배 확대한다
MSG_BUSY = "이 방에서 이미 생성 중인 작업이 있습니다. 끝난 뒤 다시 시도해주세요."
MSG_UNEXPECTED = "생성 중 오류가 발생했습니다."

_busy_lock = threading.Lock()
_busy_rooms = set()


# ─── 입력 ────────────────────────────────────────────────────────────────

def extract_prompt(chat_command, message):
    """
    명령 뒤의 내용만 돌려준다. 디스패처는 명령이 메시지 맨 앞에 있을 때만 떼어 주므로
    ('얘들아 #tts 안녕' → 그대로 전달됨) 여기서 한 번 더 명령 뒤쪽만 잘라낸다.
    """
    text = message or ""
    index = text.find(chat_command) if chat_command else -1
    if index >= 0:
        text = text[index + len(chat_command):]
    return text.strip()


def find_api_key(names, contains=None):
    """
    names 순서대로 환경변수를 찾고, 없으면 이름에 contains가 들어가고
    KEY/TOKEN/SECRET으로 끝나는 환경변수를 찾는다. 없으면 None.
    """
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    if contains:
        needle = contains.upper()
        for name in sorted(os.environ):
            upper = name.upper()
            if needle in upper and upper.endswith(("KEY", "TOKEN", "SECRET")):
                value = os.environ[name].strip()
                if value:
                    return value
    return None


def env_text(name, default):
    return os.environ.get(name, "").strip() or default


def env_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, "").strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


# 한 모델이 바쁘면(503) 다음 모델로 넘어간다 — 번역이 실패하면 한글이 그대로 넘어가 엉뚱한 그림이 나온다
GEMINI_MODELS = ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash")

_TRANSLATE_INSTRUCTION = (
    "Translate the following text into concise English. "
    "Output only the translation, with no quotes or commentary.\n\n"
)
# 채팅 말투("토끼그려줘", "만렙토끼그려봐")를 글자 그대로 옮기면 "Draw a max-level rabbit."처럼
# 그림 모델이 못 알아듣는 문장이 된다. 그래서 번역이 아니라 '보이는 것의 묘사'로 다시 쓰게 한다.
_IMAGE_INSTRUCTION = (
    "Rewrite the chat user's request below as a prompt for a pixel-art image generator.\n"
    "- Output ONE line of plain English, at most 30 words: the subject, how it looks, "
    "what it is doing, and the setting.\n"
    "- Describe only what should be visible. Drop request words such as 'draw', 'make', 'please'.\n"
    "- Turn slang, game terms and brand names into concrete visual traits "
    "(a 'max-level' character = legendary look with glowing aura and ornate gear; "
    "a fried-chicken brand = golden crispy fried chicken).\n"
    "- Keep every subject and detail the user asked for. Do not add text, captions or watermarks.\n"
    "- No quotes and no explanations.\n\n"
    "Request: "
)


def _ask_gemini(instruction, text):
    """Gemini에 묻고 한 줄 답을 받는다. 모델이 실패하면 다음 모델로 넘어가고, 모두 실패하면 None."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai

        client = genai.Client(api_key=api_key)  # 변수에 잡아 둬야 한다 — 임시 객체면 요청 전에 닫힌다
    except Exception as e:
        Helper.CustomPrint(f"⚠️ Gemini 준비 실패 ({type(e).__name__}): {e}")
        return None

    models = [env_text("GEMINI_TRANSLATE_MODEL", GEMINI_MODELS[0])]
    models += [model for model in GEMINI_MODELS if model not in models]
    for model in models:
        try:
            response = client.models.generate_content(model=model, contents=instruction + text)
            answer = " ".join((response.text or "").split())
            if answer:
                return answer
        except Exception as e:
            Helper.CustomPrint(f"⚠️ 설명 번역 실패 ({model}, {type(e).__name__}): {str(e)[:120]}")
    return None


def to_english(text, purpose=None):
    """
    영어만 제대로 알아듣는 생성 모델(PixelLab 등)에 넘길 설명을 영어로 옮긴다.
    한글 설명을 그대로 보내면 설명과 무관한 결과가 나온다 (2026-11 실측).
    - purpose=None: 그대로 번역한다. 이미 영어(ASCII)면 손대지 않는다.
    - purpose="image": 번역 대신 그림 모델용 묘사로 다시 쓴다 (영어 입력도 다듬는다).
    GEMINI_API_KEY가 없거나 모든 모델이 실패하면 원문을 그대로 돌려준다 — 호출한 쪽에서
    결과에 한글이 남아 있는지 보고 판단한다.
    """
    if not text:
        return text
    if purpose != "image" and text.isascii():
        return text
    instruction = _IMAGE_INSTRUCTION if purpose == "image" else _TRANSLATE_INSTRUCTION
    answer = _ask_gemini(instruction, text)
    if not answer:
        return text
    Helper.CustomPrint(f"🌐 설명 번역: {text[:40]!r} → {answer[:120]!r}")
    return answer[:500]


# ─── 파일 저장 ───────────────────────────────────────────────────────────

def media_dir():
    # 호출 시점에 계산한다 — 테스트가 runtime_paths.SAVED_DIR을 임시 폴더로 바꾼다
    path = runtime_paths.SAVED_DIR / "media"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _slug(text, limit=20):
    slug = re.sub(r"[^\w]+", "_", text or "", flags=re.UNICODE).strip("_")
    return slug[:limit].strip("_") or "audio"


def save_media(prefix, text, extension, data):
    """생성된 바이트를 saved/media 에 저장하고 절대 경로(str)를 돌려준다."""
    folder = media_dir()
    stamp = datetime.now().strftime("%m%d_%H%M%S")
    path = folder / f"{prefix}_{_slug(text)}_{stamp}.{extension}"
    path.write_bytes(data)
    _prune(folder)
    return str(path.resolve())


def _prune(folder):
    try:
        files = sorted(
            (p for p in folder.iterdir() if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in files[MEDIA_KEEP_FILES:]:
            old.unlink()
    except OSError:
        pass  # 정리 실패가 전송을 막을 이유는 없다


# ─── 이미지 → 클립보드용 DIB ─────────────────────────────────────────────

def image_bytes_to_dib(data, min_side=MIN_SEND_IMAGE_SIDE):
    """
    PNG/JPEG 등 이미지 바이트를 CF_DIB용 바이트로 바꾼다 (BMP에서 14바이트 파일 헤더 제거).
    투명 배경은 흰색으로 채우고, 작은 그림(픽셀아트)은 흐려지지 않게 정수배로 확대한다.
    """
    from PIL import Image

    image = Image.open(BytesIO(data))
    image.load()
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, rgba)
    image = image.convert("RGB")

    shortest = min(image.size)
    if 0 < shortest < min_side:
        factor = -(-min_side // shortest)  # 올림 나눗셈
        image = image.resize(
            (image.width * factor, image.height * factor), Image.NEAREST
        )

    buffer = BytesIO()
    image.save(buffer, "BMP")
    return buffer.getvalue()[14:]


# ─── 백그라운드 실행 ─────────────────────────────────────────────────────

def _find_chat(room):
    from Lib import log_monitor  # 엔진이 여기에 ChatProcess 목록을 등록해 둔다

    for chat in log_monitor.global_chat_list or []:
        if getattr(chat, "chatroom_name", None) == room:
            return chat
    return None


def run_in_background(room, ack, work):
    """
    work() -> (payload, type) 를 별도 스레드에서 실행한다.
    - 방의 ChatProcess를 찾으면: 안내문(ack, 없으면 전송 없음)을 바로 반환하고 결과는 그 방의 메시지 큐로 보낸다.
    - 못 찾으면(단독 실행·테스트): 그 자리에서 실행해 결과를 그대로 반환한다.
    방마다 한 번에 한 작업만 받는다 — 연타로 유료 API를 여러 번 부르지 않게.
    """
    chat = _find_chat(room)
    if chat is None:
        return _guarded(work)

    with _busy_lock:
        if room in _busy_rooms:
            return MSG_BUSY, "text"
        _busy_rooms.add(room)

    def target():
        try:
            payload, kind = _guarded(work)
            chat.add_message_to_queue(payload, kind)
        except Exception as e:
            Helper.CustomPrint(f"❌ [{room}] 생성 결과 전달 실패: {e}")
        finally:
            with _busy_lock:
                _busy_rooms.discard(room)

    threading.Thread(target=target, name=f"media-{room}", daemon=True).start()
    if not ack:
        return "", "none"  # 금방 끝나는 작업은 안내문 없이 결과만 보낸다
    return ack, "text"


def _guarded(work):
    try:
        return work()
    except Exception as e:
        Helper.CustomPrint(f"❌ 생성 작업 미처리 예외 ({type(e).__name__}): {e}")
        return MSG_UNEXPECTED, "text"
