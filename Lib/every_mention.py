import pyautogui
import time
import win32con, win32gui

def FocusWindow(cheat_room_name):
    hwndMain = win32gui.FindWindow(None, cheat_room_name)
    if hwndMain == 0:
        print(f"❌ Error: Cannot find chatroom '{cheat_room_name}'")
        return

    win32gui.SetForegroundWindow(hwndMain)

def mention_all(k):
    """
    K명의 사용자를 모두 태그하는 함수
    @ 입력 후 방향키 (down)를 점진적으로 증가시키며 입력
    """
    for i in range(k - 1):  # 0부터 k-2까지 실행
        pyautogui.write("@")  # @ 입력
        time.sleep(0.2)  # 입력이 반영될 시간 대기

        for _ in range(i + 1):  # i+1만큼 방향키 입력
            pyautogui.press("down")
            time.sleep(0.1)  # 키 입력 사이 딜레이

        pyautogui.press("enter")  # 선택 확정
        time.sleep(0.2)  # 태그가 반영될 시간 대기

def GetData(opentalk_name, cheate_commnad, message):
    FocusWindow(opentalk_name)
    mention_all(7)
    return