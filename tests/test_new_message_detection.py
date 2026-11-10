# -*- coding: utf-8 -*-
"""
새 메시지 판정 회귀 테스트.

2026-11-10 사고: 새 메시지를 '복사한 글의 줄 번호'로 가려서, 복사한 글의 길이가 달라지는 순간
(다른 방 내용이 읽힘 / 창이 다시 열려 일부만 보임 / 이전 대화가 더 불러와짐) 예전 메시지 수백 개가
새 메시지로 처리돼 옛 인스타 링크의 이미지가 다시 전송됐다.
"""
import datetime

import pytest

from Lib import access_control, chat_process, dataManager
from Lib.chat_process import ChatProcess, find_new_messages, message_age_minutes


def now_time(minutes_ago=0):
    moment = datetime.datetime.now() - datetime.timedelta(minutes=minutes_ago)
    marker = "오전" if moment.hour < 12 else "오후"
    hour = moment.hour % 12 or 12
    return f"{marker} {hour}:{moment.minute:02d}"


def chat_text(messages, date_line="2026년 11월 10일 화요일"):
    """[(이름, 시각, 내용)] → 카카오톡에서 복사한 것 같은 글."""
    lines = [date_line] if date_line else []
    lines += [f"[{name}] [{time}] {text}" for name, time, text in messages]
    return "\r\n".join(lines)


OLD = [("철수", "오후 1:00", f"옛날 얘기 {i}") for i in range(30)]
OLD_LINK = ("영희", "오후 1:30", "#테스트 옛날 명령")
HISTORY = OLD + [OLD_LINK] + [("철수", "오후 2:00", f"그 뒤 얘기 {i}") for i in range(20)]
OTHER_ROOM = [("민수", "오전 9:00", f"다른 방 얘기 {i}") for i in range(33)]


@pytest.fixture
def chat(monkeypatch, tmp_path):
    """실제 카카오톡 없이 판정·실행 경로만 도는 ChatProcess. 실행된 명령은 chat.fired에 쌓인다."""
    cp = ChatProcess.__new__(ChatProcess)
    cp.chatroom_name = "방"
    cp.BotName = "봇"
    cp.stop_event = None
    cp.IsLoad = 1
    cp.chatroomHwnd = 1
    cp.hwndListControl = 2
    cp._first_run = True
    cp._last_copy_text = None
    cp._next_init_retry = 0.0
    cp.last_activity = 0.0
    cp._seen_tail = None
    cp._tail_misses = 0
    cp.fired = []
    cp.logs = []
    cp.next_text = ""

    cp.is_kakao_running = lambda: True
    cp.validate_window_handle = lambda hwnd, name: True
    cp.copy_cheat = lambda *args: cp.next_text
    cp.process_message_queue = lambda: None
    cp.CustomPrint = lambda message, saveLog=True: cp.logs.append(str(message))
    cp.send = lambda payload, kind="text": None

    def handler(room, command, message):
        cp.fired.append(message)
        return "", "none"

    monkeypatch.setattr(dataManager, "chat_command_Map", [["#테스트", "설명", handler]])
    acl = access_control.AccessControl(tmp_path / "permissions.json", tmp_path / "seen.json")
    monkeypatch.setattr(access_control, "get_default", lambda: acl)

    def read(messages, **kwargs):
        cp.next_text = chat_text(messages, **kwargs)
        cp.run()

    cp.read = read
    return cp


# ─── find_new_messages ───────────────────────────────────────────────────

def sig(*texts):
    return [("a", "오후 1:00", t) for t in texts]


def new_texts(seen, signatures):
    """(새 메시지 내용 목록, 기억 갱신 가능 여부) — 못 맞추면 None."""
    found = find_new_messages(seen, signatures)
    if found is None:
        return None
    indices, can_update = found
    return [signatures[i][2] for i in indices], can_update


def test_alignment_basic_append_prepend_and_trim():
    seen = sig("3", "4", "5")
    assert new_texts(seen, sig("1", "2", "3", "4", "5")) == ([], True)                 # 변화 없음
    assert new_texts(seen, sig("1", "2", "3", "4", "5", "6", "7")) == (["6", "7"], True)  # 뒤에 2개 추가
    assert new_texts(seen, sig("x", "y", "1", "2", "3", "4", "5", "6")) == (["6"], True)  # 앞에 이전 대화가 더 불러와짐
    assert new_texts(seen, sig("3", "4", "5", "6")) == (["6"], True)                    # 앞쪽이 잘려 나감


def test_alignment_rejects_unrelated_content():
    seen = sig("3", "4", "5")
    assert new_texts(seen, sig("가", "나", "다", "라")) is None
    assert new_texts(seen, []) is None
    assert new_texts([], sig("1", "2")) is None


def test_alignment_does_not_accept_a_single_coincidence():
    # 한두 개만 우연히 같은 것은 같은 대화라는 근거가 못 된다
    seen = sig("1", "2", "3", "4", "ㅋㅋ")
    assert new_texts(seen, sig("ㅋㅋ", "전혀", "다른", "내용")) is None
    assert new_texts(seen, sig("전혀", "다른", "내용", "ㅋㅋ")) is None


def test_alignment_treats_changed_text_from_same_sender_and_time_as_old():
    seen = sig("1", "2", "3", "4", "5", "6")
    # 마지막 메시지가 삭제 표시로 바뀌고(같은 사람·같은 시각), 그 뒤에 새 메시지가 하나 왔다
    assert new_texts(seen, sig("1", "2", "3", "4", "5", "삭제된 메시지입니다.", "새 글")) == (["새 글"], True)
    # 예전 명령 뒤에 시스템 안내가 붙어 내용이 달라져도 다시 실행하지 않는다
    changed = "#tts 안녕" + chr(10) + "철수님이 들어왔습니다."
    assert new_texts(sig("1", "2", "3", "#tts 안녕"), sig("1", "2", "3", changed)) == ([], True)


def test_alignment_finds_message_inserted_before_the_bots_reply():
    # 단체방: 봇의 답장이 먼저 보이고, 조금 전에 보낸 다른 사람의 메시지가 그 앞에 끼어든다
    seen = sig("1", "2", "3", "4", "5", "명령") + [("봇", "오후 1:00", "답장")]
    now = sig("1", "2", "3", "4", "5", "명령") + [("철수", "오후 1:00", "#tts 끼어든 명령"), ("봇", "오후 1:00", "답장")]
    assert new_texts(seen, now) == (["#tts 끼어든 명령"], True)


def test_alignment_survives_a_message_vanishing_from_the_middle():
    seen = sig("1", "2", "3", "4", "5", "6", "7", "8")
    assert new_texts(seen, sig("1", "2", "3", "4", "6", "7", "8", "9")) == (["9"], True)


def test_alignment_stale_view_keeps_memory():
    # 방금 본 마지막 메시지가 이번엔 안 보인다(덜 불러와진 화면) — 새 메시지 없음, 기억은 그대로 둔다
    seen = sig("1", "2", "3", "4", "5", "6")
    assert new_texts(seen, sig("1", "2", "3", "4", "5")) == ([], False)
    assert new_texts(seen, sig("1", "2", "3", "4")) == ([], False)


def test_alignment_ignores_far_away_coincidences_in_old_history():
    # 기억의 첫 메시지와 똑같은 글이 한참 전 대화에도 있어도, 그 사이의 예전 메시지를 새 것으로 보지 않는다
    old_history = sig("ㅋㅋ") + sig(*[f"예전 {i}" for i in range(40)])
    seen = sig("ㅋㅋ", "바뀌기 전", "3", "4", "5", "6", "7", "8")
    now = old_history + sig("ㅋㅋ", "바뀐 뒤", "3", "4", "5", "6", "7", "8", "새 글")
    assert new_texts(seen, now) == (["새 글"], True)


def test_alignment_short_history():
    assert new_texts(sig("1"), sig("1", "2")) == (["2"], True)
    assert new_texts(sig("1", "2"), sig("1", "2", "3")) == (["3"], True)
    assert new_texts(sig("1", "2"), sig("9", "8", "7")) is None


# ─── 실행 경로 ───────────────────────────────────────────────────────────

def test_first_read_never_runs_existing_commands(chat):
    chat.read(HISTORY)
    assert chat.fired == []


def test_new_command_runs_once(chat):
    chat.read(HISTORY)
    chat.read(HISTORY + [("영희", now_time(), "#테스트 새 명령")])
    chat.read(HISTORY + [("영희", now_time(), "#테스트 새 명령"), ("철수", now_time(), "오")])
    assert chat.fired == ["새 명령"]


def test_other_rooms_content_does_not_replay_history(chat):
    # 사고 재현: 한 번 다른 방 내용(33줄)이 읽힌 뒤 다시 정상 내용이 읽힌다
    chat.read(HISTORY)
    chat.read(OTHER_ROOM)
    chat.read(HISTORY)
    assert chat.fired == []
    assert any("찾지 못했습니다" in line for line in chat.logs)


def test_new_command_still_runs_after_a_wrong_read(chat):
    chat.read(HISTORY)
    chat.read(OTHER_ROOM)
    chat.read(HISTORY + [("영희", now_time(), "#테스트 진짜 새 명령")])
    assert chat.fired == ["진짜 새 명령"]


def test_reopened_window_then_history_loading_does_not_replay(chat):
    # 창이 다시 열려 최근 일부만 보이다가, 이전 대화가 차례로 더 불러와진다
    chat.read(HISTORY)
    chat.read(HISTORY[-15:], date_line=None)
    chat.read(HISTORY[-40:], date_line=None)
    chat.read(HISTORY)
    assert chat.fired == []


def test_startup_with_partial_history_does_not_replay(chat):
    # 시작 직후 일부만 불러와진 상태에서 기준을 잡고, 그 뒤에 이전 대화가 불러와진다
    chat.read(HISTORY[-10:], date_line=None)
    chat.read(HISTORY)
    assert chat.fired == []


def test_empty_first_read_does_not_replay(chat):
    # 첫 읽기에 메시지가 하나도 없었어도(로딩 전) 나중에 보이는 예전 메시지를 실행하지 않는다
    chat._first_run = False
    chat._seen_tail = []
    chat.read(HISTORY)
    assert chat.fired == []
    chat.read(HISTORY + [("영희", now_time(), "#테스트 그 다음")])
    assert chat.fired == ["그 다음"]


def test_command_inserted_before_bot_reply_runs_once(chat):
    chat.read(HISTORY)
    command = ("영희", now_time(), "#테스트 첫 명령")
    reply = ("봇", now_time(), "답장")
    chat.read(HISTORY + [command])
    chat.read(HISTORY + [command, reply])
    late = ("철수", now_time(), "#테스트 끼어든 명령")
    chat.read(HISTORY + [command, late, reply])
    chat.read(HISTORY + [command, late, reply, ("철수", now_time(), "ㅇㅋ")])
    assert chat.fired == ["첫 명령", "끼어든 명령"]


def test_stale_view_then_full_view_does_not_rerun(chat):
    chat.read(HISTORY)
    command = ("영희", now_time(), "#테스트 한 번만")
    chat.read(HISTORY + [command])
    chat.read(HISTORY)                      # 방금 본 메시지가 잠깐 안 보이는 화면
    chat.read(HISTORY + [command])          # 다시 보인다
    chat.read(HISTORY + [command, ("봇", now_time(), "답장")])
    assert chat.fired == ["한 번만"]
    assert not any("찾지 못했습니다" in line for line in chat.logs)


def test_miss_is_recorded_for_diagnosis(chat, tmp_path):
    chat.read(HISTORY)
    chat.read(OTHER_ROOM)
    debug = (tmp_path / "detect_debug.log").read_text(encoding="utf-8")
    assert "miss 1/3" in debug and "기억:" in debug and "이번:" in debug


def test_resync_after_repeated_misses_without_running_anything(chat):
    chat.read(HISTORY)
    for round_number in range(chat_process.RESYNC_AFTER_MISSES):
        chat.read(OTHER_ROOM + [("민수", now_time(), f"#테스트 다른 방 명령 {round_number}")])
    assert chat.fired == []
    assert any("기준을 새로 잡습니다" in line for line in chat.logs)
    # 기준을 다시 잡은 뒤에는 그 대화에서 정상 동작한다
    chat.read(OTHER_ROOM + [("민수", now_time(), "#테스트 다른 방 명령 2"), ("민수", now_time(), "#테스트 이어서")])
    assert chat.fired == ["이어서"]


def test_old_command_is_skipped_even_if_it_looks_new(chat):
    # 안전장치: 판정이 어긋나 '새 메시지'로 잡히더라도 오래된 명령은 실행하지 않는다
    chat.read(HISTORY)
    stale = now_time(minutes_ago=chat_process.MAX_COMMAND_AGE_MINUTES + 5)
    chat.read(HISTORY + [("영희", stale, "#테스트 한참 전 명령"), ("영희", now_time(), "#테스트 방금 명령")],
              date_line=datetime.datetime.now().strftime("%Y년 %m월 %d일 화요일"))
    assert chat.fired == ["방금 명령"]
    assert any("오래된 명령 건너뜀" in line for line in chat.logs)


def test_yesterdays_command_is_skipped(chat):
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y년 %m월 %d일 월요일")
    chat.read(HISTORY, date_line=yesterday)
    chat.read(HISTORY + [("영희", now_time(), "#테스트 어제 같은 시각")], date_line=yesterday)
    assert chat.fired == []


# ─── message_age_minutes ─────────────────────────────────────────────────

NOW = datetime.datetime(2026, 11, 10, 16, 56, 30)


@pytest.mark.parametrize(
    "date_text, raw_time, expected",
    [
        ("2026-11-10", "오후 4:56", 0.5),
        ("2026-11-10", "오후 4:57", 0.0),       # 표시 시각이 조금 앞서도 0분
        ("2026-11-10", "오후 4:26", 30.5),
        ("2026-11-10", "오전 12:05", 1011.5),   # 오전 12시 = 0시
        ("2026-11-10", "오후 12:05", 291.5),    # 오후 12시 = 12시
        ("2026-11-09", "오후 4:56", 1440.5),
        (None, "오후 4:50", 6.0),               # 날짜를 모르면 시각 차이
        (None, "오후 11:59", 1017.0),           # 날짜를 모르는 '미래 시각'은 어제로 본다
        ("2026년 이상한 날짜", "16:50", 6.0),
        ("2026-11-10", "4:50 PM", 6.5),
    ],
)
def test_message_age_minutes(date_text, raw_time, expected):
    assert message_age_minutes(date_text, raw_time, NOW) == pytest.approx(expected)


@pytest.mark.parametrize("raw_time", ["", None, "방금", "25:00", "오후 4시"])
def test_message_age_unknown_time_format_is_not_blocked(raw_time):
    assert message_age_minutes("2026-11-10", raw_time, NOW) is None


def test_midnight_rollover_without_date_line():
    just_after_midnight = datetime.datetime(2026, 11, 11, 0, 1, 0)
    assert message_age_minutes(None, "오후 11:59", just_after_midnight) == 2.0


# ─── 클립보드 읽기 ───────────────────────────────────────────────────────

class FakeClipboard:
    """win32clipboard 대역: 내용 하나를 들고 있고, 열려 있을 때만 읽고 쓸 수 있다."""

    def __init__(self, text):
        self.text = text
        self.opened = False
        self.emptied = 0

    def OpenClipboard(self):
        self.opened = True

    def CloseClipboard(self):
        self.opened = False

    def EmptyClipboard(self):
        assert self.opened
        self.text = None
        self.emptied += 1

    def IsClipboardFormatAvailable(self, fmt):
        return self.text is not None

    def GetClipboardData(self, fmt):
        assert self.opened
        return self.text


def bare_chat(monkeypatch, clipboard):
    cp = ChatProcess.__new__(ChatProcess)
    cp.chatroom_name = "방"
    cp.chatroomHwnd = 1
    cp.hwndListControl = 2
    monkeypatch.setattr(chat_process, "win32clipboard", clipboard)
    monkeypatch.setattr(ChatProcess, "COPY_TIMEOUT", 0.05)
    monkeypatch.setattr(chat_process.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(cp, "validate_window_handle", lambda hwnd, name: True, raising=False)
    monkeypatch.setattr(cp, "SetForceGroundWindow", lambda hwnd: True, raising=False)
    return cp


def test_copy_does_not_return_stale_clipboard_when_room_does_not_respond(monkeypatch):
    # 다른 방이 올려 둔 내용이 클립보드에 남아 있고, 이 방은 복사에 응답하지 않는다
    clipboard = FakeClipboard("다른 방의 채팅 내용")
    cp = bare_chat(monkeypatch, clipboard)
    monkeypatch.setattr(cp, "PostKeyEx", lambda *args, **kwargs: None, raising=False)
    assert cp.copy_cheat("방", 1, 2) == ""
    assert clipboard.emptied >= 1


def test_copy_returns_what_this_room_put_on_the_clipboard(monkeypatch):
    clipboard = FakeClipboard("다른 방의 채팅 내용")
    cp = bare_chat(monkeypatch, clipboard)

    def post_key(hwnd, key, *args, **kwargs):
        if key == ord("C"):
            clipboard.text = "이 방의 채팅 내용"

    monkeypatch.setattr(cp, "PostKeyEx", post_key, raising=False)
    assert cp.copy_cheat("방", 1, 2) == "이 방의 채팅 내용"
