import pyautogui
import time
import win32gui

def FocusWindow(cheat_room_name):
    hwndMain = win32gui.FindWindow(None, cheat_room_name)
    if hwndMain == 0:
        print(f"❌ Error: Cannot find chatroom '{cheat_room_name}'")
        return

    time.sleep(0.5)
    win32gui.SetForegroundWindow(hwndMain)
    time.sleep(0.5)
    # 추가: 채팅 입력창을 클릭하여 명시적으로 포커스 설정

    # 예를 들어, 채팅 입력창의 좌표 (x, y)가 (100, 800)라고 가정:

def mention_all(k):
    """
    K명의 사용자를 모두 태그하는 함수
    @ 입력 후 방향키 (down)를 점진적으로 증가시키며 입력
    """
    time.sleep(0.5)

    for i in range(k - 1):  # 0부터 k-2까지 실행
        pyautogui.write("@")  # @ 입력
        print("@")
        time.sleep(0.2)  # 입력이 반영될 시간 대기

        for _ in range(i + 1):  # i+1만큼 방향키 입력
            pyautogui.press("down")
            print("down")
            time.sleep(0.1)  # 키 입력 사이 딜레이

        pyautogui.press("enter")  # 선택 확정
        print("enter")
        time.sleep(0.2)  # 태그가 반영될 시간 대기


def GetData(opentalk_name, cheate_commnad, message):
    FocusWindow(opentalk_name)
    mention_all(3)
    return


def main(kakao_opentalk_name):
    GetData(kakao_opentalk_name, "", "")