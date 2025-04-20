import configparser
from pathlib import Path

# ini 파일 경로
base_dir = Path(__file__).resolve().parent
ini_path = base_dir.parent / 'config' / 'DefaultSetting.ini'

if not ini_path.exists():
    raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {ini_path}")

config = configparser.ConfigParser(allow_no_value=True)
config.optionxform = lambda opt: opt  # 대소문자, 공백 그대로
loaded = config.read(ini_path, encoding='utf-8')
if not loaded:
    raise FileNotFoundError(f"설정 파일을 로드하지 못했습니다: {ini_path}")


API_KEY_FILE_PATH   = config.get('APIKey', 'path')
CHATROOM_FILE_PATH = config.get('ChattingRoomSetting', 'path')

def save_chatroom_info(chatroom_name, chat_command, member_count, file_path=CHATROOM_FILE_PATH):
    """
    이미 chatroom_name이 존재하면 member_count를 업데이트(
    수정),
    없으면 새 레코드를 추가하여 저장합니다.
    """
    print("==== DEBUG START ====")
    print(f"★ Function: save_chatroom_info")
    print(f"★ Parameters: chatroom_name = '{chatroom_name}'")
    print(f"★ Parameters: chat_command  = '{chat_command}'")
    print(f"★ Parameters: member_count  = {member_count}")
    print(f"★ file_path  = '{file_path}'")
    print(f"★ Current working directory: {os.getcwd()}")
    print("---- Step 1: Load existing JSON data ----")

    # 기존 JSON 데이터 불러오기
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                print("    [WARN] JSON 파일이 리스트 형식이 아니라 초기화합니다.")
                data = []
            else:
                print(f"    [INFO] 불러온 기존 레코드 수: {len(data)}")
    except FileNotFoundError:
        print(f"    [WARN] 파일을 찾을 수 없어 새로 만듭니다: {file_path}")
        data = []
    except json.JSONDecodeError as e:
        print(f"    [ERROR] JSON 파싱 에러: {e}")
        print("    [INFO] 데이터를 초기화합니다.")
        data = []

    # 새로운 항목(수정 or 추가) 준비
    chatroom_data = {
        "chatroom_name": chatroom_name,
        "member_count": member_count
        # 필요한 필드가 더 있다면 여기에 추가
    }

    print("---- Step 2: Check if the chatroom already exists ----")
    found = False
    for entry in data:
        if entry.get("chatroom_name") == chatroom_name:
            print(f"    [DEBUG] 동일한 채팅방 이름을 발견: {chatroom_name}, 기존 인원수={entry.get('member_count')}")
            entry["member_count"] = member_count  # 기존 항목 수정
            found = True
            break

    if found:
        print(f"    [INFO] '{chatroom_name}' 항목을 수정했습니다. (새 인원수={member_count})")
    else:
        data.append(chatroom_data)
        print(f"    [INFO] '{chatroom_name}' 항목을 새로 추가했습니다. (인원수={member_count})")

    print("---- Step 3: Save updated data to JSON ----")
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"    [INFO] JSON 파일 저장 완료: {file_path}")
    except Exception as e:
        print(f"    [ERROR] JSON 저장 실패: {e}")

    # 최종 데이터 디버그 출력(선택 사항)
    print(f"    [DEBUG] 최종 data 리스트 개수: {len(data)}")
    print("---- Step 4: Done ----")
    print("==== DEBUG END ====")
    return "", "none"


# 사용 예시 (직접 테스트 시 아래 주석 해제해서 실행해 보세요)
# if __name__ == "__main__":
#     save_chatroom_info("테스트방", "#방인원", 10)
#     save_chatroom_info("테스트방", "#방인원", 5)


# 📥 **저장된 JSON 파일을 불러오는 함수:**
def load_json_info(file_path=CHATROOM_FILE_PATH):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print("✅ JSON 파일 불러오기 완료:")
            return data
    except FileNotFoundError:
        print("❌ JSON 파일을 찾을 수 없습니다.")
    except json.JSONDecodeError:
        print("❌ JSON 파일 형식이 잘못되었습니다.")

    return []


def getJsonData(file_path, search_key: str, search_value: str, column_name: str) -> any:
    """
       JSON 파일에서 특정 채팅방 이름의 지정된 컬럼 데이터를 반환합니다.

       :param file_path: JSON 파일 경로
       :param chatroom_name: 검색할 채팅방 이름
       :param column_name: 가져올 컬럼명 (예: "member_count", "chatroom_name")
       :return: 해당 컬럼의 값 (없을 경우 None 반환)
       """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            dataList = json.load(f)
            if isinstance(dataList, list):
                for data in dataList:
                    if data.get(search_key) == search_value:
                        return data.get(column_name)
            else:
                print("❌ JSON 데이터 형식이 올바르지 않습니다. (리스트가 아님)")
    except FileNotFoundError:
        print(f"❌ 파일을 찾을 수 없습니다: {file_path}")
    except json.JSONDecodeError:
        print(f"❌ JSON 파일 형식이 잘못되었습니다: {file_path}")

    return None

def get_chatroom_data(chatroom_name: str, column_name: str, file_path=CHATROOM_FILE_PATH) -> any:
    return getJsonData(file_path, "chatroom_name", chatroom_name, column_name)

import json
import os

def load_api_keys(json_path=API_KEY_FILE_PATH):
    """
    JSON 파일(예: my_keys.json)에 다음과 같은 형식의 데이터를 로드하여
    os.environ에 설정합니다.

    [
        {
            "name": "YOUTUBE_API_KEY",
            "key": "AIzaSy..."
        },
        {
            "name": "KAKAO_REST_API_KEY",
            "key": "1c1ddcf..."
        },
        ...
    ]

    :param json_path: JSON 파일 경로
    :return: 로드된 key-value 목록(딕셔너리 형태) 반환
    """
    print("==== DEBUG START ====")
    print(f"★ Function: {json_path}")
    print(f"★ JSON file path: {json_path}")
    print(f"★ Current working directory: {os.getcwd()}")

    # JSON 파일 읽기
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # data는 [{"name": "...", "key": "..."}, {...}, ...] 꼴
            if not isinstance(data, list):
                raise ValueError("JSON 최상위가 리스트 형식이 아닙니다.")
    except FileNotFoundError:
        print(f"❌ Error: 파일을 찾을 수 없습니다: {json_path}")
        return []
    except json.JSONDecodeError as e:
        print(f"❌ Error: JSON 파싱 에러: {e}")
        return []
    except ValueError as ve:
        print(f"❌ Error: {ve}")
        return []

    # 읽어온 데이터를 os.environ에 등록
    loaded_keys = []
    for entry in data:
        name = entry.get("name")
        key_value = entry.get("key")

        if not name or not key_value:
            print(f"    [WARN] name 혹은 key 필드가 누락되었습니다: {entry}")
            continue

        os.environ[name] = key_value
        loaded_keys.append((name, key_value))
        print(f"[INFO] os.environ['{name}']에 값이 설정되었습니다.")

    print("==== DEBUG END ====")
    return loaded_keys

#
def test():
    # 📝 **사용 예시:**

    save_chatroom_info("테스트방이야", "", 7)
    save_chatroom_info("하트시그널 토론회장", "", 10)
    save_chatroom_info("이더", "", 3)

    # 📂 **사용 예시:**
    file_path = CHATROOM_FILE_PATH
    chatroom_name = "하트시그널 토론회장"

    # 원하는 컬럼명을 자유롭게 설정 가능
    member_count = get_chatroom_data(chatroom_name, "member_count", file_path)
    print(f"채팅방 '{chatroom_name}'의 인원 수: {member_count}명")

    chatroom_title = get_chatroom_data(chatroom_name, "chatroom_name", file_path)
    print(f"채팅방 이름: {chatroom_title}")

    # 존재하지 않는 컬럼을 요청할 경우
    unknown_data = get_chatroom_data(chatroom_name, "unknown_column", file_path)
    print(f"존재하지 않는 컬럼: {unknown_data}")