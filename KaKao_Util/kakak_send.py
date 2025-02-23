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

    print(f"✅ Message sent to '{cheat_room_name}': {text}")


## 탭
def SendTab(n=1):
    for _ in range(n):
        ctypes.windll.user32.keybd_event(win32con.VK_TAB, 0, 0, 0)  # Key down
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(win32con.VK_TAB, 0, win32con.KEYEVENTF_KEYUP, 0)  # Key up
        time.sleep(0.1)

# # 엔터

