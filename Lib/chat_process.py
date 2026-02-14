import re
import datetime, pyautogui
import time, win32con, win32api, win32gui, ctypes
import pyperclip
from pywinauto import clipboard # 채팅창내용 가져오기 위해
import pandas as pd
from . import Helper
from . import dataManager
import win32clipboard
import queue
import subprocess
import os
import psutil

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
    # 카카오톡 실행 상태 캐시 (클래스 변수 - 모든 인스턴스 공유)
    _kakao_running_cache = False
    _kakao_check_time = 0
    _KAKAO_CHECK_INTERVAL = 10  # 10초마다만 프로세스 체크

    def __init__(self, chatroom_name):
        self.chatroom_name = chatroom_name
        self.last_index = 0
        self.IsLoad = 0
        self.BotName = dataManager.BOT_NAME
        self.message_queue = queue.Queue()  # 메시지 큐
        self.chatroomHwnd = 0  # 채팅방 창 핸들 초기화
        self.hwndListControl = 0  # 리스트 컨트롤 핸들 초기화
        self.hwndkakao_edit3 = 0  # 검색 Edit 컨트롤 핸들 초기화
        self.init()

    def init(self):
        # Open
        self.init_open_romm(self.chatroom_name)


        # 핸들을 찾지 못한 경우 초기화 실패로 처리
        if self.chatroomHwnd == 0:
            self.CustomPrint("❌ Error: Cannot find chatroom - 초기화 실패")
            self.IsLoad = 0  # 명시적으로 초기화 실패 설정
            return
        
        # 리스트 컨트롤 핸들 검색
        self.hwndListControl = win32gui.FindWindowEx(self.chatroomHwnd, None, "EVA_VH_ListControl_Dblclk", None)
        if self.hwndListControl == 0:
            self.CustomPrint("❌ Error: Cannot find list control - 초기화 실패")
            self.IsLoad = 0  # 명시적으로 초기화 실패 설정
            return

        # 채팅방열고
        # self.open_room(self.chatroom_name)
        CopyText = self.copy_cheat(self.chatroom_name, self.chatroomHwnd, self.hwndListControl)

        # 채팅 내용 복사 실패 시 초기화 실패로 처리
        if not CopyText or CopyText.strip() == "":
            self.CustomPrint("❌ Error: Cannot copy chat content - 초기화 실패")
            self.IsLoad = 0  # 명시적으로 초기화 실패 설정
            return

        df = self.parse_chat_log(CopyText)
        # 파싱 결과는 콘솔에만 출력하고 파일에는 저장하지 않음
        self.CustomPrint(f"[최초] 파싱 결과:", saveLog=False)
        self.CustomPrint(str(df), saveLog=False)

        # 마지막으로 읽은 메시지의 line_idx를 구함 (가장 마지막 행)
        if not df.empty:
            self.last_index = df.iloc[-1]['line_idx']
            self.CustomPrint(f"✅ 초기화 완료 - 마지막 메시지 인덱스: {self.last_index}")
        else:
            self.last_index = -1
            self.CustomPrint("✅ 초기화 완료 - 채팅 내용이 비어있음 (last_index: -1)")

        # 모든 초기화가 성공한 경우에만 IsLoad = 1 설정
        self.IsLoad = 1

    def SetForceGroundWindow(self, hwndMain):
        """
        주어진 창 핸들을 전면으로 가져오는 메서드입니다.
        창이 최소화되어 있다면 복원하고, 포커스를 설정합니다.
        SetForegroundWindow 예외를 안전하게 처리합니다.
        """
        if not win32gui.IsWindow(hwndMain):
            self.CustomPrint(f"❌ 유효하지 않은 창 핸들: {hwndMain}")
            return False
        
        try:
            # 현재 포커스된 창 정보 저장
            current_focus = win32gui.GetForegroundWindow()
            current_focus_title = win32gui.GetWindowText(current_focus)
            
            # 이미 원하는 창이 포커스되어 있다면 바로 반환
            if current_focus == hwndMain:
                return True
            
            # 창이 최소화되어 있다면 복원
            if win32gui.IsIconic(hwndMain):
                win32gui.ShowWindow(hwndMain, win32con.SW_RESTORE)
                time.sleep(0.05)

            # 창을 전면으로 가져오기 (여러 방법 시도)
            success = False

            # 방법 1: 일반적인 SetForegroundWindow
            try:
                win32gui.SetForegroundWindow(hwndMain)
                time.sleep(0.05)
                if win32gui.GetForegroundWindow() == hwndMain:
                    success = True
            except Exception as e:
                self.CustomPrint(f"⚠️ SetForegroundWindow 실패: {e}")

            # 방법 2: ShowWindow + SetForegroundWindow 조합
            if not success:
                try:
                    win32gui.ShowWindow(hwndMain, win32con.SW_SHOW)
                    win32gui.ShowWindow(hwndMain, win32con.SW_RESTORE)
                    time.sleep(0.05)
                    win32gui.SetForegroundWindow(hwndMain)
                    time.sleep(0.05)
                    if win32gui.GetForegroundWindow() == hwndMain:
                        success = True
                except Exception as e:
                    self.CustomPrint(f"⚠️ ShowWindow + SetForegroundWindow 실패: {e}")

            # 방법 3: BringWindowToTop 사용
            if not success:
                try:
                    win32gui.BringWindowToTop(hwndMain)
                    time.sleep(0.05)
                    if win32gui.GetForegroundWindow() == hwndMain:
                        success = True
                except Exception as e:
                    self.CustomPrint(f"⚠️ BringWindowToTop 실패: {e}")
            
            if success:
                return True
            else:
                self.CustomPrint(f"⚠️ 창 포커스 실패 - 현재 포커스된 창: {current_focus_title}")
                return False
                
        except Exception as e:
            self.CustomPrint(f"❌ SetForceGroundWindow 예외 발생: {e}")
            return False

    def is_kakao_running(self):
        """카카오톡이 실행 중인지 확인 (캐시 사용으로 성능 최적화)"""
        now = time.time()
        # 캐시가 유효하면 캐시된 결과 반환
        if now - ChatProcess._kakao_check_time < ChatProcess._KAKAO_CHECK_INTERVAL:
            return ChatProcess._kakao_running_cache

        try:
            ChatProcess._kakao_check_time = now
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] and 'kakao' in proc.info['name'].lower():
                    ChatProcess._kakao_running_cache = True
                    return True
            ChatProcess._kakao_running_cache = False
            return False
        except Exception as e:
            self.CustomPrint(f"❌ 프로세스 확인 중 오류: {e}")
            return ChatProcess._kakao_running_cache  # 오류 시 캐시 반환

    def launch_kakao(self):
        """카카오톡을 실행합니다"""
        try:
            # 일반적인 카카오톡 설치 경로들
            possible_paths = [
                r"C:\Program Files (x86)\Kakao\KakaoTalk\KakaoTalk.exe",
                r"C:\Program Files\Kakao\KakaoTalk\KakaoTalk.exe",
                r"C:\Users\{}\AppData\Local\Kakao\KakaoTalk\KakaoTalk.exe".format(os.getenv('USERNAME')),
                r"C:\Users\{}\AppData\Roaming\Kakao\KakaoTalk\KakaoTalk.exe".format(os.getenv('USERNAME')),
            ]
            
            kakao_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    kakao_path = path
                    break
            
            if not kakao_path:
                # 환경변수에서 PATH 검색
                try:
                    result = subprocess.run(['where', 'KakaoTalk.exe'], 
                                          capture_output=True, text=True, shell=True)
                    if result.returncode == 0:
                        kakao_path = result.stdout.strip().split('\n')[0]
                except:
                    pass
            
            if kakao_path:
                self.CustomPrint(f"🚀 카카오톡 실행 중: {kakao_path}")
                subprocess.Popen([kakao_path], shell=True)
                
                # 카카오톡이 완전히 로드될 때까지 대기
                for i in range(30):  # 최대 30초 대기
                    time.sleep(1)
                    if self.is_kakao_running():
                        self.CustomPrint("✅ 카카오톡 실행 완료")
                        time.sleep(3)  # 추가 대기 (로그인 등)
                        return True
                    self.CustomPrint(f"⏳ 카카오톡 로딩 중... ({i+1}/30)")
                
                self.CustomPrint("❌ 카카오톡 실행 시간 초과")
                return False
            else:
                self.CustomPrint("❌ 카카오톡 실행 파일을 찾을 수 없습니다")
                return False
                
        except Exception as e:
            self.CustomPrint(f"❌ 카카오톡 실행 중 오류: {e}")
            return False

    def ensure_kakao_running(self):
        """카카오톡이 실행 중인지 확인하고, 실행되지 않았다면 실행합니다"""
        if not self.is_kakao_running():
            self.CustomPrint("📱 카카오톡이 실행되지 않음 - 자동 실행 시도")
            return self.launch_kakao()
        else:
            self.CustomPrint("✅ 카카오톡이 이미 실행 중")
            return True

    def run(self):
        # 카카오톡이 실행 중인지 확인
        if not self.is_kakao_running():
            self.CustomPrint("📱 카카오톡이 실행되지 않음 - 자동 실행 시도")
            if not self.ensure_kakao_running():
                self.CustomPrint("❌ 카카오톡 실행 실패 - 이번 사이클 건너뛰기")
                return
        
        # Load가 실패하면 다시 초기화 시도
        if self.IsLoad == 0:
            self.CustomPrint("🔄 초기화 실패로 인한 재시도...")
            self.init()

        # 재초기화 후에도 실패하면 종료
        if self.IsLoad == 0:
            self.CustomPrint("❌ 초기화 실패 - 이번 사이클 건너뛰기")
            return

        # 창 핸들이 유효하지 않으면 방 다시 열기 (유효하면 스킵)
        if not self.validate_window_handle(self.chatroomHwnd, self.chatroom_name):
            self.open_room(self.chatroom_name)
            # 방 열기 후 핸들 재검색
            self.chatroomHwnd = win32gui.FindWindow(None, self.chatroom_name)
            if self.chatroomHwnd != 0:
                self.hwndListControl = win32gui.FindWindowEx(self.chatroomHwnd, None, "EVA_VH_ListControl_Dblclk", None)

        # 채팅 내용 복사
        CopyText = self.copy_cheat(self.chatroom_name, self.chatroomHwnd, self.hwndListControl)
        
        # 채팅 내용 복사 실패 시 처리
        if not CopyText or CopyText.strip() == "":
            if Helper.is_debug_mode():
                self.CustomPrint("❌ 채팅 내용 복사 실패", saveLog=False)
            return
        
        df = self.parse_chat_log(CopyText)
        result = self.check_new_commands(df)

        if len(result) > 0:
            for cmd_key, func_ptr in result:
                self.CustomPrint(cmd_key)
        elif Helper.is_debug_mode():
            self.CustomPrint("신규 채팅이 없습니다.", saveLog=False)
        
        # 메시지 큐 처리 (기존 명령어 처리 후)
        self.process_message_queue()

    def add_message_to_queue(self, message, message_type="text"):
        """메시지 큐에 메시지 추가 (스레드 안전)"""
        try:
            self.message_queue.put((message, message_type), block=False)
            self.CustomPrint(f"📨 메시지 큐에 추가됨: {message[:30]}...")
        except queue.Full:
            self.CustomPrint(f"❌ 메시지 큐가 가득참: {message[:30]}...")

    def process_message_queue(self):
        """메시지 큐 처리 (메인 스레드에서만 호출)"""
        processed_count = 0
        max_process = 5  # 한 번에 최대 5개 메시지 처리
        
        while not self.message_queue.empty() and processed_count < max_process:
            try:
                message, message_type = self.message_queue.get(block=False)
                self.CustomPrint(f"📤 큐에서 메시지 전송: {message[:30]}...")
                
                # 실제 메시지 전송
                self.send(message, message_type)
                
                self.message_queue.task_done()
                processed_count += 1
                
                # 메시지 간 간격
                time.sleep(0.15)
                
            except queue.Empty:
                break
            except Exception as e:
                self.CustomPrint(f"❌ 큐 메시지 처리 오류: {str(e)}")
                break
        
        if processed_count > 0:
            self.CustomPrint(f"✅ 메시지 큐에서 {processed_count}개 메시지 처리 완료")

    def init_open_romm(self, chatroom_name):
        """채팅방 초기화 및 창 핸들 검증"""
        try:
            # 카카오톡이 실행 중인지 확인하고, 실행되지 않았다면 실행
            if not self.ensure_kakao_running():
                Helper.CustomPrint(f"❌ 카카오톡 실행에 실패했습니다.")
                return
            
            # 카카오톡 메인 창 찾기
            hWndKaKao = win32gui.FindWindow(None, "카카오톡")
            if hWndKaKao == 0:
                Helper.CustomPrint(f"❌ 카카오톡 창을 찾을 수 없습니다. 카카오톡이 실행 중인지 확인해주세요.")
                return
            
            # 카카오톡 창이 최소화되어 있다면 복원
            if win32gui.IsIconic(hWndKaKao):
                win32gui.ShowWindow(hWndKaKao, win32con.SW_RESTORE)
                time.sleep(0.2)
            
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
                time.sleep(0.3)
                self.SendReturn(self.hwndkakao_edit3)
                time.sleep(0.5)
                
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
        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.3)

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
        try:
            focus_success = self.SetForceGroundWindow(hwndMain)
            if not focus_success:
                Helper.CustomPrint(f"⚠️ [{cheat_room_name}] 1단계: 창 포커스 실패 - 계속 진행")
            time.sleep(0.05)

            # Tab 키로 입력창 포커스
            self.SendTab(1)

            # 클립보드 복사
            pyperclip.copy(text)
            time.sleep(0.05)

            # Ctrl+V (붙여넣기)
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(0x56, 0, 0, 0)  # V key
            win32api.keybd_event(0x56, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.05)

            # Enter 전송
            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)

            Helper.CustomPrint(f"✅ [{cheat_room_name}] 메시지 전송 완료: '{text[:30]}...'")
            
        except Exception as e:
            Helper.CustomPrint(f"❌ [{cheat_room_name}] 메시지 전송 중 오류: {str(e)}")
            import traceback
            Helper.CustomPrint(f"❌ [{cheat_room_name}] 스택 트레이스: {traceback.format_exc()}")

    def send_image(self, hwndMain, cheat_room_name):
        """
        현재 클립보드에 있는 이미지를 카카오톡 채팅방에 붙여넣기(CTRL+V) 후 엔터키를 통해 전송합니다.
        """
        # 카카오톡 창 포커스로 가져오기
        self.SetForceGroundWindow(hwndMain)
        time.sleep(0.05)

        # 입력창으로 포커스를 이동
        self.SendTab(1)
        time.sleep(0.05)

        # Ctrl+V (붙여넣기) 시뮬레이션
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(0x56, 0, 0, 0)  # V 키 (0x56)
        time.sleep(0.02)
        win32api.keybd_event(0x56, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.05)

        # 엔터키 시뮬레이션 (메시지 전송)
        win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
        win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)

    ## 탭
    def SendTab(self, n=1):
        for _ in range(n):
            ctypes.windll.user32.keybd_event(win32con.VK_TAB, 0, 0, 0)  # Key down
            time.sleep(0.01)
            ctypes.windll.user32.keybd_event(win32con.VK_TAB, 0, win32con.KEYEVENTF_KEYUP, 0)  # Key up
            time.sleep(0.02)

    def copy_cheat(self, chatroom_name, hwndMain, hwndListControl):
        """
        chatroom_name 방의 hwndMain 창을 포커스한 뒤,
        리스트 컨트롤(hwndListControl)의 모든 텍스트를 복사해서 반환합니다.
        예외 발생 시에는 빈 문자열을 반환하고, 에러를 로깅합니다.
        """
        max_retries = 3
        retry_delay = 0.3  # seconds
        
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
                    
                    # SetForceGroundWindow 메서드 사용
                    focus_success = self.SetForceGroundWindow(hwndMain)
                    if not focus_success and Helper.is_debug_mode():
                        Helper.CustomPrint(f"⚠️ [{chatroom_name}] 창 포커스 실패 - 계속 진행")
                        
                except Exception as e:
                    Helper.CustomPrint(f"❌ [{chatroom_name}] 창 포커스 예외 발생: {e}")
                    time.sleep(retry_delay)
                    continue

                # 클립보드 초기화
                try:
                    win32clipboard.OpenClipboard()
                    win32clipboard.EmptyClipboard()
                    win32clipboard.CloseClipboard()
                except Exception as e:
                    Helper.CustomPrint(f"❌ [{chatroom_name}] 클립보드 초기화 실패: {e}")
                    time.sleep(retry_delay)
                    continue

                # Ctrl+A, Ctrl+C 조합키로 전체 복사
                self.PostKeyEx(hwndListControl, ord('A'), [w.VK_CONTROL], False)
                time.sleep(0.1)
                self.PostKeyEx(hwndListControl, ord('C'), [w.VK_CONTROL], False)
                time.sleep(0.15)  # 클립보드 복사 대기

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
            self.CustomPrint("📝 파싱된 메시지가 없습니다.")
            return []
        
        if 'line_idx' not in message_df.columns:
            self.CustomPrint(f"❌ DataFrame에 'line_idx' 컬럼이 없습니다. 컬럼: {list(message_df.columns)}")
            return []

        # 새 메시지: line_idx > self.last_index
        new_msgs = message_df[message_df['line_idx'] > self.last_index]
        
        # 새 메시지가 있는지 로깅
        if not new_msgs.empty:
            self.CustomPrint(f"📨 새 메시지 {len(new_msgs)}개 발견 (last_index: {self.last_index})")
        elif Helper.is_debug_mode():
            self.CustomPrint(f"📝 새 메시지 없음 (last_index: {self.last_index})", saveLog=False)

        results = []
        for idx, row in new_msgs.iterrows():
            msg = row['message']
            name = row['name']
            line_idx = row['line_idx']

            if self.is_ignore_message(msg, name) == 1:
                continue

            for chat_command, desc, chat_func in dataManager.chat_command_Map:
                if chat_command in msg:
                    message = self.split_command(chat_command, msg)
                    self.CustomPrint(f"🎯 명령어 감지: {chat_command} (line_idx: {line_idx})")
                    
                    try:
                        resultString, result_type = chat_func(self.chatroom_name, chat_command, message)

                        if result_type is not None:
                            self.send(resultString, result_type)  # 메시지 전송
                            self.CustomPrint(f"✅ 명령어 처리 완료: {self.chatroom_name} - {msg[:30]}... - [{result_type}]")
                    except Exception as e:
                        self.CustomPrint(f"❌ 명령어 처리 중 오류: {str(e)}")

        # 마지막 메시지 인덱스 갱신 (새 메시지가 있을 때만)
        if not message_df.empty:
            new_last_index = message_df.iloc[-1]['line_idx']
            if new_last_index != self.last_index:
                self.CustomPrint(f"📊 last_index 업데이트: {self.last_index} → {new_last_index}")
                self.last_index = new_last_index

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


