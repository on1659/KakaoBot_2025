import re
import datetime, pyautogui
import time, win32con, win32api, win32gui, ctypes
import pyperclip
from pywinauto import clipboard # 채팅창내용 가져오기 위해
import pandas as pd
from . import Helper
from . import dataManager
import win32clipboard

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
        self.BotName = dataManager.BOT_NAME
        self.init()

    def init(self):
        # Open
        self.init_open_romm(self.chatroom_name)

        if self.chatroomHwnd == 0:
            if Helper.is_debug_mode():
                self.CustomPrint("❌ Error: Cannot find chatroom")
            return
        self.hwndListControl = win32gui.FindWindowEx(self.chatroomHwnd, None, "EVA_VH_ListControl_Dblclk", None)

        # 채팅방열고
        # self.open_room(self.chatroom_name)
        CopyText = self.copy_cheat(self.chatroom_name, self.chatroomHwnd, self.hwndListControl)

        df = self.parse_chat_log(CopyText)
        # 파싱 결과는 콘솔에만 출력하고 파일에는 저장하지 않음
        self.CustomPrint(f"[최초] 파싱 결과:", saveLog=False)
        self.CustomPrint(str(df), saveLog=False)

        # 마지막으로 읽은 메시지의 line_idx를 구함 (가장 마지막 행)
        if not df.empty:
            self.last_index = df.iloc[-1]['line_idx']
        else:
            self.last_index = -1

        self.IsLoad = 1

    def SetForceGroundWindow(self, hwndMain):
        """
        주어진 창 핸들을 전면으로 가져오는 메서드입니다.
        창이 최소화되어 있다면 복원하고, 포커스를 설정합니다.
        """
        if not win32gui.IsWindow(hwndMain):
            raise Exception(f"유효하지 않은 창 핸들: {hwndMain}")
        
        # 현재 포커스된 창 정보 저장
        current_focus = win32gui.GetForegroundWindow()
        current_focus_title = win32gui.GetWindowText(current_focus)
        
        # 이미 원하는 창이 포커스되어 있다면 바로 반환
        if current_focus == hwndMain:
            return
        
        # 창이 최소화되어 있다면 복원
        if win32gui.IsIconic(hwndMain):
            win32gui.ShowWindow(hwndMain, win32con.SW_RESTORE)
            time.sleep(0.2)  # 창 복원 대기
        
        # 현재 포커스된 창이 카카오톡 창인 경우, 포커스 해제
        if "카카오톡" in current_focus_title:
            # 포커스 해제를 위해 데스크톱 창으로 포커스 이동
            desktop_hwnd = win32gui.GetDesktopWindow()
            win32gui.SetForegroundWindow(desktop_hwnd)
            time.sleep(0.2)  # 포커스 해제 대기
        
        # 창을 전면으로 가져오기
        win32gui.SetForegroundWindow(hwndMain)
        time.sleep(0.3)  # 포커스 변경 대기
        
        # 포커스가 변경되었는지 확인
        if win32gui.GetForegroundWindow() != hwndMain:
            # 한 번 더 시도
            desktop_hwnd = win32gui.GetDesktopWindow()
            win32gui.SetForegroundWindow(desktop_hwnd)
            time.sleep(0.2)
            win32gui.SetForegroundWindow(hwndMain)
            time.sleep(0.3)
            
            if win32gui.GetForegroundWindow() != hwndMain:
                raise Exception(f"창 포커스 실패 - 현재 포커스된 창: {current_focus_title}")

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
        pyperclip.copy("")

        if len(result) > 0:
            for cmd_key, func_ptr in result:
                self.CustomPrint(cmd_key)
        elif Helper.is_debug_mode():
            self.CustomPrint("신규 채팅이 없습니다.", saveLog=False)


    def init_open_romm(self, chatroom_name):
        """채팅방 초기화 및 창 핸들 검증"""
        try:
            # 카카오톡 메인 창 찾기
            hWndKaKao = win32gui.FindWindow(None, "카카오톡")
            if hWndKaKao == 0:
                Helper.CustomPrint(f"❌ 카카오톡 창을 찾을 수 없습니다. 카카오톡이 실행 중인지 확인해주세요.")
                return
            
            # 카카오톡 창이 최소화되어 있다면 복원
            if win32gui.IsIconic(hWndKaKao):
                win32gui.ShowWindow(hWndKaKao, win32con.SW_RESTORE)
                time.sleep(0.5)
            
            # 채팅방 검색 Edit 컨트롤 찾기
            hwndkakao_edit1 = win32gui.FindWindowEx(hWndKaKao, None, "EVA_ChildWindow", None)
            if hwndkakao_edit1 == 0:
                Helper.CustomPrint(f"❌ 카카오톡 Edit 컨트롤을 찾을 수 없습니다.")
                return
                
            hwndkakao_edit2_1 = win32gui.FindWindowEx(hwndkakao_edit1, None, "EVA_Window", None)
            hwndkakao_edit2_2 = win32gui.FindWindowEx(hwndkakao_edit1, hwndkakao_edit2_1, "EVA_Window", None)
            self.hwndkakao_edit3 = win32gui.FindWindowEx(hwndkakao_edit2_2, None, "Edit", None)
            
            if self.hwndkakao_edit3 == 0:
                Helper.CustomPrint(f"❌ 카카오톡 검색 Edit을 찾을 수 없습니다.")
                return

            # 채팅방 창 핸들 찾기
            self.chatroomHwnd = win32gui.FindWindow(None, chatroom_name)
            
            # 채팅방이 없으면 검색으로 열기
            if self.chatroomHwnd == 0:
                Helper.CustomPrint(f"📝 채팅방 '{chatroom_name}'을 검색하여 열기 시도...")
                
                # 검색창에 채팅방 이름 입력
                SendMessage(self.hwndkakao_edit3, win32con.WM_SETTEXT, 0, chatroom_name)
                time.sleep(1)
                self.SendReturn(self.hwndkakao_edit3)
                time.sleep(1)
                
                # 다시 채팅방 창 핸들 찾기
                self.chatroomHwnd = win32gui.FindWindow(None, chatroom_name)
                
                if self.chatroomHwnd == 0:
                    Helper.CustomPrint(f"❌ 채팅방 '{chatroom_name}'을 찾을 수 없습니다.")
                    return
                else:
                    Helper.CustomPrint(f"✅ 채팅방 '{chatroom_name}' 열기 성공")
            else:
                Helper.CustomPrint(f"✅ 채팅방 '{chatroom_name}' 이미 열려있음")
                
        except Exception as e:
            Helper.CustomPrint(f"❌ 채팅방 초기화 중 오류 발생: {str(e)}")
            return

    def validate_window_handle(self, hwnd, window_name):
        """창 핸들이 유효한지 검증하고 필요시 재검색"""
        if hwnd == 0:
            return False
            
        if not win32gui.IsWindow(hwnd):
            Helper.CustomPrint(f"❌ [{window_name}] 창 핸들이 유효하지 않습니다: {hwnd}")
            return False
            
        # 창이 숨겨져 있거나 최소화되어 있는지 확인
        if not win32gui.IsWindowVisible(hwnd):
            Helper.CustomPrint(f"❌ [{window_name}] 창이 숨겨져 있습니다: {hwnd}")
            return False
            
        return True


    def refresh_window_handles(self):
        """창 핸들들을 새로고침"""
        try:
            # 카카오톡 메인 창 재검색
            hWndKaKao = win32gui.FindWindow(None, "카카오톡")
            if hWndKaKao == 0:
                Helper.CustomPrint("❌ 카카오톡 창을 찾을 수 없습니다.")


                return False
                
            # 채팅방 창 핸들 재검색
            self.chatroomHwnd = win32gui.FindWindow(None, self.chatroom_name)
            if self.chatroomHwnd == 0:
                Helper.CustomPrint(f"❌ 채팅방 '{self.chatroom_name}' 창을 찾을 수 없습니다.")
                return False
                
            # 리스트 컨트롤 핸들 재검색
            self.hwndListControl = win32gui.FindWindowEx(self.chatroomHwnd, None, "EVA_VH_ListControl_Dblclk", None)
            if self.hwndListControl == 0:
                Helper.CustomPrint(f"❌ 채팅방 리스트 컨트롤을 찾을 수 없습니다.")
                return False
                
            Helper.CustomPrint(f"✅ 창 핸들 새로고침 완료: {self.chatroom_name}")
            return True
            
        except Exception as e:
            Helper.CustomPrint(f"❌ 창 핸들 새로고침 중 오류: {str(e)}")
            return False

    def SendReturn(self, hWnd):
        PostMessage(hWnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
        time.sleep(0.01)
        PostMessage(hWnd, win32con.WM_KEYUP, win32con.VK_RETURN, 0)

    def open_room(self, chatroom_name):
        # # # 채팅방 목록 검색하는 Edit (채팅방이 열려있지 않아도 전송 가능하기 위하여)
        #self.SetForceGroundWindow(self.hWndKaKao)

        # # Edit에 검색 _ 입력되어있는 텍스트가 있어도 덮어쓰기됨
        SendMessage(self.hwndkakao_edit3, win32con.WM_SETTEXT, 0, chatroom_name)
        time.sleep(0.5)  # 안정성 위해 필요
        pyautogui.press("enter")
        time.sleep(0.5)

    def send(self, text, type="text"):
        """
        카카오톡 메시지 전송 (개선된 인터페이스)
        Args:
            text: 전송할 텍스트 (type="text"일 때)
            type: "text" 또는 "image"
        """
        if type == "text":
            self.sendtext(self.chatroom_name, self.chatroomHwnd, text)
        elif type == "image":
            self.send_image(self.chatroomHwnd, self.chatroom_name)

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
        max_retries = 3
        retry_delay = 1.0  # seconds
        
        for attempt in range(max_retries):
            try:
                # 포커스 강제
                try:
                    # 창이 유효한지 확인
                    if not self.validate_window_handle(hwndMain, chatroom_name):
                        # 창 핸들이 유효하지 않으면 새로고침 시도
                        if attempt == 0:  # 첫 번째 시도에서만 새로고침
                            Helper.CustomPrint(f"🔄 [{chatroom_name}] 창 핸들 새로고침 시도...")
                            if self.refresh_window_handles():
                                # 새로고침 후 새로운 핸들 사용
                                hwndMain = self.chatroomHwnd
                                hwndListControl = self.hwndListControl
                            else:
                                time.sleep(retry_delay)
                                continue
                        else:
                            time.sleep(retry_delay)
                            continue
                        
                    # 창을 전면으로 가져오기 전에 현재 포커스된 창 저장
                    current_focus = win32gui.GetForegroundWindow()
                    current_focus_title = win32gui.GetWindowText(current_focus)
                    
                    # 이미 원하는 창이 포커스되어 있다면 대기 시간만 추가
                    if current_focus == hwndMain:
                        time.sleep(0.3)
                    else:
                        # 현재 포커스된 창이 카카오톡 창인 경우, 포커스 해제
                        if "카카오톡" in current_focus_title:
                            # 포커스 해제를 위해 데스크톱 창으로 포커스 이동
                            desktop_hwnd = win32gui.GetDesktopWindow()
                            win32gui.SetForegroundWindow(desktop_hwnd)
                            time.sleep(0.2)
                        
                        # 창을 전면으로 가져오기
                        win32gui.ShowWindow(hwndMain, win32con.SW_RESTORE)
                        time.sleep(0.2)
                        win32gui.SetForegroundWindow(hwndMain)
                        time.sleep(0.3)
                        
                        # 포커스가 변경되었는지 확인
                        if win32gui.GetForegroundWindow() != hwndMain:
                            Helper.CustomPrint(f"❌ [{chatroom_name}] 창 포커스 실패 - 현재 포커스된 창: {current_focus_title}")
                            time.sleep(retry_delay)
                            continue
                        
                except Exception as e:
                    Helper.CustomPrint(f"❌ [{chatroom_name}] SetForegroundWindow 예외 발생: {e}")
                    time.sleep(retry_delay)
                    continue

                # 클립보드 초기화
                try:
                    win32clipboard.OpenClipboard()
                    win32clipboard.EmptyClipboard()
                    win32clipboard.CloseClipboard()
                    time.sleep(0.2)  # 클립보드 초기화 대기
                except Exception as e:
                    Helper.CustomPrint(f"❌ [{chatroom_name}] 클립보드 초기화 실패: {e}")
                    time.sleep(retry_delay)
                    continue

                # Ctrl+A, Ctrl+C 조합키로 전체 복사
                self.PostKeyEx(hwndListControl, ord('A'), [w.VK_CONTROL], False)
                time.sleep(0.5)
                self.PostKeyEx(hwndListControl, ord('C'), [w.VK_CONTROL], False)
                time.sleep(0.5)  # 클립보드 복사 대기

                try:
                    # 클립보드 내용 가져오기 시도
                    win32clipboard.OpenClipboard()
                    if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                        ctext = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                        win32clipboard.CloseClipboard()
                        if ctext:  # 내용이 있는 경우에만 반환
                            return ctext
                        else:
                            Helper.CustomPrint(f"❌ [{chatroom_name}] 클립보드 내용이 비어있습니다.")
                            time.sleep(retry_delay)
                            continue
                    else:
                        Helper.CustomPrint(f"❌ [{chatroom_name}] 클립보드에 텍스트 형식이 없습니다.")
                        win32clipboard.CloseClipboard()
                        time.sleep(retry_delay)
                        continue
                        
                except Exception as e:
                    Helper.CustomPrint(f"❌ [{chatroom_name}] 클립보드 접근 예외 발생: {e}")
                    try:
                        win32clipboard.CloseClipboard()
                    except:
                        pass
                    time.sleep(retry_delay)
                    continue

            except Exception as e:
                Helper.CustomPrint(f"❌ [{chatroom_name}] copy_cheat 예외 발생: {e}")
                import traceback
                Helper.CustomPrint(traceback.format_exc())
                time.sleep(retry_delay)
                continue

        # 모든 재시도 실패 시 빈 문자열 반환
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
        # 빈 텍스트인 경우 빈 DataFrame 반환
        if not text or not text.strip():
            return pd.DataFrame({
                'line_idx': [],
                'name': [],
                'raw_time': [],
                'date': [],
                'timestamp': [],
                'message': []
            })
        
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

    def is_ignore_message(self, message, name):
        # 1. 내 메시지인지 검사
        if name == self.BotName:
            return 1

        # 2. 무시할 메시지 검사 (ignore_message로 시작하는 메시지)
        if re.match(rf"^{re.escape(dataManager.ignore_message)}", message):
            return 1
        return 0

       # # 2. 헤더 라인 검사: [이름] [시간] 형태
       # header_pattern = re.compile(r'^\[(?P<name>[^\]]+)\]\s*\[(?P<time>[^\]]+)\]$')
       # m = header_pattern.match(message.strip())

       # # 3. 정규식 매칭이 되지 않으면 None 반환됨 (m이 None일 때 예외 처리)
       # if m is None:
       #     print(f"{message} No match for header pattern")
       #     return 1

       # # 4. name과 time이 올바르게 매칭되지 않으면 무시 처리
       # if m.group('name') is None:
       #     print("name None")
       #     return 1

       # if m.group('time') is None:
       #     print("time None")
       #     return 1

       # # 모든 조건을 통과하면 0 반환
       # return 0

    ## 5) 추가된 메시지 중 커맨드 포함 확인
    def check_new_commands(self, message_df):
        """
        1) 새로 복사한 전체 로그를 파싱(message_df).
        2) last_index 이후(line_idx > self.last_index)에 추가된 메시지들만 선별(new_msgs).
        3) 메시지 내용에 chat_command_map의 key(명령어)가 포함되어 있으면,
           해당 key에 대응하는 함수포인터 + 전체 메시지(또는 일부)를 묶어
           리스트 형태로 반환한다.
        """

        # DataFrame이 비어있거나 'line_idx' 컬럼이 없는 경우 처리
        if message_df.empty:
            return []
        
        if 'line_idx' not in message_df.columns:
            Helper.CustomPrint(f"❌ [{self.chatroom_name}] DataFrame에 'line_idx' 컬럼이 없습니다. 컬럼: {list(message_df.columns)}")
            return []

        # 새 메시지: line_idx > self.last_index
        new_msgs = message_df[message_df['line_idx'] > self.last_index]

        results = []
        for idx, row in new_msgs.iterrows():
            msg = row['message']
            name = row['name']

            if self.is_ignore_message(msg, name) == 1:
                continue

            for chat_command, desc, chat_func in dataManager.chat_command_Map:
                if chat_command in msg:
                    message = self.split_command(chat_command, msg)
                    resultString, result_type = chat_func(self.chatroom_name, chat_command, message)

                    if result_type is not None:
                        self.send(resultString, result_type)  # 메시지 전송
                        Helper.CustomPrint(f"{self.chatroom_name} - {msg} - [{result_type}]")

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

    def CustomPrint(self, messages, saveLog=True):
        print(f"{self.chatroom_name}-{messages}")  # 항상 콘솔에 출력
        if saveLog:
            Helper.CustomPrint(f"{self.chatroom_name}-{messages}")

if __name__ == "__main__":
   proc = ChatProcess("이더")
   time.sleep(0.5)

   while True:
    proc.run()
    time.sleep(0.5)


