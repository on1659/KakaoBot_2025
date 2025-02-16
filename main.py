import re
import time, win32con, win32api, win32gui, ctypes
import requests
from bs4 import BeautifulSoup
from apscheduler.schedulers.background import BackgroundScheduler
from pywinauto import clipboard # 채팅창내용 가져오기 위해
import pandas as pd # 가져온 채팅내용 DF로 쓸거라서
import pyperclip

import kakaoRestAPI
import youtube
import win32process

# # 카톡창 이름, (활성화 상태의 열려있는 창)
kakao_opentalk_name = '이더'
chat_command = '#유툽'  # 테스트용..

PBYTE256 = ctypes.c_ubyte * 256
_user32 = ctypes.WinDLL("user32")
GetKeyboardState = _user32.GetKeyboardState
SetKeyboardState = _user32.SetKeyboardState
PostMessage = win32api.PostMessage
SendMessage = win32gui.SendMessage
FindWindow = win32gui.FindWindow
IsWindow = win32gui.IsWindow
GetCurrentThreadId = win32api.GetCurrentThreadId
GetWindowThreadProcessId = _user32.GetWindowThreadProcessId
AttachThreadInput = _user32.AttachThreadInput

MapVirtualKeyA = _user32.MapVirtualKeyA
MapVirtualKeyW = _user32.MapVirtualKeyW

MakeLong = win32api.MAKELONG
w = win32con

# # 채팅방에 메시지 전송
def kakao_sendtext(chatroom_name, text):
    """Send a message to KakaoTalk chatroom using clipboard + Ctrl+V"""

    hwndMain = win32gui.FindWindow(None, chatroom_name)
    if hwndMain == 0:
        print(f"❌ Error: Cannot find chatroom '{chatroom_name}'")
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

    print(f"✅ Message sent to '{chatroom_name}': {text}")

# # 채팅내용 가져오기
def copy_chatroom(chatroom_name):
    # # 핸들 _ 채팅방
    hwndMain = win32gui.FindWindow( None, chatroom_name)
    hwndListControl = win32gui.FindWindowEx(hwndMain, None, "EVA_VH_ListControl_Dblclk", None)

    # #조합키, 본문을 클립보드에 복사 ( ctl + c , v )
    PostKeyEx(hwndListControl, ord('A'), [w.VK_CONTROL], False)
    time.sleep(1)
    PostKeyEx(hwndListControl, ord('C'), [w.VK_CONTROL], False)
    ctext = clipboard.GetData()
    # print(ctext)
    return ctext


# 조합키 쓰기 위해
def PostKeyEx(hwnd, key, shift, specialkey):
    if IsWindow(hwnd):

        ThreadId = GetWindowThreadProcessId(hwnd, None)

        lparam = MakeLong(0, MapVirtualKeyA(key, 0))
        msg_down = w.WM_KEYDOWN
        msg_up = w.WM_KEYUP

        if specialkey:
            lparam = lparam | 0x1000000

        if len(shift) > 0:
            pKeyBuffers = PBYTE256()
            pKeyBuffers_old = PBYTE256()

            SendMessage(hwnd, w.WM_ACTIVATE, w.WA_ACTIVE, 0)
            AttachThreadInput(GetCurrentThreadId(), ThreadId, True)
            GetKeyboardState(ctypes.byref(pKeyBuffers_old))

            for modkey in shift:
                if modkey == w.VK_MENU:
                    lparam = lparam | 0x20000000
                    msg_down = w.WM_SYSKEYDOWN
                    msg_up = w.WM_SYSKEYUP
                pKeyBuffers[modkey] |= 128

            SetKeyboardState(ctypes.byref(pKeyBuffers))
            time.sleep(0.01)
            PostMessage(hwnd, msg_down, key, lparam)
            time.sleep(0.01)
            PostMessage(hwnd, msg_up, key, lparam | 0xC0000000)
            time.sleep(0.01)
            SetKeyboardState(ctypes.byref(pKeyBuffers_old))
            time.sleep(0.01)
            AttachThreadInput(GetCurrentThreadId(), ThreadId, False)

        else:
            SendMessage(hwnd, msg_down, key, lparam)
            SendMessage(hwnd, msg_up, key, lparam | 0xC0000000)

## 탭
def SendTab(n=1):
    for _ in range(n):
        ctypes.windll.user32.keybd_event(win32con.VK_TAB, 0, 0, 0)  # Key down
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(win32con.VK_TAB, 0, win32con.KEYEVENTF_KEYUP, 0)  # Key up
        time.sleep(0.1)


# # 엔터
def SendReturn(hwnd):
    win32api.keybd_event(win32con.VK_TAB, 0, 0, 0)  # Key down
    time.sleep(0.1)
    win32api.keybd_event(win32con.VK_TAB, 0, win32con.KEYEVENTF_KEYUP, 0)  # Key up


def split_youtube_command(pattern, message):
    """
    #유툽 [key word] 형식의 문자열에서
    해시태그와 키워드를 분리합니다.
    예시: "#유툽 [Python tutorials]" -> ("#유툽", "Python tutorials")
    """
    match = re.match(pattern, message)
    if match:
        hashtag = match.group(1)
        keyword = match.group(2)
        return hashtag, keyword
    else:
        return None, None

# # 채팅방 열기
def open_chatroom(chatroom_name):
    # # # 채팅방 목록 검색하는 Edit (채팅방이 열려있지 않아도 전송 가능하기 위하여)
    hwndkakao = win32gui.FindWindow(None, "카카오톡")
    hwndkakao_edit1 = win32gui.FindWindowEx( hwndkakao, None, "EVA_ChildWindow", None)
    hwndkakao_edit2_1 = win32gui.FindWindowEx( hwndkakao_edit1, None, "EVA_Window", None)
    hwndkakao_edit2_2 = win32gui.FindWindowEx( hwndkakao_edit1, hwndkakao_edit2_1, "EVA_Window", None)    # ㄴ시작핸들을 첫번째 자식 핸들(친구목록) 을 줌(hwndkakao_edit2_1)
    hwndkakao_edit3 = win32gui.FindWindowEx( hwndkakao_edit2_2, None, "Edit", None)

    # # Edit에 검색 _ 입력되어있는 텍스트가 있어도 덮어쓰기됨
    win32api.SendMessage(hwndkakao_edit3, win32con.WM_SETTEXT, 0, chatroom_name)
    time.sleep(1)   # 안정성 위해 필요
    SendReturn(hwndkakao_edit3)
    time.sleep(1)


# # 채팅내용 초기 저장 _ 마지막 채팅
def chat_last_save():
    open_chatroom(kakao_opentalk_name)  # 채팅방 열기
    ttext = copy_chatroom(kakao_opentalk_name)  # 채팅내용 가져오기

    a = ttext.split('\r\n')   # \r\n 으로 스플릿 __ 대화내용 인용의 경우 \r 때문에 해당안됨
    df = pd.DataFrame(a)    # DF 으로 바꾸기

    df[0] = df[0].str.replace(r'\[([\S\s]+)\] \[(오전|오후)([0-9:\s]+)\] ', '', regex=True)  # 정규식으로 채팅내용만 남기기

    return df.index[-2], df.iloc[-2, 0]

# # 채팅방 커멘드 체크
def chat_chek_command(cls, clst):
    open_chatroom(kakao_opentalk_name)  # 채팅방 열기
    ttext = copy_chatroom(kakao_opentalk_name)  # 채팅내용 가져오기

    a = ttext.split('\r\n')  # \r\n 으로 스플릿 __ 대화내용 인용의 경우 \r 때문에 해당안됨
    df = pd.DataFrame(a)  # DF 으로 바꾸기

    df[0] = df[0].str.replace(r'\[([\S\s]+)\] \[(오전|오후)([0-9:\s]+)\] ', '', regex=True)    # 정규식으로 채팅내용만 남기기

    if df.iloc[-2, 0] == clst:
        print("채팅 없었음..")
        return df.index[-2], df.iloc[-2, 0]
    else:
        print("채팅 있었음")

        df1 = df.iloc[cls+1 : , 0]   # 최근 채팅내용만 남김

        found = df1[ df1.str.contains(chat_command) ]    # 챗 카운트

        if 1 <= int(found.count()):
            print("-------커멘드 확인!")
            hashtag, keyword = split_youtube_command(chat_command, found            )
            realtimeList = youtube.GetData(keyword)
            kakao_sendtext(kakao_opentalk_name, realtimeList)  # 메시지 전송

            # 명령어 여러개 쓸경우 리턴값으로 각각 빼서 쓰면 될듯. 일단 테스트용으로 위에 하드코딩 해둠
            return df.index[-2], df.iloc[-2, 0]

        else:
            print("커멘드 미확인")
            return df.index[-2], df.iloc[-2, 0]

def main():

    # sched = BackgroundScheduler()
    # sched.start()

    cls, clst = chat_last_save()  # 초기설정 _ 마지막채팅 저장

    # # 매 분 5초마다 job_1 실행
    # sched.add_job(job_1, 'cron', second='*/5', id="test_1")

    while True:
        print("실행중.................")
        cls, clst = chat_chek_command(cls, clst)  # 커멘드 체크
        time.sleep(2)


if __name__ == '__main__':
    #kakaoRestAPI.send_kakao_message("hellow")
   main()

