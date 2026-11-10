# -*- coding: utf-8 -*-
"""매 사이클 읽기 경로: 내용이 같으면 파싱 생략, 바뀌면 활동 시각 기록."""
import pandas as pd

from Lib.chat_process import ChatProcess


def make_chat(copies):
    chat = ChatProcess.__new__(ChatProcess)
    chat.chatroom_name = "방"
    chat.stop_event = None
    chat.IsLoad = 1
    chat.chatroomHwnd = 1
    chat.hwndListControl = 2
    chat._first_run = False
    chat._last_copy_text = None
    chat._next_init_retry = 0.0
    chat.last_activity = 0.0
    chat.calls = {"parse": 0, "commands": 0, "queue": 0}

    texts = iter(copies)
    chat.is_kakao_running = lambda: True
    chat.validate_window_handle = lambda hwnd, name: True
    chat.copy_cheat = lambda *args: next(texts)

    def parse(text):
        chat.calls["parse"] += 1
        return pd.DataFrame({"line_idx": [1], "name": ["a"], "message": [text]})

    def commands(df):
        chat.calls["commands"] += 1
        return []

    def queue():
        chat.calls["queue"] += 1

    chat.parse_chat_log = parse
    chat.check_new_commands = commands
    chat.process_message_queue = queue
    chat.CustomPrint = lambda *args, **kwargs: None
    return chat


def test_unchanged_chat_skips_parsing_but_still_sends_queue():
    chat = make_chat(["로그1", "로그1", "로그1"])
    chat.run()
    chat.run()
    chat.run()
    assert chat.calls["parse"] == 1
    assert chat.calls["commands"] == 1
    assert chat.calls["queue"] == 3


def test_activity_recorded_only_when_new_content_appears():
    chat = make_chat(["로그1", "로그1", "로그1\n새 메시지"])
    chat.run()
    assert chat.last_activity == 0.0  # 첫 복사는 기준선일 뿐
    chat.run()
    assert chat.last_activity == 0.0
    chat.run()
    assert chat.last_activity > 0.0
    assert chat.calls["parse"] == 2


def test_failed_init_waits_before_retrying(monkeypatch):
    chat = make_chat([])
    chat.IsLoad = 0
    attempts = []
    chat.init = lambda: attempts.append(1)
    chat.run()
    chat.run()
    assert len(attempts) == 1  # 두 번째 사이클은 재시도 간격 때문에 건너뜀
