# -*- coding: utf-8 -*-
"""
ElevenLabs 명령.

- #tts (내용): 글을 음성으로 읽어 전송한다.
- #bgm (내용): 설명에 맞는 배경음악(연주곡)을 만들어 전송한다. (ElevenLabs Music API)

받은 mp3는 커버 이미지를 붙인 동영상(mp4)으로 바꿔 보낸다 — mp3 첨부파일과 달리 채팅에서
바로 재생된다 (audio_video 참조). 변환에 실패하면 mp3 파일을 그대로 보낸다.

API 키는 config/api_key.json 의 ELEVENLABS_API_KEY (load_api_keys()가 os.environ에 주입).
같은 파일에 아래 이름으로 항목을 추가하면 기본값을 바꿀 수 있다 (모두 선택):
  ELEVENLABS_VOICE_ID   — #tts 목소리 (기본: ElevenLabs 기본 제공 보이스)
  ELEVENLABS_TTS_MODEL  — #tts 모델 (기본: eleven_multilingual_v2, 한국어 지원)
  ELEVENLABS_BGM_SECONDS — #bgm 기본 길이(초, 10~20, 기본 20)
  ELEVENLABS_MUSIC_MODEL — #bgm 모델 (기본: music_v1)
  ELEVENLABS_SEND_AS    — video(기본, 바로 재생) | file(mp3 첨부파일)

#bgm은 "#bgm 15초 잔잔한 피아노"처럼 맨 앞에 길이를 적으면 그 길이로 만든다.
(길이만큼 크레딧이 든다. 설명은 영어로 옮겨 보내고, 가사 없는 연주곡으로 고정한다.)

반환 계약: 성공 (보낼 파일 경로, "file") / 실패 (안내문, "text").
어떤 실패에서도 예외를 내보내지 않는다 — 디스패처의 광역 except가 삼키면 방이 무응답이 된다.
"""
import re

import requests

from Lib import Helper, audio_video, media_common

API_BASE = "https://api.elevenlabs.io/v1"
KEY_NAMES = ("ELEVENLABS_API_KEY", "ELEVEN_API_KEY", "XI_API_KEY")

DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"   # 공식 문서 예제의 기본 제공 보이스
DEFAULT_TTS_MODEL = "eleven_multilingual_v2"
OUTPUT_FORMAT = "mp3_44100_128"

MAX_TTS_CHARS = 500   # 글자 수만큼 크레딧이 나가므로 한 번에 읽을 길이를 제한한다
MAX_BGM_CHARS = 300
DEFAULT_BGM_SECONDS = 20
MIN_BGM_SECONDS = 10
MAX_BGM_SECONDS = 20   # 길이만큼 크레딧이 들어 한 번에 20초까지만 만든다
DEFAULT_MUSIC_MODEL = "music_v1"
_LENGTH_PREFIX = re.compile(r"^(\d{1,3})\s*(초|분)\s+(.+)$", re.DOTALL)
TTS_TIMEOUT_SEC = 30
BGM_TIMEOUT_SEC = 300

MSG_NO_KEY = "ElevenLabs API 키가 없습니다. API 키 설정에 ELEVENLABS_API_KEY를 추가해주세요."
MSG_TTS_USAGE = "사용법: #tts (읽을 내용)"
MSG_BGM_USAGE = "사용법: #bgm (음악 설명)\n예) #bgm 잔잔한 로파이 피아노 / #bgm 15초 신나는 8비트 게임 음악 (최대 20초)"
MSG_BAD_KEY = "ElevenLabs API 키가 올바르지 않습니다. 관리자에게 문의해주세요."
MSG_NO_PERMISSION = "ElevenLabs API 키에 이 기능의 권한이 없습니다. 키 권한 설정을 확인해주세요."
MSG_QUOTA = "ElevenLabs 크레딧이 부족합니다."
MSG_RATE_LIMITED = "ElevenLabs 요청이 몰렸습니다. 잠시 후 다시 시도해주세요."
MSG_VOICE = "ElevenLabs 목소리(voice)를 찾을 수 없습니다. ELEVENLABS_VOICE_ID를 확인해주세요."
MSG_NETWORK = "ElevenLabs에 연결하지 못했습니다. 잠시 후 다시 시도해주세요."
MSG_EMPTY = "ElevenLabs가 빈 응답을 보냈습니다. 다시 시도해주세요."
MSG_BGM_ACK = "🎵 BGM을 요청하였습니다. 잠시만 기다려주세요."
MSG_PAID_PLAN = "ElevenLabs 음악 생성은 유료 플랜에서만 쓸 수 있습니다."


def _api_key():
    return media_common.find_api_key(KEY_NAMES, contains="ELEVENLABS")


def _error_message(response):
    """ElevenLabs 오류 응답을 안내문으로 바꾼다. detail은 {status, message} 또는 검증 오류 목록이다."""
    status, message = "", ""
    try:
        detail = response.json().get("detail")
        if isinstance(detail, dict):
            status = str(detail.get("status", ""))
            message = str(detail.get("message", ""))
        elif isinstance(detail, list) and detail:
            message = str(detail[0].get("msg", "")) if isinstance(detail[0], dict) else str(detail[0])
        elif isinstance(detail, str):
            message = detail
    except ValueError:
        message = response.text[:200]

    Helper.CustomPrint(
        f"❌ [elevenlabs] HTTP {response.status_code} status={status!r} message={message[:200]!r}"
    )

    # 크레딧 부족도 401로 오므로 HTTP 코드보다 status 문자열을 먼저 본다
    if "quota" in status:
        return MSG_QUOTA
    if "paid" in status or response.status_code == 402:
        return MSG_PAID_PLAN
    if "permission" in status:
        return MSG_NO_PERMISSION
    if "voice" in status:
        return MSG_VOICE
    if response.status_code == 401:
        return MSG_BAD_KEY
    if response.status_code == 429:
        return MSG_RATE_LIMITED
    summary = message[:120] or f"HTTP {response.status_code}"
    return f"ElevenLabs 오류: {summary}"


def _request_audio(path, body, timeout):
    """반환: (오디오 바이트, None) 또는 (None, 안내문)."""
    api_key = _api_key()
    if not api_key:
        return None, MSG_NO_KEY
    try:
        response = requests.post(
            f"{API_BASE}/{path}",
            params={"output_format": OUTPUT_FORMAT},
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json=body,
            timeout=timeout,
        )
    except requests.RequestException as e:
        Helper.CustomPrint(f"❌ [elevenlabs] 요청 실패: {type(e).__name__}: {e}")
        return None, MSG_NETWORK

    if response.status_code != 200:
        return None, _error_message(response)
    if not response.content:
        return None, MSG_EMPTY
    return response.content, None


def synthesize_speech(text):
    voice_id = media_common.env_text("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
    model_id = media_common.env_text("ELEVENLABS_TTS_MODEL", DEFAULT_TTS_MODEL)
    return _request_audio(
        f"text-to-speech/{voice_id}",
        {"text": text, "model_id": model_id},
        TTS_TIMEOUT_SEC,
    )


def split_seconds(description):
    """'15초 피아노' → (15, '피아노'). 최대 길이를 넘으면('2분 록') 최대 길이로 자른다. 길이를 안 적으면 기본 길이를 쓴다."""
    match = _LENGTH_PREFIX.match(description)
    if match:
        seconds = int(match.group(1)) * (60 if match.group(2) == "분" else 1)
        seconds = max(MIN_BGM_SECONDS, min(MAX_BGM_SECONDS, seconds))
        return seconds, match.group(3).strip()
    default = media_common.env_int(
        "ELEVENLABS_BGM_SECONDS", DEFAULT_BGM_SECONDS, MIN_BGM_SECONDS, MAX_BGM_SECONDS
    )
    return default, description


def generate_music(description, seconds):
    """ElevenLabs Music API로 가사 없는 연주곡을 만든다. 반환: (오디오 바이트, None) 또는 (None, 안내문)."""
    return _request_audio(
        "music",
        {
            "prompt": media_common.to_english(description),
            "music_length_ms": seconds * 1000,
            "model_id": media_common.env_text("ELEVENLABS_MUSIC_MODEL", DEFAULT_MUSIC_MODEL),
            "force_instrumental": True,
        },
        BGM_TIMEOUT_SEC,
    )


def _playable(mp3_path, label, text):
    """채팅에서 바로 재생되는 동영상으로 바꾼다. 설정으로 껐거나 변환에 실패하면 mp3 그대로."""
    if media_common.env_text("ELEVENLABS_SEND_AS", "video").lower() == "file":
        return mp3_path
    return audio_video.audio_to_video(mp3_path, label, text) or mp3_path


def tts(opentalk_name, chat_command, message):
    """#tts 핸들러 — 음성 생성과 동영상 변환에 몇 초 걸려 백그라운드로 돌린다 (안내문 없이 결과만 전송)."""
    text = media_common.extract_prompt(chat_command, message)
    if not text:
        return MSG_TTS_USAGE, "text"
    if len(text) > MAX_TTS_CHARS:
        return f"#tts는 한 번에 {MAX_TTS_CHARS}자까지 읽을 수 있습니다. (현재 {len(text)}자)", "text"
    if not _api_key():
        return MSG_NO_KEY, "text"

    def work():
        audio, error = synthesize_speech(text)
        if error:
            return error, "text"
        path = media_common.save_media("tts", text, "mp3", audio)
        Helper.CustomPrint(f"✅ [elevenlabs] TTS 준비 완료 ({len(audio)} bytes)")
        return _playable(path, "TTS", text), "file"

    return media_common.run_in_background(opentalk_name, None, work)


def bgm(opentalk_name, chat_command, message):
    """#bgm 핸들러 — 음악 생성에 수십 초~몇 분 걸려 백그라운드로 돌린다 (안내문 먼저, 결과는 나중에)."""
    description = media_common.extract_prompt(chat_command, message)
    if not description:
        return MSG_BGM_USAGE, "text"
    if len(description) > MAX_BGM_CHARS:
        return f"#bgm 설명은 {MAX_BGM_CHARS}자까지 쓸 수 있습니다. (현재 {len(description)}자)", "text"
    if not _api_key():
        return MSG_NO_KEY, "text"

    seconds, description = split_seconds(description)

    def work():
        audio, error = generate_music(description, seconds)
        if error:
            return error, "text"
        path = media_common.save_media("bgm", description, "mp3", audio)
        Helper.CustomPrint(f"✅ [elevenlabs] BGM 준비 완료 ({seconds}초, {len(audio)} bytes)")
        return _playable(path, "BGM", description), "file"

    return media_common.run_in_background(opentalk_name, MSG_BGM_ACK, work)
