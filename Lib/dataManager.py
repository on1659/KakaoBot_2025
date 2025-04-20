import sys
from pathlib import Path
import configparser

from Lib import youtube, convert_naver_map, every_mention, json_data_manager
from Lib import gpt_api, insta

# ─── ini 파일 경로 설정 ────────────────────────────────────────────────
# 이 스크립트가 있는 폴더의 한 단계 위에 DefaultSetting.ini 가 있다고 가정
base_dir = Path(__file__).resolve().parent
ini_path = base_dir.parent / 'config' / 'DefaultSetting.ini'

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
# config.items('RoomList') → [(room_name, None), ...]
kakao_opentalk_name_List = [
    room_name for room_name, _ in config.items('RoomList')
    if room_name.strip()
]

# ─── 커맨드 맵 정의 ─────────────────────────────────────────────────────
chat_command_Map = [
    ['#유툽',    youtube.GetData],
    ['[카카오맵]', convert_naver_map.GetData],
    ['#all',     every_mention.GetData],
    ['#방인원',   json_data_manager.save_chatroom_info],
    ['#gpt',     gpt_api.getData],
    ['https://www.instagram.com/', insta.GetData],
]

# ─── 확인용 출력 ───────────────────────────────────────────────────────
if __name__ == '__main__':
    print("불러온 오픈톡 방 목록:", kakao_opentalk_name_List)
    print("등록된 커맨드:", [cmd for cmd, _ in chat_command_Map])
