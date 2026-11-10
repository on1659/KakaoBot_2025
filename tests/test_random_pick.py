# -*- coding: utf-8 -*-
import random

import pytest

from Lib import dataManager, random_pick
from Lib.chat_process import match_command


@pytest.mark.parametrize(
    "message,expected",
    [
        ("짜장 vs 짬뽕", ["짜장", "짬뽕"]),
        ("짜장 VS 짬뽕 Vs 볶음밥", ["짜장", "짬뽕", "볶음밥"]),
        ("  치킨   vs.  피자 ", ["치킨", "피자"]),
        ("짜장 vs 짬뽕?", ["짜장", "짬뽕"]),
        ("아이폰 16 프로 vs 갤럭시 S25 울트라", ["아이폰 16 프로", "갤럭시 S25 울트라"]),
        ("뱅호vs빠끄", ["뱅호", "빠끄"]),
        ("짜장VS짬뽕vs볶음밥", ["짜장", "짬뽕", "볶음밥"]),
        ("짜장 vs짬뽕", ["짜장", "짬뽕"]),
    ],
)
def test_parse_options(message, expected):
    assert random_pick.parse_options(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "vscode 좋아",                      # 영단어의 일부
        "devs 모임 언제야",                  # 영단어의 일부
        "1vs1 하자",                         # 숫자에 붙은 vs
        "짜장 vs ",                          # 빈 선택지
        "어제 경기 봤는데 진짜 대단하더라 한국 vs 일본",  # 단어가 너무 많음
        "한국 vs 일본 경기 봤어? 진짜 재밌더라",
        "가" * 21 + " vs 나",                 # 선택지가 너무 긺
        "짜장 vs 짬뽕\n뭐 먹지",             # 여러 줄
        "이거 봐 https://x.com vs 저거",     # 링크 포함
        " vs ".join(str(i) for i in range(11)),  # 선택지 11개
    ],
)
def test_parse_rejects_casual_chat(message):
    assert random_pick.parse_options(message) is None


def test_get_data_picks_one_option():
    text, kind = random_pick.GetData("방", " vs ", "짜장 vs 짬뽕", rng=random.Random(1))
    assert kind == "text"
    first, second = text.split("\n")
    assert first == '"짜장" vs "짬뽕"'
    assert second in {"  ▶ 짜장", "  ▶ 짬뽕"}


def test_reply_never_retriggers_itself():
    text, _ = random_pick.GetData("방", " vs ", "A vs B vs C", rng=random.Random(0))
    entry = match_command(dataManager.chat_command_Map, text)
    assert entry is None or entry[2]("방", entry[0], text) == ("", "none")


def test_non_matching_message_sends_nothing():
    assert random_pick.GetData("방", " vs ", "한국 vs 일본 경기 봤어? 진짜 재밌더라") == ("", "none")


@pytest.mark.parametrize("message", ["짜장 vs 짬뽕", "짜장 VS 짬뽕", "짜장 Vs 짬뽕", "뱅호vs빠끄"])
def test_dispatcher_routes_all_spellings(message):
    entry = match_command(dataManager.chat_command_Map, message)
    assert entry is not None and entry[2] is random_pick.GetData


def test_explicit_command_wins_over_vs():
    entry = match_command(dataManager.chat_command_Map, "#gpt 짜장 vs 짬뽕 뭐가 나아?")
    assert entry[0] == "#gpt"


def test_english_word_does_not_hide_later_command():
    # 'vscode'가 vs 기능으로 잡히면 뒤의 #gpt가 묻힌다
    entry = match_command(dataManager.chat_command_Map, "vscode 설정 #gpt 알려줘")
    assert entry[0] == "#gpt"


def test_trigger_is_registered_once():
    keys = [e[0] for e in dataManager.chat_command_Map if e[2] is random_pick.GetData]
    assert keys == [random_pick.TRIGGER]
