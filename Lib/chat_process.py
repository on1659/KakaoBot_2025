import re
import difflib
import datetime, pyautogui
import time, win32con, win32api, win32gui, ctypes
import pyperclip
from pywinauto import clipboard # 채팅창내용 가져오기 위해
import pandas as pd
from . import Helper
from . import dataManager
from . import access_control
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
GetClipboardSequenceNumber = _user32.GetClipboardSequenceNumber

MapVirtualKeyA = _user32.MapVirtualKeyA
MapVirtualKeyW = _user32.MapVirtualKeyW

MakeLong = win32api.MAKELONG
w = win32con


def describe_payload(payload, message_type="text"):
    """로그용 한 줄 요약 — 이미지 바이트를 그대로 찍지 않는다."""
    if message_type == "image":
        return f"<이미지 {len(payload) if payload else 0} bytes>"
    if message_type == "file":
        return f"<파일 {os.path.basename(str(payload))}>"
    return f"{str(payload)[:30]}..."


SEEN_TAIL_SIZE = 30          # 직전에 본 대화의 끝부분을 몇 개까지 기억할지
ALIGN_WINDOW_EXTRA = 200     # 이번에 읽은 대화에서 끝의 (기억 + 이만큼)개만 맞춰 본다
MAX_LOCAL_EDIT = 3           # 맞는 구간 사이에 이 정도까지 끼어들거나 빠진 것은 같은 대화의 변형으로 본다
RESYNC_AFTER_MISSES = 3      # 기억한 대화를 연속 몇 번 못 찾으면 기준을 새로 잡을지
MAX_COMMAND_AGE_MINUTES = 10  # 보낸 지 이보다 오래된 명령은 실행하지 않는다

_TIME_PATTERN = re.compile(r"^\s*(오전|오후|AM|PM)?\s*(\d{1,2}):(\d{2})\s*(AM|PM)?\s*$", re.IGNORECASE)


def find_new_messages(seen, signatures):
    """
    직전에 본 대화의 끝부분(seen)과 이번에 읽은 메시지 목록(signatures)을 맞춰 보고
    (새 메시지의 인덱스 목록, 기억을 이번 내용으로 갱신해도 되는지)를 돌려준다.
    같은 대화라고 볼 근거가 부족하면 None.

    예전에는 '복사한 글에서 몇 번째 줄인가'로 새 메시지를 가렸다. 그런데 복사한 글의 길이는
    새 메시지가 없어도 바뀐다 — 카카오톡이 이전 대화를 더 불러오거나, 창이 다시 열려 최근 일부만
    보이거나, 다른 방 내용이 클립보드에서 읽히는 경우다. 그때마다 줄 번호가 어긋나 예전 메시지
    수백 개가 새 메시지로 처리됐다 (2026-11-10 사고). 그래서 위치가 아니라 내용으로 맞춘다.

    맞추는 방법 (두 목록의 공통 부분을 찾는 정렬):
    - 가장 길게 맞는 구간을 중심으로, 그 앞쪽으로 작은 차이(MAX_LOCAL_EDIT 이하)만 건너가며
      '같은 대화 구간'을 정한다. 그 구간보다 앞은 더 예전 대화이므로 새 메시지가 아니다.
    - 구간 안과 뒤에서 기억에 없던 메시지가 새 메시지다. 단체방에서는 다른 사람의 메시지가
      봇의 답장보다 앞에 끼어들 수 있어서, '맨 끝에 붙은 것'만 보면 놓친다.
    - 같은 사람·같은 시각인데 내용만 다른 것은 예전 메시지가 바뀐 것(삭제 표시, 뒤에 붙은
      시스템 안내)으로 보고 다시 실행하지 않는다.
    - 기억의 끝부분이 이번에 안 보이면(덜 불러와진 화면) 새 메시지 없음으로 치고 기억을 유지한다.
    - 맞는 메시지가 절반(최소 3개)에 못 미치면 같은 대화가 아니라고 본다.
    """
    if not seen:
        return None
    offset = max(0, len(signatures) - (len(seen) + ALIGN_WINDOW_EXTRA))
    window = signatures[offset:]
    if not window:
        return None
    opcodes = difflib.SequenceMatcher(None, seen, window, autojunk=False).get_opcodes()
    equal_blocks = [(i2 - i1, n) for n, (tag, i1, i2, j1, j2) in enumerate(opcodes) if tag == "equal"]
    if not equal_blocks:
        return None

    # 가장 길게 맞는 구간(같으면 더 뒤쪽)에서 앞으로, 작은 차이만 건너가며 구간의 시작을 찾는다
    main = max(equal_blocks)[1]
    start = main
    while start > 0:
        tag, i1, i2, j1, j2 = opcodes[start - 1]
        if tag != "equal" and max(i2 - i1, j2 - j1) > MAX_LOCAL_EDIT:
            break
        start -= 1

    region = opcodes[start:]
    matched = sum(i2 - i1 for tag, i1, i2, j1, j2 in region if tag == "equal")
    smaller = min(len(seen), len(window))
    needed = smaller if smaller < 3 else max(3, -(-smaller // 2))
    if matched < needed:
        return None

    new_indices = []
    anchored = False  # 구간에서 처음 맞는 메시지를 지났는가
    for tag, i1, i2, j1, j2 in region:
        if tag == "equal":
            anchored = True
        elif not anchored:
            continue
        elif tag == "insert":
            new_indices.extend(range(j1, j2))
        elif tag == "replace":
            for k, j in enumerate(range(j1, j2)):
                if i1 + k < i2 and seen[i1 + k][:2] == window[j][:2]:
                    continue  # 같은 사람·같은 시각 — 내용만 바뀐 예전 메시지
                new_indices.append(j)
    can_update = region[-1][0] != "delete"
    return [offset + j for j in new_indices], can_update


def message_age_minutes(date_text, raw_time, now=None):
    """
    메시지를 보낸 지 몇 분 됐는지 계산한다. 시각을 해석할 수 없으면 None (판단 불가).
    date_text는 'YYYY-MM-DD'(날짜 줄에서 얻음)이거나 없을 수 있다. 날짜를 모르면
    하루 안의 시각 차이로 계산한다 (자정을 넘긴 직후의 메시지를 미래로 보지 않게).
    """
    match = _TIME_PATTERN.match(str(raw_time or ""))
    if not match:
        return None
    marker = (match.group(1) or match.group(4) or "").upper()
    hour, minute = int(match.group(2)), int(match.group(3))
    if marker in ("오후", "PM") and hour < 12:
        hour += 12
    elif marker in ("오전", "AM") and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    now = now or datetime.datetime.now()

    try:
        day = datetime.datetime.strptime(str(date_text), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        day = None
    if day is not None:
        age = (now - datetime.datetime.combine(day, datetime.time(hour, minute))).total_seconds() / 60
        if age >= -2:  # 표시 시각은 분 단위라 조금 앞설 수 있다
            return max(0.0, age)
        # 날짜 줄과 PC 시계가 어긋난 경우 — 아래의 시각 차이 계산으로 넘긴다
    return float(((now.hour * 60 + now.minute) - (hour * 60 + minute)) % 1440)


def match_command(command_map, msg):
    """
    메시지에 매치되는 명령을 하나만 반환한다 (없으면 None) — 이중 발화 버그의 수정.
    우선순위: 메시지에서 먼저 등장하는 키가 이기고, 같은 위치면 긴 키가 이긴다.
    - '#modelcheck' → #model과 #modelcheck 둘 다 위치 0 → 긴 #modelcheck 선택
    - '#gpt 이거 봐 https://instagram.com/...' → 앞선 #gpt 선택
      (단순 긴 키 우선이면 뒤에 있는 URL 키가 명시적 명령을 가로챈다)
    키가 find_in(msg) -> (위치, 길이)를 제공하면 부분문자열 대신 그 결과를 쓴다
    (예: random_pick.TRIGGER — 앞뒤 글자 조건이 있는 'vs').
    """
    best = None
    best_rank = None
    for entry in command_map:
        key = entry[0]
        finder = getattr(key, "find_in", None)
        idx, length = finder(msg) if finder else (msg.find(key), len(key))
        if idx < 0:
            continue
        rank = (idx, -length)
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best = entry
    return best


class ChatProcess:
    # 카카오톡 실행 상태 캐시 (클래스 변수 - 모든 인스턴스 공유)
    _kakao_running_cache = False
    _kakao_check_time = 0
    _KAKAO_CHECK_INTERVAL = 10  # 10초마다만 프로세스 체크
    MAX_SEARCH_RESULTS_TO_TRY = 5  # 방 이름이 참여자 이름과 겹칠 때 시도할 검색 결과 수
    INIT_RETRY_INTERVAL = 30  # 초기화(방 열기) 실패 후 재시도 간격(초)
    COPY_TIMEOUT = 1.0  # Ctrl+C 후 클립보드가 바뀌길 기다리는 최대 시간(초)
    FILE_DIALOG_TIMEOUT = 5.0  # 파일 전송 중 창이 뜨거나 닫히길 기다리는 최대 시간(초)

    def __init__(self, chatroom_name, stop_event=None):
        self.chatroom_name = chatroom_name
        self.stop_event = stop_event
        self._seen_tail = None  # 직전에 본 대화의 끝부분 (find_new_messages 참조). None이면 아직 기준 없음
        self._tail_misses = 0   # 기억한 대화를 이번 내용에서 연속으로 못 찾은 횟수
        self.IsLoad = 0
        self.BotName = dataManager.BOT_NAME
        self.message_queue = queue.Queue()  # 메시지 큐
        self.chatroomHwnd = 0  # 채팅방 창 핸들 초기화
        self.hwndListControl = 0  # 리스트 컨트롤 핸들 초기화
        self.hwndkakao_edit3 = 0  # 검색 Edit 컨트롤 핸들 초기화
        self.hwndkakao_search_list = 0  # 검색 결과 리스트 핸들
        self._next_init_retry = 0.0
        self._last_copy_text = None  # 직전 사이클에 복사한 채팅 내용 (변화 감지용)
        self.last_activity = 0.0  # 새 메시지를 마지막으로 본 시각 (time.monotonic) — 엔진의 대기 모드 판단용
        self._first_run = True  # 첫 실행 시 기존 메시지 무시용
        self.init()

    def _stop_requested(self):
        return bool(self.stop_event and self.stop_event.is_set())

    def _wait(self, seconds):
        """종료 이벤트가 있으면 sleep 대신 즉시 깨울 수 있는 대기를 사용한다."""
        if self.stop_event:
            return self.stop_event.wait(seconds)
        time.sleep(seconds)
        return False

    def init(self):
        if self._stop_requested():
            return
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

        # 지금 보이는 대화를 '이미 본 것'으로 기억한다 — 이후에 들어온 메시지만 처리한다
        self._remember_seen(df)
        self.CustomPrint(f"✅ 초기화 완료 - 기존 메시지 {len(df)}개는 처리하지 않습니다")

        # 모든 초기화가 성공한 경우에만 IsLoad = 1 설정
        self.IsLoad = 1

    def SetForceGroundWindow(self, hwndMain):
        """
        주어진 창 핸들을 전면으로 가져오는 메서드입니다.
        Windows의 포커스 잠금 타임아웃을 해제한 뒤 포커스를 전환합니다.
        """
        if not win32gui.IsWindow(hwndMain):
            self.CustomPrint(f"❌ 유효하지 않은 창 핸들: {hwndMain}")
            return False

        try:
            current_focus = win32gui.GetForegroundWindow()

            if current_focus == hwndMain:
                return True

            if win32gui.IsIconic(hwndMain):
                win32gui.ShowWindow(hwndMain, win32con.SW_RESTORE)
                time.sleep(0.15)

            # 포커스 잠금 타임아웃을 0으로 설정 (Windows 포커스 보호 해제)
            SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
            SPIF_SENDCHANGE = 0x0002
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_SETFOREGROUNDLOCKTIMEOUT, 0, 0, SPIF_SENDCHANGE
            )

            # 현재 포커스된 창의 스레드에 연결
            foreground_tid = GetWindowThreadProcessId(current_focus, None)
            current_tid = GetCurrentThreadId()
            attached = False
            if foreground_tid != current_tid:
                AttachThreadInput(current_tid, foreground_tid, True)
                attached = True

            try:
                # Alt키로 포커스 잠금 해제 + 포커스 전환
                win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.02)

                win32gui.BringWindowToTop(hwndMain)
                win32gui.ShowWindow(hwndMain, win32con.SW_SHOW)
                win32gui.SetForegroundWindow(hwndMain)
            except Exception:
                pass
            finally:
                if attached:
                    AttachThreadInput(current_tid, foreground_tid, False)

            time.sleep(0.15)
            if win32gui.GetForegroundWindow() == hwndMain:
                return True

            self.CustomPrint(f"⚠️ 창 포커스 실패 - 현재 포커스된 창: {win32gui.GetWindowText(win32gui.GetForegroundWindow())}")
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
                    if self._wait(1):
                        self.CustomPrint("⏹️ 종료 요청으로 카카오톡 실행 대기를 중단합니다.")
                        return False
                    if self.is_kakao_running():
                        self.CustomPrint("✅ 카카오톡 실행 완료")
                        if self._wait(3):  # 추가 대기 (로그인 등)
                            return False
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
        if self._stop_requested():
            return
        # 카카오톡이 실행 중인지 확인
        if not self.is_kakao_running():
            self.CustomPrint("📱 카카오톡이 실행되지 않음 - 자동 실행 시도")
            if not self.ensure_kakao_running():
                self.CustomPrint("❌ 카카오톡 실행 실패 - 이번 사이클 건너뛰기")
                return
        
        # Load가 실패하면 다시 초기화 시도 (방 열기 시도가 몇 초 걸리므로 간격을 둬서
        # 이름이 틀린 방 하나 때문에 다른 방 응답이 매 사이클 늦어지지 않게 한다)
        if self.IsLoad == 0:
            if time.time() < self._next_init_retry:
                return
            self.CustomPrint("🔄 초기화 실패로 인한 재시도...")
            self.init()

        # 재초기화 후에도 실패하면 종료
        if self.IsLoad == 0:
            self._next_init_retry = time.time() + self.INIT_RETRY_INTERVAL
            self.CustomPrint(f"❌ 초기화 실패 - {self.INIT_RETRY_INTERVAL}초 뒤 다시 시도")
            return

        # 창 핸들이 유효하지 않으면 방 다시 열기 (유효하면 스킵)
        if not self.validate_window_handle(self.chatroomHwnd, self.chatroom_name):
            self.open_room(self.chatroom_name)
            # 방 열기 후 핸들 재검색
            self.chatroomHwnd = win32gui.FindWindow(None, self.chatroom_name)
            if self.chatroomHwnd != 0:
                self.hwndListControl = win32gui.FindWindowEx(self.chatroomHwnd, None, "EVA_VH_ListControl_Dblclk", None)
        # (읽기는 포커스 없이 하므로 매 사이클 창을 앞으로 가져오지 않는다 — 전송할 때만 포커스)

        # 채팅 내용 복사
        CopyText = self.copy_cheat(self.chatroom_name, self.chatroomHwnd, self.hwndListControl)

        # 채팅 내용 복사 실패 시 처리
        if not CopyText or CopyText.strip() == "":
            if Helper.is_debug_mode():
                self.CustomPrint("❌ 채팅 내용 복사 실패", saveLog=False)
            return

        # 지난 사이클과 내용이 같으면 새 메시지가 없다 — 파싱(pandas)을 건너뛴다
        if CopyText == self._last_copy_text:
            self.process_message_queue()
            return
        if self._last_copy_text is not None:
            self.last_activity = time.monotonic()
        self._last_copy_text = CopyText

        df = self.parse_chat_log(CopyText)

        # 첫 실행 시 기존 메시지를 모두 "읽음" 처리하고 명령어 처리 스킵
        if self._first_run:
            self._remember_seen(df)
            self.CustomPrint(f"✅ 첫 실행 - 기존 메시지 {len(df)}개 스킵")
            self._first_run = False
            return

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
            self.CustomPrint(f"📨 메시지 큐에 추가됨: {describe_payload(message, message_type)}")
        except queue.Full:
            self.CustomPrint(f"❌ 메시지 큐가 가득참: {describe_payload(message, message_type)}")

    def process_message_queue(self):
        """메시지 큐 처리 (메인 스레드에서만 호출)"""
        processed_count = 0
        max_process = 5  # 한 번에 최대 5개 메시지 처리
        
        while not self.message_queue.empty() and processed_count < max_process:
            try:
                message, message_type = self.message_queue.get(block=False)
                self.CustomPrint(f"📤 큐에서 메시지 전송: {describe_payload(message, message_type)}")
                
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
            if self._stop_requested():
                return
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
            # 채팅 탭(ChatRoomListView)의 두 번째 리스트 = 검색 결과 목록 (첫 번째는 전체 채팅 목록)
            chat_list = win32gui.FindWindowEx(hwndkakao_edit2_2, None, "EVA_VH_ListControl_Dblclk", None)
            self.hwndkakao_search_list = win32gui.FindWindowEx(hwndkakao_edit2_2, chat_list, "EVA_VH_ListControl_Dblclk", None)

            if self.hwndkakao_edit3 == 0:
                Helper.CustomPrint(f"❌ 카카오톡 검색 Edit을 찾을 수 없습니다.")
                return

            # 채팅방 창 핸들 찾기
            self.chatroomHwnd = win32gui.FindWindow(None, chatroom_name)

            # 채팅방이 없으면 검색으로 열기
            if self.chatroomHwnd == 0:
                Helper.CustomPrint(f"📝 채팅방 '{chatroom_name}'을 검색하여 열기 시도...")
                self.chatroomHwnd = self._open_room_via_search(chatroom_name)

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
        self.SendKey(hWnd, win32con.VK_RETURN)

    @staticmethod
    def SendKey(hWnd, vk):
        PostMessage(hWnd, win32con.WM_KEYDOWN, vk, 0)
        time.sleep(0.01)
        PostMessage(hWnd, win32con.WM_KEYUP, vk, 0)

    def open_room(self, chatroom_name):
        self._open_room_via_search(chatroom_name)

    @staticmethod
    def _visible_kakao_room_windows():
        found = set()

        def collect(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == "EVA_Window_Dblclk":
                found.add(hwnd)

        win32gui.EnumWindows(collect, None)
        return found

    def _open_room_via_search(self, chatroom_name):
        """
        채팅 탭 검색으로 방을 열고 창 핸들을 반환한다 (실패 시 0).
        카카오톡 검색은 방 이름뿐 아니라 '참여자 이름'도 찾기 때문에, 방 이름이 사람 이름과
        같으면(예: 본인 닉네임) 다른 단체방이 첫 결과가 된다. 결과 내용은 읽을 수 없으므로
        n번째 결과를 차례로 열어 창 제목이 정확히 일치하는지 확인하고, 이번에 잘못 연 창은 닫는다.
        메인 창이 트레이로 숨겨져 있어도 동작한다 (메시지를 핸들에 직접 보냄).
        """
        edit = self.hwndkakao_edit3
        results = self.hwndkakao_search_list or edit
        if not edit:
            return 0

        already_open = self._visible_kakao_room_windows()
        hwnd = 0
        try:
            for position in range(self.MAX_SEARCH_RESULTS_TO_TRY):
                if self._stop_requested():
                    break
                # 검색어를 다시 넣어 선택 위치를 첫 결과로 초기화
                SendMessage(edit, win32con.WM_SETTEXT, 0, "")
                time.sleep(0.1)
                SendMessage(edit, win32con.WM_SETTEXT, 0, chatroom_name)
                time.sleep(0.4)
                for _ in range(position):
                    self.SendKey(results, win32con.VK_DOWN)
                    time.sleep(0.05)
                self.SendKey(results, win32con.VK_RETURN)

                for _ in range(10):
                    time.sleep(0.1)
                    hwnd = win32gui.FindWindow(None, chatroom_name)
                    if hwnd:
                        # 막 생성된 창은 잠깐 보이지 않는 상태라 바로 복사하면 실패한다
                        for _ in range(10):
                            if win32gui.IsWindowVisible(hwnd):
                                break
                            time.sleep(0.1)
                        time.sleep(0.2)
                        return hwnd

                # 이미 열려 있던 방이 결과로 잡히면 새 창이 없다 — 그래도 다음 결과를 계속 시도
                wrong = self._visible_kakao_room_windows() - already_open
                for other in wrong:
                    Helper.CustomPrint(
                        f"↪ [{chatroom_name}] 검색 결과 {position + 1}번째는 "
                        f"'{win32gui.GetWindowText(other)}' - 닫고 다음 결과 시도"
                    )
                    PostMessage(other, win32con.WM_CLOSE, 0, 0)
                time.sleep(0.3)
            return 0
        finally:
            SendMessage(edit, win32con.WM_SETTEXT, 0, "")  # 채팅 목록 필터 해제

    def send(self, payload, type="text"):
        """
        카카오톡 메시지 전송
        Args:
            payload: type="text"면 문자열, type="image"면 DIB 바이트
                     (BMP 인코딩에서 14바이트 파일 헤더를 제거한 것 — insta.GetData 참조),
                     type="file"이면 보낼 파일의 경로 (예: #tts가 만든 mp3)
            type: "text" | "image" | "file"
        """
        if type == "text":
            self.sendtext(self.chatroom_name, self.chatroomHwnd, payload)
        elif type == "image":
            self.send_image(payload)
        elif type == "file":
            self.send_file(payload)
        elif type != "none":
            # "none"은 전송 없음이 계약이지만, 그 외 미지의 타입은 오타/계약 위반이다
            Helper.CustomPrint(f"⚠️ [{self.chatroom_name}] 알 수 없는 전송 타입 무시: {type!r}")

    def sendtext(self, cheat_room_name, hwndMain, text):
        try:
            focus_success = self.SetForceGroundWindow(hwndMain)
            if not focus_success:
                Helper.CustomPrint(f"⚠️ [{cheat_room_name}] 1단계: 창 포커스 실패 - 계속 진행")
            time.sleep(0.1)

            # 입력창 포커스
            self._focus_input_box()
            time.sleep(0.1)

            # 클립보드 복사
            pyperclip.copy(text)
            time.sleep(0.1)

            # Ctrl+V (붙여넣기)
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(0x56, 0, 0, 0)  # V key
            win32api.keybd_event(0x56, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.1)

            # Enter 전송
            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)

            Helper.CustomPrint(f"✅ [{cheat_room_name}] 메시지 전송 완료: '{text[:30]}...'")
            
        except Exception as e:
            Helper.CustomPrint(f"❌ [{cheat_room_name}] 메시지 전송 중 오류: {str(e)}")
            import traceback
            Helper.CustomPrint(f"❌ [{cheat_room_name}] 스택 트레이스: {traceback.format_exc()}")

    def _copy_dib_to_clipboard(self, dib_bytes):
        """
        DIB 바이트를 클립보드에 올리고 같은 세션 안에서 CF_DIB 등록까지 확인한다.
        (세션을 닫았다 다시 열어 확인하면 클립보드 리스너가 끼어드는 레이스가 생긴다)
        try/finally로 클립보드 해제를 보장한다.
        """
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_DIB, dib_bytes)
                return bool(win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB))
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:
            Helper.CustomPrint(f"❌ [{self.chatroom_name}] 클립보드 이미지 복사 실패: {e}")
            return False

    def send_image(self, dib_bytes):
        """
        DIB 바이트를 클립보드에 올린 뒤 붙여넣기(CTRL+V)+엔터로 전송한다.
        run()이 매 사이클 방 전체 채팅 로그를 클립보드에 복사해 두므로, 여기서 직접
        올리고 CF_DIB를 확인하지 않으면 실패 시 채팅 로그가 그대로 방에 게시된다.
        """
        if not dib_bytes or not self._copy_dib_to_clipboard(dib_bytes):
            self.sendtext(self.chatroom_name, self.chatroomHwnd, "이미지 전송에 실패했습니다.")
            return

        # 카카오톡 창 포커스로 가져오기
        self.SetForceGroundWindow(self.chatroomHwnd)
        time.sleep(0.1)

        # 입력창으로 포커스를 이동
        self._focus_input_box()
        time.sleep(0.1)

        # Ctrl+V (붙여넣기) 시뮬레이션
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(0x56, 0, 0, 0)  # V 키 (0x56)
        time.sleep(0.02)
        win32api.keybd_event(0x56, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(1.0)  # 이미지 미리보기 팝업 렌더링 대기

        # 엔터키 시뮬레이션 (메시지 전송)
        win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
        win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
        Helper.CustomPrint(f"✅ [{self.chatroom_name}] 이미지 전송 완료 ({len(dib_bytes)} bytes)")

    @staticmethod
    def _wait_for(predicate, timeout, interval=0.1):
        """predicate()가 참 값을 돌려줄 때까지 기다린다. 시간 안에 안 되면 마지막 값을 반환."""
        deadline = time.monotonic() + timeout
        value = predicate()
        while not value and time.monotonic() < deadline:
            time.sleep(interval)
            value = predicate()
        return value

    def _find_owned_window(self, class_name, titled):
        """이 채팅방이 소유한 보이는 창(파일 열기 창, 전송 확인 창)을 찾는다. 없으면 0."""
        found = []

        def collect(hwnd, _):
            if (win32gui.IsWindowVisible(hwnd)
                    and win32gui.GetClassName(hwnd) == class_name
                    and win32gui.GetWindow(hwnd, win32con.GW_OWNER) == self.chatroomHwnd
                    and bool(win32gui.GetWindowText(hwnd)) == titled):
                found.append(hwnd)

        win32gui.EnumWindows(collect, None)
        return found[0] if found else 0

    @staticmethod
    def _window_gone(hwnd):
        return not (win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd))

    def _click_input_box(self):
        """입력창에 클릭 메시지를 보내 포커스를 준다 (실제 마우스 커서는 움직이지 않는다)."""
        edit = win32gui.FindWindowEx(self.chatroomHwnd, None, "RICHEDIT50W", None)
        if not edit:
            return False
        left, top, right, bottom = win32gui.GetClientRect(edit)
        position = MakeLong((right - left) // 2, (bottom - top) // 2)
        PostMessage(edit, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, position)
        PostMessage(edit, win32con.WM_LBUTTONUP, 0, position)
        return True

    def _focus_input_box(self):
        """
        붙여넣기 전에 입력창에 포커스를 준다.
        예전에는 Tab 한 번으로 옮겼는데, 포커스가 이미 입력창에 있으면(같은 방에 연달아 보낼 때 등)
        Tab이 옆의 '+' 버튼으로 넘어가 붙여넣기가 허공에 떨어지고 메시지가 사라졌다 (2026-11 실측).
        입력창을 못 찾을 때만 예전 방식으로 한다.
        """
        if not self._click_input_box():
            self.SendTab(1)

    def _send_file_via_dialog(self, file_path):
        """
        카카오톡의 파일 전송 단축키(Ctrl+T)로 파일을 보낸다. 성공하면 True.
        순서: Ctrl+T → '열기' 창의 파일 이름 칸에 경로 입력 → 열기 → '파일 전송' 확인 창에서 엔터.
        (파일을 클립보드에 복사해 붙여넣는 방식은 카카오톡이 무시한다 — 2026-11 실측)
        클립보드를 쓰지 않으므로 실패해도 방에 엉뚱한 내용이 붙여넣어질 일이 없다.
        """
        self.SetForceGroundWindow(self.chatroomHwnd)
        time.sleep(0.1)
        self._click_input_box()
        time.sleep(0.2)

        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(0x54, 0, 0, 0)  # T
        time.sleep(0.02)
        win32api.keybd_event(0x54, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)

        open_dialog = self._wait_for(lambda: self._find_owned_window("#32770", True), self.FILE_DIALOG_TIMEOUT)
        if not open_dialog:
            Helper.CustomPrint(f"❌ [{self.chatroom_name}] 파일 열기 창이 뜨지 않았습니다.")
            return False
        time.sleep(0.3)  # 창 안 컨트롤이 만들어질 시간

        combo_ex = win32gui.FindWindowEx(open_dialog, None, "ComboBoxEx32", None)
        combo = win32gui.FindWindowEx(combo_ex, None, "ComboBox", None) if combo_ex else 0
        name_edit = win32gui.FindWindowEx(combo, None, "Edit", None) if combo else 0
        open_button = win32gui.GetDlgItem(open_dialog, win32con.IDOK) if name_edit else 0
        if not name_edit or not open_button:
            Helper.CustomPrint(f"❌ [{self.chatroom_name}] 파일 열기 창의 입력 칸을 찾지 못했습니다.")
            PostMessage(open_dialog, win32con.WM_CLOSE, 0, 0)
            return False

        SendMessage(name_edit, win32con.WM_SETTEXT, 0, file_path)
        time.sleep(0.2)
        PostMessage(open_button, win32con.BM_CLICK, 0, 0)
        if not self._wait_for(lambda: self._window_gone(open_dialog), self.FILE_DIALOG_TIMEOUT):
            Helper.CustomPrint(f"❌ [{self.chatroom_name}] 파일 열기 창이 닫히지 않아 취소합니다.")
            PostMessage(open_dialog, win32con.WM_CLOSE, 0, 0)
            return False

        # '파일 전송' 확인 창: 제목 없는 EVA 창이 채팅방 위에 뜬다
        confirm = self._wait_for(
            lambda: self._find_owned_window("EVA_Window_Dblclk", False), self.FILE_DIALOG_TIMEOUT)
        if not confirm:
            Helper.CustomPrint(f"❌ [{self.chatroom_name}] 파일 전송 확인 창이 뜨지 않았습니다.")
            return False
        time.sleep(0.3)
        if win32gui.GetForegroundWindow() != confirm:
            self.SetForceGroundWindow(confirm)
        win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
        win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
        if not self._wait_for(lambda: self._window_gone(confirm), self.FILE_DIALOG_TIMEOUT):
            Helper.CustomPrint(f"❌ [{self.chatroom_name}] 파일 전송 확인 창이 닫히지 않아 취소합니다.")
            PostMessage(confirm, win32con.WM_CLOSE, 0, 0)
            return False
        return True

    def send_file(self, file_path):
        """파일(음성 등)을 전송한다. 실패하면 안내문을 대신 보낸다."""
        file_path = os.path.abspath(str(file_path)) if file_path else ""
        sent = False
        if file_path and os.path.isfile(file_path):
            try:
                sent = self._send_file_via_dialog(file_path)
            except Exception as e:
                Helper.CustomPrint(f"❌ [{self.chatroom_name}] 파일 전송 중 오류: {e}")
        if not sent:
            self.sendtext(self.chatroom_name, self.chatroomHwnd, "파일 전송에 실패했습니다.")
            return
        Helper.CustomPrint(f"✅ [{self.chatroom_name}] 파일 전송 완료 ({os.path.basename(file_path)})")

    ## 탭
    def SendTab(self, n=1):
        for _ in range(n):
            ctypes.windll.user32.keybd_event(win32con.VK_TAB, 0, 0, 0)  # Key down
            time.sleep(0.01)
            ctypes.windll.user32.keybd_event(win32con.VK_TAB, 0, win32con.KEYEVENTF_KEYUP, 0)  # Key up
            time.sleep(0.02)

    @staticmethod
    def _open_clipboard(attempts=30, delay=0.01):
        """클립보드를 연다. 다른 프로그램(카카오톡이 쓰는 중 등)이 잡고 있으면 잠깐씩 기다렸다 다시 시도한다."""
        for _ in range(attempts):
            try:
                win32clipboard.OpenClipboard()
                return True
            except Exception:
                time.sleep(delay)
        return False

    def _empty_clipboard(self):
        if not self._open_clipboard():
            return False
        try:
            win32clipboard.EmptyClipboard()
            return True
        except Exception:
            return False
        finally:
            win32clipboard.CloseClipboard()

    @staticmethod
    def _clipboard_has_text():
        try:
            return bool(win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT))
        except Exception:
            return False

    def _read_clipboard_text(self):
        """클립보드의 글을 읽는다. 읽을 수 없으면 빈 문자열."""
        if not self._open_clipboard():
            return ""
        try:
            if not win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return ""
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) or ""
        except Exception as e:
            Helper.CustomPrint(f"❌ [{self.chatroom_name}] 클립보드 읽기 오류: {e}")
            return ""
        finally:
            win32clipboard.CloseClipboard()

    def copy_cheat(self, chatroom_name, hwndMain, hwndListControl):
        """
        리스트 컨트롤(hwndListControl)의 모든 텍스트를 복사해서 반환합니다.
        창을 앞으로 가져오지 않고(포커스 없이) 복사하며, 고정 대기 대신 미리 비워 둔 클립보드에
        글이 올라오는 순간까지만 기다린다 — 방 하나당 약 0.1초.
        (클립보드가 '바뀌었는지'만 보면 다른 방이 올려 둔 내용을 이 방 것으로 읽을 수 있다)
        포커스 없는 복사가 실패하면 마지막 시도는 기존 방식(창 전면화 + WM_ACTIVATE)으로 한다.
        예외 발생 시에는 빈 문자열을 반환하고, 에러를 로깅합니다.
        """
        max_retries = 3
        retry_delay = 0.3  # seconds

        for attempt in range(max_retries):
            legacy_focus = attempt == max_retries - 1
            try:
                # 창 확인 (마지막 시도에서만 포커스 강제)
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
                    
                    if legacy_focus:
                        focus_success = self.SetForceGroundWindow(hwndMain)
                        if not focus_success and Helper.is_debug_mode():
                            Helper.CustomPrint(f"⚠️ [{chatroom_name}] 창 포커스 실패 - 계속 진행")

                except Exception as e:
                    Helper.CustomPrint(f"❌ [{chatroom_name}] 창 포커스 예외 발생: {e}")
                    time.sleep(retry_delay)
                    continue

                # 복사 전에 클립보드를 비운다. 비우지 않으면, 이 방의 복사가 늦거나 안 됐을 때
                # 직전에 다른 방이 올려 둔 채팅 내용을 이 방 것으로 읽게 된다 (2026-11-10 사고).
                if not self._empty_clipboard():
                    if Helper.is_debug_mode() or legacy_focus:
                        Helper.CustomPrint(f"⚠️ [{chatroom_name}] 클립보드를 비우지 못했습니다 (시도 {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    continue

                # Ctrl+A, Ctrl+C 조합키로 전체 복사 후, 비워 둔 클립보드에 글이 올라올 때까지 대기
                self.PostKeyEx(hwndListControl, ord('A'), [w.VK_CONTROL], False, activate=legacy_focus)
                self.PostKeyEx(hwndListControl, ord('C'), [w.VK_CONTROL], False, activate=legacy_focus)
                deadline = time.monotonic() + self.COPY_TIMEOUT
                while not self._clipboard_has_text() and time.monotonic() < deadline:
                    time.sleep(0.01)
                if not self._clipboard_has_text():
                    if Helper.is_debug_mode() or legacy_focus:
                        Helper.CustomPrint(f"⚠️ [{chatroom_name}] 복사 응답 없음 (시도 {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    continue

                ctext = self._read_clipboard_text()
                if ctext:  # 내용이 있는 경우에만 반환
                    return ctext
                Helper.CustomPrint(f"❌ [{chatroom_name}] 클립보드에서 채팅 내용을 읽지 못했습니다.")
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

    def PostKeyEx(self, hwnd, key, shift, specialkey, activate=True):
        """
        activate=False면 WM_ACTIVATE를 보내지 않는다. 카카오톡은 WM_ACTIVATE를 받으면
        창을 맨 앞으로 올리므로, 읽기(복사)는 activate=False로 해야 사용자의 작업을 방해하지 않는다.
        """
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

                if activate:
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

    @staticmethod
    def _signatures(message_df):
        """메시지를 구분하는 값 목록: (이름, 표시 시각, 내용). 날짜는 넣지 않는다 —
        대화 일부만 불러와진 창에서는 날짜 줄이 안 보여 같은 메시지의 날짜가 달라질 수 있다."""
        if message_df.empty:
            return []
        return list(zip(message_df['name'], message_df['raw_time'], message_df['message']))

    def _remember_seen(self, message_df):
        """지금 보이는 대화의 끝부분을 '이미 본 것'으로 기억한다 (아무것도 실행하지 않는다)."""
        self._seen_tail = self._signatures(message_df)[-SEEN_TAIL_SIZE:]
        self._tail_misses = 0

    def _select_new_messages(self, message_df):
        """
        이번에 읽은 대화에서 새 메시지만 골라 돌려준다 (없거나 판단할 수 없으면 None).
        직전에 본 대화를 이번 내용에서 찾지 못하면 아무것도 실행하지 않는다 — 다른 방 내용이
        읽혔거나 창이 다시 열린 것일 수 있다. 연속으로 못 찾으면 그때 기준을 새로 잡는다.
        """
        signatures = self._signatures(message_df)
        if not self._seen_tail:
            # 기준이 없다(대화가 비어 있었거나 첫 읽기가 실패) — 지금 보이는 것은 실행하지 않고 기준만 잡는다
            self._remember_seen(message_df)
            return None

        found = find_new_messages(self._seen_tail, signatures)
        if found is None:
            self._tail_misses += 1
            self._log_detection_miss(signatures)
            if self._tail_misses >= RESYNC_AFTER_MISSES:
                self.CustomPrint(
                    f"🔄 직전에 본 대화를 {self._tail_misses}번 연속 찾지 못해 기준을 새로 잡습니다 "
                    f"(지금 보이는 메시지 {len(signatures)}개는 실행하지 않음)"
                )
                self._remember_seen(message_df)
            else:
                self.CustomPrint(
                    f"⚠️ 직전에 본 대화를 이번에 읽은 내용({len(signatures)}개)에서 찾지 못했습니다 "
                    f"({self._tail_misses}/{RESYNC_AFTER_MISSES}) — 이번 내용은 실행하지 않습니다"
                )
            return None

        new_indices, can_update = found
        self._tail_misses = 0
        if can_update:
            self._remember_seen(message_df)
        return message_df.iloc[new_indices]

    def _log_detection_miss(self, signatures):
        """기준을 놓친 순간의 양쪽 끝부분을 saved/detect_debug.log에 남긴다 (원인 분석용, 내용은 앞 16자만)."""
        try:
            def brief(items):
                return [f"{name}|{when}|{str(text)[:16]!r}({len(str(text))})" for name, when, text in items[-8:]]

            from Lib import runtime_paths

            stamp = datetime.datetime.now().strftime("%m-%d %H:%M:%S")
            lines = [
                f"[{stamp}] {self.chatroom_name} miss {self._tail_misses}/{RESYNC_AFTER_MISSES} "
                f"(기억 {len(self._seen_tail)}개, 이번 {len(signatures)}개)",
                "  기억: " + " / ".join(brief(self._seen_tail)),
                "  이번: " + " / ".join(brief(signatures)),
            ]
            path = runtime_paths.SAVED_DIR / "detect_debug.log"
            with open(path, "a", encoding="utf-8") as handle:
                for line in lines:
                    print(line, file=handle)
        except Exception:
            pass  # 진단 기록 실패가 봇 동작을 막아서는 안 된다

    ## 5) 추가된 메시지 중 커맨드 포함 확인
    def check_new_commands(self, message_df):
        """
        1) 새로 복사한 전체 로그를 파싱한 결과(message_df)에서, 직전에 본 대화 이후에 추가된
           메시지만 고른다 (_select_new_messages — 줄 번호가 아니라 내용으로 맞춘다).
        2) 메시지 내용에 chat_command_map의 key(명령어)가 포함되어 있으면 해당 핸들러를 실행한다.
           단, 보낸 지 MAX_COMMAND_AGE_MINUTES분이 넘은 명령은 실행하지 않는다.
        """

        # DataFrame이 비어있거나 필요한 컬럼이 없는 경우 처리
        if message_df.empty:
            self.CustomPrint("📝 파싱된 메시지가 없습니다.")
            return []

        missing = [c for c in ('line_idx', 'name', 'raw_time', 'message') if c not in message_df.columns]
        if missing:
            self.CustomPrint(f"❌ DataFrame에 필요한 컬럼이 없습니다: {missing} (컬럼: {list(message_df.columns)})")
            return []

        new_msgs = self._select_new_messages(message_df)
        if new_msgs is None or new_msgs.empty:
            if Helper.is_debug_mode():
                self.CustomPrint("📝 새 메시지 없음", saveLog=False)
            return []
        self.CustomPrint(f"📨 새 메시지 {len(new_msgs)}개 발견")

        results = []
        for idx, row in new_msgs.iterrows():
            msg = row['message']
            name = row['name']
            line_idx = row['line_idx']

            if self.is_ignore_message(msg, name) == 1:
                continue

            permissions = access_control.get_default()
            try:
                permissions.record_sender(self.chatroom_name, name)
            except Exception as e:
                self.CustomPrint(f"⚠️ 대화 사용자 기록 실패: {e}", saveLog=False)

            matched = match_command(dataManager.chat_command_Map, msg)
            if matched is not None:
                chat_command, desc, chat_func = matched
                # 안전장치: 새 메시지 판정이 어긋나더라도 오래전 명령이 다시 실행되지 않게 한다
                age = message_age_minutes(row.get('date'), row.get('raw_time'))
                if age is not None and age > MAX_COMMAND_AGE_MINUTES:
                    self.CustomPrint(
                        f"⏭️ 오래된 명령 건너뜀: {chat_command} ({row.get('raw_time')}, 약 {int(age)}분 전)"
                    )
                    continue
                decision = permissions.check(self.chatroom_name, name, chat_command)
                if not decision.allowed:
                    self.CustomPrint(f"🚫 권한 없음: {name} - {chat_command} ({decision.reason})")
                    if decision.reply:
                        self.send(decision.reply, "text")
                    continue
                message = self.split_command(chat_command, msg)
                self.CustomPrint(f"🎯 명령어 감지: {chat_command} (line_idx: {line_idx})")

                try:
                    resultString, result_type = chat_func(self.chatroom_name, chat_command, message)
                    if result_type is not None:
                        self.send(resultString, result_type)
                    self.CustomPrint(f"✅ 명령어 처리 완료: {self.chatroom_name} - {msg[:30]}... - [{result_type}]")
                except Exception as e:
                    self.CustomPrint(f"❌ 명령어 처리 중 오류: {str(e)}")

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

