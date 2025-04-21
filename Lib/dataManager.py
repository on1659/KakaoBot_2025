import sys
from pathlib import Path
import configparser
from Lib import Helper

# ─── ini 파일 경로 설정 ────────────────────────────────────────────────
# 이 스크립트가 있는 폴더의 한 단계 위에 DefaultSetting.ini 가 있다고 가정
base_dir = Path(__file__).resolve().parent
ini_path = base_dir.parent / 'config' / 'DefaultSetting.ini'
ignore_message = "=== 사용 가능한 명령어 ==="

# ─── 파일 존재 여부 체크 ────────────────────────────────────────────────T
if not ini_path.exists():
    raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {ini_path}")

# ─── configparser 초기화 ───────────────────────────────────────────────
# allow_no_value=True 로 값 없이 섹션 내에 키만 나열해도 파싱 가능하도록
config = configparser.ConfigParser(allow_no_value=True)
# 옵션 이름(option) 그대로 보존 (소문자 변환 방지)
config.optionxform = lambda option: option

read_files = config.read(ini_path, encoding='utf-8')
if not read_files:
    raise FileNotFoundError(f"설정 파일을 로드하지 못했습니다: {ini_path}")

if 'RoomList' not in config:
    raise KeyError(f"'RoomList' 섹션이 INI 파일에 없습니다: {ini_path}")

# ─── [RoomList] 섹션의 키 목록을 방 이름 리스트로 변환 ───────────────────────
kakao_opentalk_name_List = [
    name for name, _ in config.items('RoomList')
]

# ─── [EveryMentionDefaultDelayTime] #all 멘션 Delay Time ───────────────────────
EVERY_MENTION_DEFAULT_DELAY_TIME = float(config.get('EveryMentionDefaultDelayTime', 'value'))

# ─── [API_KEY_FILE_PATH] json manager에서 사용될 데이터들 미리 Load ───────────────────────
API_KEY_FILE_PATH   = config.get('APIKey', 'path')
CHATROOM_FILE_PATH = config.get('ChattingRoomSetting', 'path')

def format_available_commands(chat_command) -> str:
    """
    chat_command_Map_All 에 정의된
    key와 description을 예쁘게 포매팅해서 반환
    """
    lines = [ignore_message]
    for key, description, handle in chat_command_Map:
        if key == chat_command:
            continue

        # description 이 'None' 이면 건너뛰거나 설명 없이 key만 출력할 수도 있어요
        if description and description != "None":
            # key 와 description 을 두 줄로 구분
            lines.append(f"{description}")
        else:
            lines.append(f"{description}")
    return "\n\n".join(lines)

def GetData(opentalk_name, chat_command, message):
    """
    '#command' 커맨드가 들어오면
    format_available_commands() 의 결과를 리턴하도록 구현
    """
    return format_available_commands(chat_command), "text"


# ─── 커맨드 맵 정의하기 위해서 선언 ─────────────────────────────────────────────────────

from Lib import youtube, convert_naver_map, every_mention, json_data_manager
from Lib import gpt_api, insta

# ─── 커맨드 맵 정의 ─────────────────────────────────────────────────────
# 1) 풀 맵 정의: key / description / handler
chat_command_Map = [
    ['#command', "None", GetData],
    ['#유툽', "#유툽 (검색) \n 유튜브 검색에서 첫번째 나온 영상을 보여줍니다.", youtube.GetData],
    ['[카카오맵]', "카카오맵->네이버지도 변환기능 \n 카카오맵url을 올리면 자동으로 네이버 주소로 변환해줍니다", convert_naver_map.GetData],
    ['#all', "#all \n모든 인원을 호출합니다. 단! #방인원 (숫자)로 현재 방인원에 정보를 저장해야합니다", every_mention.GetData],
    ['#방인원', "#방인원 (숫자) \n  #all을 사용하기 위한 기능으로, 현재 방인원을 직접 설정해주셔야합니다.",  json_data_manager.save_chatroom_info],
    ['#gpt', "#gpt (내용) \n gpt 에 검색하여 나온 질의를 응답해줍니다. 비용문제로 안될 수 있습니다.", gpt_api.getData],
    ['https://www.instagram.com/', "인스타 한장 요약 \n 인스타 링크를 올리면 한장 요약을 해주는 기능입니다", insta.GetData],
]

# ─── 확인용 출력 ───────────────────────────────────────────────────────
if __name__ == '__main__':
    Helper.CustomPrint("불러온 오픈톡 방 목록:", kakao_opentalk_name_List)
    Helper.CustomPrint("등록된 커맨드:", [cmd for cmd, _, _ in chat_command_Map])
