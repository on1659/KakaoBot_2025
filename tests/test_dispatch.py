# -*- coding: utf-8 -*-
"""디스패처·전송 회귀 테스트 (docs/instagram_기능_복구_작업계획.md §7)"""
from Lib import dataManager
from Lib.chat_process import ChatProcess, match_command


# ─── 명령 매칭: 긴 키 우선 + 단일 발화 (§4.4) ────────────────────────

SYNTHETIC_MAP = [
    ['#model', "d1", "f1"],
    ['#modelcheck', "d2", "f2"],
    ['https://www.instagram.com/', "d3", "f3"],
    ['https://instagram.com/', "d4", "f4"],
]


def test_modelcheck_fires_only_modelcheck():
    # 회귀: '#modelcheck' 입력이 '#model' 핸들러까지 발화하던 버그
    entry = match_command(SYNTHETIC_MAP, "#modelcheck gpt-5")
    assert entry[0] == '#modelcheck'


def test_model_still_matches():
    entry = match_command(SYNTHETIC_MAP, "#model gpt-5")
    assert entry[0] == '#model'


def test_www_url_matches_www_key():
    entry = match_command(SYNTHETIC_MAP, "봐봐 https://www.instagram.com/p/ABC/")
    assert entry[0] == 'https://www.instagram.com/'


def test_wwwless_url_matches_wwwless_key():
    # 회귀: www 없는 URL은 어떤 키에도 안 걸려 핸들러 미호출이던 버그
    entry = match_command(SYNTHETIC_MAP, "https://instagram.com/p/ABC/")
    assert entry[0] == 'https://instagram.com/'


def test_no_match_returns_none():
    assert match_command(SYNTHETIC_MAP, "그냥 잡담") is None


def test_earlier_command_beats_longer_url_key():
    # 위치 우선: 앞선 명시적 명령이 뒤의 긴 URL 키에 가로채이지 않는다
    entry = match_command(SYNTHETIC_MAP, "#model 이거 봐 https://www.instagram.com/p/ABC/")
    assert entry[0] == '#model'


def test_same_position_longer_key_wins():
    # 같은 위치에서는 긴 키가 이긴다 (#model vs #modelcheck)
    entry = match_command(SYNTHETIC_MAP, "#modelcheck")
    assert entry[0] == '#modelcheck'


def test_help_output_hides_none_description():
    # 회귀: 별칭 항목의 desc "None"이 #command 도움말에 그대로 노출되던 버그
    output = dataManager.format_available_commands("#command")
    assert "\nNone" not in output and not output.endswith("None")


def test_real_command_map_has_both_instagram_keys():
    keys = [k for k, _, _ in dataManager.chat_command_Map]
    assert 'https://www.instagram.com/' in keys
    assert 'https://instagram.com/' in keys


def test_real_map_modelcheck_single_dispatch():
    entry = match_command(dataManager.chat_command_Map, "#modelcheck")
    assert entry is not None and entry[0] == '#modelcheck'


# ─── send_image: 실패 시 채팅 로그 에코 금지 (§4.5) ───────────────────

def _bare_chat_process(monkeypatch, sent):
    """실제 카카오톡 창 없이 ChatProcess 인스턴스를 만든다 (§7 격리 전략)."""
    cp = ChatProcess.__new__(ChatProcess)
    cp.chatroom_name = "테스트방"
    cp.chatroomHwnd = 0
    monkeypatch.setattr(
        cp, "sendtext",
        lambda room, hwnd, text: sent.append(text), raising=False)
    return cp


def test_send_image_empty_payload_falls_back_to_text(monkeypatch):
    sent = []
    cp = _bare_chat_process(monkeypatch, sent)
    cp.send_image(None)
    cp.send_image(b"")
    assert sent == ["이미지 전송에 실패했습니다."] * 2


def test_send_image_clipboard_failure_falls_back_to_text(monkeypatch):
    sent = []
    cp = _bare_chat_process(monkeypatch, sent)
    monkeypatch.setattr(cp, "_copy_dib_to_clipboard", lambda b: False, raising=False)
    cp.send_image(b"\x28\x00\x00\x00fakebytes")
    # 회귀: 여기서 붙여넣기를 강행하면 run()이 복사해 둔 방 채팅 로그가 게시된다
    assert sent == ["이미지 전송에 실패했습니다."]


def test_send_routes_image_payload_to_send_image(monkeypatch):
    captured = []
    cp = ChatProcess.__new__(ChatProcess)
    cp.chatroom_name = "테스트방"
    cp.chatroomHwnd = 0
    monkeypatch.setattr(cp, "send_image", lambda p: captured.append(("image", p)), raising=False)
    monkeypatch.setattr(cp, "sendtext", lambda r, h, t: captured.append(("text", t)), raising=False)
    cp.send(b"dibdata", "image")
    cp.send("안내문", "text")
    cp.send("무시", "none")  # 핸들러가 ("", "none")을 반환하는 경우 — 전송 없음
    assert captured == [("image", b"dibdata"), ("text", "안내문")]
