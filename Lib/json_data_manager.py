from . import dataManager
from Lib import Helper
import json
import os
from pathlib import Path

API_KEY_FILE_PATH   = dataManager.API_KEY_FILE_PATH
CHATROOM_FILE_PATH = dataManager.CHATROOM_FILE_PATH


def _atomic_write_json(file_path, data):
    """JSON을 같은 폴더의 임시 파일에 쓴 뒤 원자적으로 교체한다."""
    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_suffix(target.suffix + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temp_path, target)

def save_chatroom_info(chatroom_name, chat_command, member_count, file_path=CHATROOM_FILE_PATH):
    """
    이미 chatroom_name이 존재하면 member_count를 업데이트(
    수정),
    없으면 새 레코드를 추가하여 저장합니다.
    """
    Helper.CustomPrint("==== DEBUG START ====")
    Helper.CustomPrint(f"★ Function: save_chatroom_info")
    Helper.CustomPrint(f"★ Parameters: chatroom_name = '{chatroom_name}'")
    Helper.CustomPrint(f"★ Parameters: chat_command  = '{chat_command}'")
    Helper.CustomPrint(f"★ Parameters: member_count  = {member_count}")
    Helper.CustomPrint(f"★ file_path  = '{file_path}'")
    Helper.CustomPrint(f"★ Current working directory: {os.getcwd()}")
    Helper.CustomPrint("---- Step 1: Load existing JSON data ----")

    # 기존 JSON 데이터 불러오기
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                Helper.CustomPrint("    [WARN] JSON 파일이 리스트 형식이 아니라 초기화합니다.")
                data = []
            else:
                Helper.CustomPrint(f"    [INFO] 불러온 기존 레코드 수: {len(data)}")
    except FileNotFoundError:
        Helper.CustomPrint(f"    [WARN] 파일을 찾을 수 없어 새로 만듭니다: {file_path}")
        data = []
    except json.JSONDecodeError as e:
        Helper.CustomPrint(f"    [ERROR] JSON 파싱 에러: {e}")
        Helper.CustomPrint("    [INFO] 데이터를 초기화합니다.")
        data = []

    # 새로운 항목(수정 or 추가) 준비
    chatroom_data = {
        "chatroom_name": chatroom_name,
        "member_count": member_count,
        "gpt_model": "gpt-3.5-turbo"  # 기본값으로 gpt-3.5-turbo 설정
    }

    Helper.CustomPrint("---- Step 2: Check if the chatroom already exists ----")
    found = False
    for entry in data:
        if entry.get("chatroom_name") == chatroom_name:
            Helper.CustomPrint(f"    [DEBUG] 동일한 채팅방 이름을 발견: {chatroom_name}, 기존 인원수={entry.get('member_count')}")
            entry["member_count"] = member_count  # 기존 항목 수정
            if "gpt_model" not in entry:  # gpt_model이 없으면 추가
                entry["gpt_model"] = "gpt-3.5-turbo"
            found = True
            break

    if found:
        Helper.CustomPrint(f"    [INFO] '{chatroom_name}' 항목을 수정했습니다. (새 인원수={member_count})")
    else:
        data.append(chatroom_data)
        Helper.CustomPrint(f"    [INFO] '{chatroom_name}' 항목을 새로 추가했습니다. (인원수={member_count})")

    Helper.CustomPrint("---- Step 3: Save updated data to JSON ----")
    try:
        _atomic_write_json(file_path, data)
        Helper.CustomPrint(f"    [INFO] JSON 파일 저장 완료: {file_path}")
    except Exception as e:
        Helper.CustomPrint(f"    [ERROR] JSON 저장 실패: {e}")

    # 최종 데이터 디버그 출력(선택 사항)
    Helper.CustomPrint(f"    [DEBUG] 최종 data 리스트 개수: {len(data)}")
    Helper.CustomPrint("---- Step 4: Done ----")
    Helper.CustomPrint("==== DEBUG END ====")
    return "", "none"


def update_chatroom_membercount(chatroom_name, chat_command, member_count, file_path=CHATROOM_FILE_PATH):
    update_chatroom_data(chatroom_name, "member_count", member_count, file_path)
    return "", "none"
    
def update_chatroom_data(chatroom_name, column, value, file_path=CHATROOM_FILE_PATH):
    """
    chatroom_name에 해당하는 채팅방의 column 값을 value로 변경한다.
    column은 'chatroom_name'을 제외한 key만 허용한다.
    json_path가 None이면 DefaultSetting.ini에서 CHATROOM_FILE_PATH를 사용한다.
    """
    # 파일 읽기
    try:
        with open(file_path, 'r', encoding='utf-8') as f: 
            data = json.load(f)
            if not isinstance(data, list):
                Helper.CustomPrint(f"[ERROR] JSON 데이터가 리스트가 아닙니다: {file_path}")
                return False
    except FileNotFoundError:
        Helper.CustomPrint(f"[ERROR] 파일을 찾을 수 없습니다: {file_path}")
        return False
    except json.JSONDecodeError as e:
        Helper.CustomPrint(f"[ERROR] JSON 파싱 에러: {e}")
        return False

    # chatroom_name에 해당하는 항목 찾기
    found = False
    for entry in data:
        if entry.get("chatroom_name") == chatroom_name:
            if column == "chatroom_name":
                Helper.CustomPrint("[ERROR] 'chatroom_name' 컬럼은 수정할 수 없습니다.")
                return False
            entry[column] = value
            found = True
            break

    if not found:
        Helper.CustomPrint(f"[ERROR] 채팅방 '{chatroom_name}'을(를) 찾을 수 없습니다.")
        return False

    # 파일 저장
    try:
        _atomic_write_json(file_path, data)
        Helper.CustomPrint(f"[INFO] '{chatroom_name}'의 '{column}' 값을 '{value}'로 변경 완료.")
        return True
    except Exception as e:
        Helper.CustomPrint(f"[ERROR] 파일 저장 중 에러: {e}")
        return False


# 사용 예시 (직접 테스트 시 아래 주석 해제해서 실행해 보세요)
# if __name__ == "__main__":
#     save_chatroom_info("테스트방", "#방인원", 10)
#     save_chatroom_info("테스트방", "#방인원", 5)


# 📥 **저장된 JSON 파일을 불러오는 함수:**
def load_json_info(file_path=CHATROOM_FILE_PATH):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            Helper.CustomPrint("✅ JSON 파일 불러오기 완료:")
            return data
    except FileNotFoundError:
        Helper.CustomPrint("❌ JSON 파일을 찾을 수 없습니다.")
    except json.JSONDecodeError:
        Helper.CustomPrint("❌ JSON 파일 형식이 잘못되었습니다.")

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
                Helper.CustomPrint("❌ JSON 데이터 형식이 올바르지 않습니다. (리스트가 아님)")
    except FileNotFoundError:
        Helper.CustomPrint(f"❌ 파일을 찾을 수 없습니다: {file_path}")
    except json.JSONDecodeError:
        Helper.CustomPrint(f"❌ JSON 파일 형식이 잘못되었습니다: {file_path}")

    return None

def get_chatroom_data(chatroom_name: str, column_name: str, file_path=CHATROOM_FILE_PATH) -> any:
    """
    채팅방 이름과 컬럼명을 받아서 해당 값을 검색하는 함수
    
    Args:
        chatroom_name (str): 검색할 채팅방 이름
        column_name (str): 검색할 컬럼명 (예: "gpt_model", "member_count")
    
    Returns:
        str: 해당 컬럼의 값, 없으면 None
    """
    return getJsonData(file_path, "chatroom_name", chatroom_name, column_name)

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
    Helper.CustomPrint("==== DEBUG START ====")
    Helper.CustomPrint(f"★ Function: {json_path}")
    Helper.CustomPrint(f"★ JSON file path: {json_path}")
    # JSON 파일 읽기
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # data는 [{"name": "...", "key": "..."}, {...}, ...] 꼴
            if not isinstance(data, list):
                raise ValueError("JSON 최상위가 리스트 형식이 아닙니다.")
    except FileNotFoundError:
        Helper.CustomPrint(f"❌ Error: 파일을 찾을 수 없습니다: {json_path}")
        return []
    except json.JSONDecodeError as e:
        Helper.CustomPrint(f"❌ Error: JSON 파싱 에러: {e}")
        return []
    except ValueError as ve:
        Helper.CustomPrint(f"❌ Error: {ve}")
        return []

    # 읽어온 데이터를 os.environ에 등록
    loaded_keys = []
    for index, entry in enumerate(data, start=1):
        if not isinstance(entry, dict):
            Helper.CustomPrint(f"    [WARN] API 키 {index}번 항목 형식이 올바르지 않습니다.")
            continue
        name = entry.get("name")
        key_value = entry.get("key")

        if not name or not key_value:
            Helper.CustomPrint(
                f"    [WARN] API 키 {index}번 항목의 이름 또는 값이 비어 있습니다"
                + (f" ({name})" if name else "")
            )
            continue

        os.environ[name] = key_value
        loaded_keys.append((name, key_value))
        Helper.CustomPrint(f"[INFO] os.environ['{name}']에 값이 설정되었습니다.")

    Helper.CustomPrint("==== DEBUG END ====")
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
    Helper.CustomPrint(f"채팅방 '{chatroom_name}'의 인원 수: {member_count}명")

    chatroom_title = get_chatroom_data(chatroom_name, "chatroom_name", file_path)
    Helper.CustomPrint(f"채팅방 이름: {chatroom_title}")

    # 존재하지 않는 컬럼을 요청할 경우
    unknown_data = get_chatroom_data(chatroom_name, "unknown_column", file_path)
    Helper.CustomPrint(f"존재하지 않는 컬럼: {unknown_data}")
