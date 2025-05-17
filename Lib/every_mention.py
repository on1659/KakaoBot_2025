import pyautogui
import time
import win32gui
from Lib import json_data_manager
from Lib import dataManager, Helper

DELAY_TIME_RATE = dataManager.EVERY_MENTION_DEFAULT_DELAY_TIME

def FocusWindow(cheat_room_name):

    hwndMain = win32gui.FindWindow(None, cheat_room_name)
    if hwndMain == 0:
        Helper.CustomPrint(f"❌ Error: Cannot find chatroom '{cheat_room_name}'")
        return

    win32gui.SetForegroundWindow(hwndMain)
    cur_key_count = 0

def PrintKey(key):
    global cur_key_count

def mention_all(k):

    """
    K명의 사용자를 모두 태그하는 함수
    @ 입력 후 방향키 (d
    wn)를 점진적으로 증가시키며 입력
    """
    time.sleep(DELAY_TIME_RATE * 5)

    pyautogui.write("@")  # @ 입력
    PrintKey("@")
    time.sleep(DELAY_TIME_RATE * 2)

    pyautogui.press("down")
    PrintKey("down")
    time.sleep(DELAY_TIME_RATE)

    pyautogui.press("enter")  # 선택 확정
    PrintKey("enter")
    time.sleep(DELAY_TIME_RATE * 2)

    for i in range(k - 1):  # 0부터 k-2까지 실행
        pyautogui.write("@")  # @ 입력
        PrintKey("@")
        time.sleep(DELAY_TIME_RATE * 2)  # 입력이 반영될 시간 대기

        for _ in range(i + 1):  # i+1만큼 방향키 입력
            pyautogui.press("down")
            PrintKey("down")
            time.sleep(DELAY_TIME_RATE)  # 키 입력 사이 딜레이

        pyautogui.press("enter")  # 선택 확정
        PrintKey("enter")
        time.sleep(DELAY_TIME_RATE * 2)  # 태그가 반영될 시간 대기

    pyautogui.press("enter")  # 선택 확정
    PrintKey("enter")
    time.sleep(DELAY_TIME_RATE * 2)  # 태그가 반영될 시간 대기


def select_all_and_delete():
    # Ctrl+A: 모든 텍스트 선택
    # Ctrl+A: 모든 텍스트 선택
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(DELAY_TIME_RATE * 2)  # 선택 상태가 반영되도록 잠시 대기

    # Backspace: 선택된 텍스트 삭제
    pyautogui.press('backspace')
    time.sleep(DELAY_TIME_RATE * 2)


def GetData(opentalk_name, cheate_commnad, message):
    FocusWindow(opentalk_name)
    member_value = json_data_manager.get_chatroom_data(opentalk_name, "member_count")

    if member_value is None:
        Helper.CustomPrint(f"❌ Error: '{opentalk_name}'에서 'member_count' 값을 찾지 못했습니다. 0으로 처리합니다.")
        member_count = 0
        return "방 인원을 직접 세팅해주세요", "none"
    else:
        try:
            member_count = int(member_value)
        except ValueError:
            Helper.CustomPrint(f"❌ Error: 'member_count'가 정수로 변환 불가능한 값({member_value})입니다. 0으로 처리합니다.")
            member_count = 0

    mention_all(member_count)
    # select_all_and_delete()
    return None, "none"

#def main(kakao_opentalk_name):
#    GetData(kakao_opentalk_name, "", "")