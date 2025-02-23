import pyautogui
import time
import win32gui

cur_key_count = 0


def FocusWindow(cheat_room_name):

    hwndMain = win32gui.FindWindow(None, cheat_room_name)
    if hwndMain == 0:
        print(f"❌ Error: Cannot find chatroom '{cheat_room_name}'")
        return

    win32gui.SetForegroundWindow(hwndMain)
    cur_key_count = 0

def PrintKey(key):
    global cur_key_count
    print(key)
    cur_key_count = cur_key_count + 1

def mention_all(k):
    """
    K명의 사용자를 모두 태그하는 함수
    @ 입력 후 방향키 (down)를 점진적으로 증가시키며 입력
    """
    time.sleep(0.5)

    pyautogui.write("@")  # @ 입력
    PrintKey("@")
    time.sleep(0.2)

    pyautogui.press("down")
    PrintKey("down")
    time.sleep(0.1)

    pyautogui.press("enter")  # 선택 확정
    PrintKey("enter")
    time.sleep(0.2)

    for i in range(k - 1):  # 0부터 k-2까지 실행
        pyautogui.write("@")  # @ 입력
        PrintKey("@")
        time.sleep(0.2)  # 입력이 반영될 시간 대기

        for _ in range(i + 1):  # i+1만큼 방향키 입력
            pyautogui.press("down")
            PrintKey("down")
            time.sleep(0.1)  # 키 입력 사이 딜레이

        pyautogui.press("enter")  # 선택 확정
        PrintKey("enter")
        time.sleep(0.2)  # 태그가 반영될 시간 대기

"""
Press the backspace key 'count' times.
"""
def press_backspace(count):
    for _ in range(count):
        pyautogui.press("backspace")
        time.sleep(0.1)  # small delay between presses

def GetData(opentalk_name, cheate_commnad, message):
    FocusWindow(opentalk_name)
    mention_all(7)
    press_backspace(cur_key_count)

    return None

def main(kakao_opentalk_name):
    GetData(kakao_opentalk_name, "", "")