"""'짜장 vs 짬뽕' 형태의 메시지에서 선택지 하나를 랜덤으로 골라준다."""

import random
import re

# 'vs' 바로 앞뒤에 영문·숫자가 붙어 있으면 단어의 일부로 본다.
# → '뱅호vs빠끄', '짜장 VS 짬뽕'은 인식하고 'vscode', 'devs', '1vs1'은 무시한다.
VS_PATTERN = re.compile(r"(?<![A-Za-z0-9])vs\.?(?![A-Za-z0-9])", re.IGNORECASE)
SEPARATOR = re.compile(r"\s*" + VS_PATTERN.pattern + r"\s*", re.IGNORECASE)


class PatternKey(str):
    """문자열 명령 키처럼 쓰이지만 정규식으로 위치를 찾는 키 (chat_process.match_command 참고).

    str 값("vs")은 권한 설정·도움말에서 기능을 식별하는 데 쓰인다.
    """

    def __new__(cls, value, pattern):
        key = super().__new__(cls, value)
        key.pattern = pattern
        return key

    def find_in(self, message):
        match = self.pattern.search(message)
        return (match.start(), len(match.group())) if match else (-1, 0)


TRIGGER = PatternKey("vs", VS_PATTERN)

MAX_OPTIONS = 10
# 일상 대화("한국 vs 일본 경기 봤어? 진짜 재밌더라")를 걸러내기 위한 선택지 크기 제한.
MAX_OPTION_LENGTH = 20
MAX_OPTION_WORDS = 4

_rng = random.SystemRandom()


def parse_options(message):
    """선택지 목록을 반환한다. 일상 대화로 보이면 None."""
    text = message.strip()
    if not text or "\n" in text or "http://" in text or "https://" in text:
        return None
    options = [part.strip().rstrip("?!？！").strip() for part in SEPARATOR.split(text)]
    if len(options) < 2 or len(options) > MAX_OPTIONS:
        return None
    for option in options:
        if not option or len(option) > MAX_OPTION_LENGTH or len(option.split()) > MAX_OPTION_WORDS:
            return None
    return options


def GetData(opentalk_name, chat_command, message, rng=_rng):
    options = parse_options(message)
    if options is None:
        return "", "none"
    choice = rng.choice(options)
    # 응답이 두 줄이라 parse_options가 거부하므로, 봇 이름 설정이 어긋나 자기 메시지를
    # 다시 읽더라도 또 반응하지 않는다.
    quoted = " vs ".join(f'"{option}"' for option in options)
    return f"{quoted}\n  ▶ {choice}", "text"
