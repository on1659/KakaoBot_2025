import time, win32con, win32api, win32gui, ctypes
import pyperclip

def sendtext(cheat_room_name, text):
    """Send a message to KakaoTalk chatroom using clipboard + Ctrl+V"""
    hwndMain = win32gui.FindWindow(None, cheat_room_name)
    if hwndMain == 0:
        print(f"❌ Error: Cannot find chatroom '{cheat_room_name}'")
        return

    # Bring KakaoTalk chat window to the front
    win32gui.SetForegroundWindow(hwndMain)
    time.sleep(0.3)

    # Simulate pressing Tab key 3 times (to navigate to input box)
    SendTab(1)

    # Copy text to clipboard
    pyperclip.copy(text)
    time.sleep(0.2)

    # Simulate Ctrl+V (Paste)
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(0x56, 0, 0, 0)  # V key
    win32api.keybd_event(0x56, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)

    time.sleep(0.2)

    # Simulate Enter Key to Send Message
    win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
    win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)

def send_image(cheat_room_name):
    """
    현재 클립보드에 있는 이미지를 카카오톡 채팅방에 붙여넣기(CTRL+V) 후 엔터키를 통해 전송합니다.
    """
    # 카카오톡 채팅방 창 찾기
    hwndMain = win32gui.FindWindow(None, cheat_room_name)
    if hwndMain == 0:
        print(f"❌ Error: Cannot find chatroom '{cheat_room_name}'")
        return

    # 카카오톡 창 포커스로 가져오기
    win32gui.SetForegroundWindow(hwndMain)
    time.sleep(0.3)

    # 입력창으로 포커스를 이동 (필요시 Tab키 시뮬레이션)
    SendTab(1)
    time.sleep(0.2)

    # Ctrl+V (붙여넣기) 시뮬레이션
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(0x56, 0, 0, 0)  # V 키 (0x56)
    time.sleep(0.1)
    win32api.keybd_event(0x56, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.2)

    # 엔터키 시뮬레이션 (메시지 전송)
    win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
    win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)

## 탭
def SendTab(n=1):
    for _ in range(n):
        ctypes.windll.user32.keybd_event(win32con.VK_TAB, 0, 0, 0)  # Key down
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(win32con.VK_TAB, 0, win32con.KEYEVENTF_KEYUP, 0)  # Key up
        time.sleep(0.1)

# # 엔터

