import re
import datetime, pyautogui
import time, win32con, win32api, win32gui, ctypes
import pyperclip
from pywinauto import clipboard # 채팅창내용 가져오기 위해
import pandas as pd
from . import Helper
from . import dataManager

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

class ChatProcess:
    def __init__(self, chatroom_name):
        self.chatroom_name = chatroom_name
        self.last_index = 0
        self.IsLoad = 0
        self.init()

    def init(self):
        # Open
        self.hWndKaKao = win32gui.FindWindow(None, "카카오톡")
        self.hwndkakao_edit1 = win32gui.FindWindowEx(self.hWndKaKao, None, "EVA_ChildWindow", None)
        self.hwndkakao_edit2_1 = win32gui.FindWindowEx(self.hwndkakao_edit1, None, "EVA_Window", None)
        self.hwndkakao_edit2_2 = win32gui.FindWindowEx(self.hwndkakao_edit1, self.hwndkakao_edit2_1, "EVA_Window",None)  # ㄴ시작핸들을 첫번째 자식 핸들(친구목록) 을 줌(hwndkakao_edit2_1)
        self.hwndkakao_edit3 = win32gui.FindWindowEx(self.hwndkakao_edit2_2, None, "Edit", None)
        self.chatroomHwnd = win32gui.FindWindow(None, self.chatroom_name)
        if self.chatroomHwnd == 0:
            if Helper.is_debug_mode():
                self.CustomPrint("❌ Error: Cannot find chatroom")
            return
        self.hwndListControl = win32gui.FindWindowEx(self.chatroomHwnd, None, "EVA_VH_ListControl_Dblclk", None)


        # 채팅방열고
        self.open_room(self.chatroom_name)
        CopyText = self.copy_cheat(self.chatroom_name, self.chatroomHwnd, self.hwndListControl)

        df = self.parse_chat_log(CopyText)
        self.CustomPrint("[최초] 파싱 결과:")
        self.CustomPrint(df)

        # 마지막으로 읽은 메시지의 line_idx를 구함 (가장 마지막 행)
        if not df.empty:
            self.last_index = df.iloc[-1]['line_idx']
        else:
            self.last_index = -1

        self.IsLoad = 1
        self.ignoreMessage = dataManager.ignore_message

    def SetForceGroundWindow(self, hwndMain):
        win32gui.SetForegroundWindow(hwndMain)

    def run(self):

        # Load가 실패하면 다시 돌려야됩니다
        if self.IsLoad == 0:
            self.init()

        if self.IsLoad == 0:
            return

        self.open_room(self.chatroom_name)
        CopyText = self.copy_cheat(self.chatroom_name, self.chatroomHwnd, self.hwndListControl)
        df = self.parse_chat_log(CopyText)
        result = self.check_new_commands(df)

        if len(result) > 0:
            for cmd_key, func_ptr in result:
                self.CustomPrint(cmd_key)
        elif Helper.is_debug_mode():
            self.CustomPrint("신규 채팅이 없습니다.")

    def open_room(self, chatroom_name):

        # # # 채팅방 목록 검색하는 Edit (채팅방이 열려있지 않아도 전송 가능하기 위하여)
        self.SetForceGroundWindow(self.hWndKaKao)

        # # Edit에 검색 _ 입력되어있는 텍스트가 있어도 덮어쓰기됨
        win32api.SendMessage(self.hwndkakao_edit3, win32con.WM_SETTEXT, 0, chatroom_name)
        time.sleep(0.5)  # 안정성 위해 필요
        pyautogui.press("enter")
        time.sleep(0.5)

    def send(self, cheat_room_name, hwndMain, text, type):

        if type == "text":
            self.sendtext(cheat_room_name, hwndMain, text)

        elif type == "image":
            self.send_image(hwndMain, cheat_room_name)

    def sendtext(self, cheat_room_name, hwndMain, text):

        # Bring KakaoTalk chat window to the front
        self.SetForceGroundWindow(hwndMain)
        time.sleep(0.3)

        # Simulate pressing Tab key 3 times (to navigate to input box)
        self.SendTab(1)

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

    def send_image(self, hwndMain, cheat_room_name):
        """
        현재 클립보드에 있는 이미지를 카카오톡 채팅방에 붙여넣기(CTRL+V) 후 엔터키를 통해 전송합니다.
        """
        # 카카오톡 창 포커스로 가져오기
        self.SetForceGroundWindow(hwndMain)
        time.sleep(0.3)

        # 입력창으로 포커스를 이동 (필요시 Tab키 시뮬레이션)
        self.SendTab(1)
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
    def SendTab(self, n=1):
        for _ in range(n):
            ctypes.windll.user32.keybd_event(win32con.VK_TAB, 0, 0, 0)  # Key down
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(win32con.VK_TAB, 0, win32con.KEYEVENTF_KEYUP, 0)  # Key up
            time.sleep(0.1)

    def copy_cheat(self, chatroom_name, hwndMain, hwndListControl):
        """
        chatroom_name 방의 hwndMain 창을 포커스한 뒤,
        리스트 컨트롤(hwndListControl)의 모든 텍스트를 복사해서 반환합니다.
        예외 발생 시에는 빈 문자열을 반환하고, 에러를 로깅합니다.
        """
        try:
            # 포커스 강제
            self.SetForceGroundWindow(hwndMain)

            # Ctrl+A, Ctrl+C 조합키로 전체 복사
            self.PostKeyEx(hwndListControl, ord('A'), [w.VK_CONTROL], False)
            time.sleep(0.5)
            self.PostKeyEx(hwndListControl, ord('C'), [w.VK_CONTROL], False)

            # 클립보드에서 데이터 읽기
            ctext = clipboard.GetData()
            return ctext

        except Exception as e:
            # Helper.CustomPrint 이나 CustomPrint 등 로깅 함수 사용
            Helper.CustomPrint(f"❌ copy_cheat 예외 발생: {e}")
            # 디버그 정보가 더 필요하면 traceback 출력도 고려
            import traceback
            Helper.CustomPrint(traceback.format_exc())
            return ""

    def PostKeyEx(self, hwnd, key, shift, specialkey):
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



    def parse_chat_log_as_list(self, text):
        """
        전달받은 채팅 로그(여러 줄)에서 날짜 라인은 무시하고,
        채팅 메시지 라인(예: "[김영태] [오전 11:35] 메시지")을 파싱하여
        메시지 본문만 리스트로 반환합니다.
        """
        chat_pattern = re.compile(r'^\[(?P<name>[^\]]+)\]\s+\[(?P<time>[^\]]+)\]\s+(?P<msg>.+)$')
        date_pattern = re.compile(r'^(?P<date>\d{4}년\s*\d+월\s*\d+일.*)$')

        message_list = []  # 메시지 본문만 저장할 리스트
        current_date = None

        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 날짜 라인인지 확인
            date_match = date_pattern.match(line)
            if date_match:
                # 날짜 라인은 무시 (필요하다면 current_date를 업데이트만 해둬도 됨)
                tokens = date_match.group("date").split()
                # 여기서는 날짜 갱신 로직이 필요 없다면 pass,
                # 혹은 필요 시 current_date를 갱신해도 됨
                continue

            # 채팅 메시지 라인 파싱
            chat_match = chat_pattern.match(line)
            if chat_match:
                msg = chat_match.group("msg").strip()
                message_list.append(msg)

        return message_list

    def parse_chat_log(self, text):
        """
        전달받은 전체 채팅 로그(여러 줄)를 파싱하여 DataFrame을 반환합니다.
        날짜 라인(예: "2025년 3월 20일 목요일")을 만나면 current_date를 업데이트하고,
        채팅 메시지 라인(예: "[김영태] [오후 11:10] [카카오맵] 자양동명진센트라임")은
        이름, 시간, 메시지를 추출하여, 메시지가 여러 줄인 경우 후속 줄은 이전 메시지에 이어붙입니다.
        """
        chat_pattern = re.compile(r'^\[(?P<name>[^\]]+)\]\s+\[(?P<time>[^\]]+)\]\s+(?P<msg>.+)$')
        date_pattern = re.compile(r'^(?P<date>\d{4}년\s*\d+월\s*\d+일.*)$')

        records = []
        current_date = None
        lines = text.splitlines()
        prev_record = None  # 마지막으로 추가된 메시지 기록

        for idx, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # 날짜 라인 검사
            date_match = date_pattern.match(line)
            if date_match:
                raw_date = date_match.group("date")  # 예: "2025년 3월 20일 목요일"
                tokens = raw_date.split()
                if len(tokens) >= 3:
                    try:
                        date_obj = datetime.datetime.strptime(" ".join(tokens[:3]), "%Y년 %m월 %d일")
                        current_date = date_obj.strftime("%Y-%m-%d")
                    except Exception:
                        current_date = raw_date  # 파싱 실패 시 원본 사용
                else:
                    current_date = raw_date
                # 날짜 라인은 메시지로 처리하지 않음.
                prev_record = None
                continue

            # 채팅 메시지 라인 검사
            chat_match = chat_pattern.match(line)
            if chat_match:
                name = chat_match.group("name")
                raw_time = chat_match.group("time")  # 예: "오후 11:10"
                msg = chat_match.group("msg").strip()
                if current_date:
                    timestamp = f"{current_date} {raw_time}"
                else:
                    timestamp = raw_time
                record = {
                    "line_idx": idx,
                    "name": name,
                    "raw_time": raw_time,
                    "date": current_date,
                    "timestamp": timestamp,
                    "message": msg
                }
                records.append(record)
                prev_record = record  # 현재 메시지를 이전 메시지로 저장
            else:
                # 현재 줄이 채팅 메시지 형식이 아니라면, 이전 메시지의 내용에 이어붙임
                if prev_record:
                    prev_record["message"] += "\n" + line
                else:
                    # 이전 메시지가 없다면 별도로 새 메시지로 추가할 수도 있음 (옵션)
                    pass

        return pd.DataFrame(records)

    # 사용 예시
    if __name__ == "__main__":
        sample_text = """[김영태] [오후 11:10] [카카오맵] 자양동명진센트라임
    서울 광진구 아차산로46가길 15 (자양동) https://kko.kakao.com/-YGaamj4Mg"""
        df = parse_chat_log(sample_text)
        Helper.CustomPrint(df)

        ## 5) 추가된 메시지 중 커맨드 포함 확인

    def check_new_commands(self, message_df):
        """
        1) 새로 복사한 전체 로그를 파싱(message_df).
        2) last_index 이후(line_idx > self.last_index)에 추가된 메시지들만 선별(new_msgs).
        3) 메시지 내용에 chat_command_map의 key(명령어)가 포함되어 있으면,
           해당 key에 대응하는 함수포인터 + 전체 메시지(또는 일부)를 묶어
           리스트 형태로 반환한다.
        """

        # 새 메시지: line_idx > self.last_index
        new_msgs = message_df[message_df['line_idx'] > self.last_index]

        results = []
        for idx, row in new_msgs.iterrows():
            msg = row['message']

            if re.match(rf"^{re.escape(self.ignoreMessage)}", msg):
                continue

            for chat_command, desc, chat_func in dataManager.chat_command_Map:
                if chat_command in msg:
                    message = self.split_command(chat_command, msg)
                    resultString, result_type = chat_func(self.chatroom_name, chat_command, message)

                    if resultString is not None:
                        self.send(self.chatroom_name, self.chatroomHwnd, resultString, result_type)  # 메시지 전송

        # 마지막 메시지 인덱스 갱신

        if not message_df.empty:
            self.last_index = message_df.iloc[-1]['line_idx']

        # 결과는 [(function, message), ...] 형태의 리스트
        return results

    def split_command(self, chat_command, command_str):
        """
        #유툽 [key word] 형식의 문자열에서
        해시태그와 키워드를 분리합니다.
        예시: "#유툽 [Python tutorials]" -> ("#유툽", "Python tutorials")
        """
        # 정규식 패턴을 동적으로 생성
        pattern = r"^" + re.escape(chat_command) + r"\s*"
        return re.sub(pattern, "", command_str)

    def CustomPrint(self, messages):
        Helper.CustomPrint(f"{self.chatroom_name}-{messages}")

if __name__ == "__main__":
   proc = ChatProcess("이더")
   time.sleep(0.5)

   while True:
    proc.run()
    time.sleep(0.5)


