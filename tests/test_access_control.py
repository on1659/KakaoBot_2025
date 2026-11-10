from __future__ import annotations

import json
import os

import pytest

from Lib import access_control
from Lib.access_control import AccessControl, default_permissions, validate_permissions


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def acl(tmp_path, clock):
    return AccessControl(tmp_path / "permissions.json", tmp_path / "seen.json", clock=clock)


def rules(**overrides):
    data = default_permissions()
    data.update(overrides)
    return data


def test_missing_file_allows_everything(acl):
    assert acl.check("방", "아무개", "#gpt").allowed
    assert acl.check("방", "아무개", "#없는명령").allowed


def test_every_registered_command_belongs_to_one_feature():
    from Lib import dataManager

    keys = [entry[0] for entry in dataManager.chat_command_Map]
    feature_commands = [c for f in access_control.FEATURES for c in f.commands]
    assert sorted(keys) == sorted(feature_commands)
    assert len(feature_commands) == len(set(feature_commands))


def test_disabled_feature_blocks_all_aliases_even_for_admin(acl):
    data = rules(users=[{"name": "관리", "role": "admin"}])
    data["features"]["instagram"]["enabled"] = False
    acl.save(data)
    assert not acl.check("방", "관리", "https://www.instagram.com/").allowed
    assert not acl.check("방", "관리", "https://instagram.com/").allowed
    assert acl.check("방", "관리", "#gpt").allowed


def test_room_restriction(acl):
    data = rules()
    data["features"]["gpt"]["rooms"] = ["봇방"]
    acl.save(data)
    assert acl.check("봇방", "누구", "#gpt").allowed
    decision = acl.check("다른방", "누구", "#gpt")
    assert not decision.allowed and decision.reason == "허용되지 않은 방"


def test_levels_and_roles(acl):
    data = rules(
        users=[
            {"name": "관리", "role": "admin"},
            {"name": "회원", "role": "user"},
            {"name": "악당", "role": "blocked"},
        ]
    )
    data["features"]["gpt"]["level"] = "user"
    data["features"]["gpt_model_change"]["level"] = "admin"
    acl.save(data)

    assert not acl.check("방", "악당", "#유툽").allowed
    assert acl.check("방", "손님", "#유툽").allowed

    assert acl.check("방", "회원", "#gpt").allowed
    assert acl.check("방", "관리", "#gpt").allowed
    assert not acl.check("방", "손님", "#gpt").allowed

    assert acl.check("방", "관리", "#model").allowed
    assert not acl.check("방", "회원", "#model").allowed


def test_deny_unregistered_policy(acl):
    acl.save(rules(unregistered_policy="deny", users=[{"name": "회원", "role": "user"}]))
    assert acl.check("방", " 회원 ", "#gpt").allowed
    decision = acl.check("방", "손님", "#gpt")
    assert not decision.allowed and decision.reason == "미등록 사용자"


def test_deny_reply_is_rate_limited_and_not_sent_to_blocked(acl, clock):
    data = rules(
        unregistered_policy="deny",
        deny_message="권한이 없습니다",
        users=[{"name": "악당", "role": "blocked"}],
    )
    acl.save(data)

    assert acl.check("방", "손님", "#gpt").reply == "권한이 없습니다"
    assert acl.check("방", "손님", "#gpt").reply is None
    clock.now += access_control.DENY_REPLY_COOLDOWN_SECONDS + 1
    assert acl.check("방", "손님", "#gpt").reply == "권한이 없습니다"

    blocked = acl.check("방", "악당", "#gpt")
    assert not blocked.allowed and blocked.reply is None


def test_file_changes_are_picked_up_without_restart(acl, tmp_path):
    path = tmp_path / "permissions.json"
    acl.save(rules())
    assert acl.check("방", "누구", "#gpt").allowed

    data = rules()
    data["features"]["gpt"]["enabled"] = False
    path.write_text(json.dumps(data), encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert not acl.check("방", "누구", "#gpt").allowed


def test_broken_file_keeps_last_good_rules(acl, tmp_path):
    path = tmp_path / "permissions.json"
    data = rules()
    data["features"]["gpt"]["enabled"] = False
    acl.save(data)
    assert not acl.check("방", "누구", "#gpt").allowed

    path.write_text("{ broken", encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert not acl.check("방", "누구", "#gpt").allowed
    assert acl.check("방", "누구", "#유툽").allowed


def test_broken_file_on_first_load_fails_closed(tmp_path):
    path = tmp_path / "permissions.json"
    path.write_text("not json", encoding="utf-8")
    acl = AccessControl(path, tmp_path / "seen.json")
    decision = acl.check("방", "누구", "#유툽")
    assert not decision.allowed and decision.reason == "권한 설정 파일 오류"


def test_validation_errors():
    _, errors = validate_permissions(
        {
            "unregistered_policy": "maybe",
            "users": [
                {"name": "", "role": "user"},
                {"name": "a", "role": "user"},
                {"name": "a", "role": "user"},
                {"name": "b", "role": "god"},
            ],
            "features": {"gpt": {"enabled": "yes"}, "unknown": {}},
        }
    )
    assert len(errors) == 5


def test_save_rejects_invalid_and_does_not_write(acl, tmp_path):
    with pytest.raises(ValueError):
        acl.save({"users": [{"name": "x", "role": "root"}]})
    assert not (tmp_path / "permissions.json").exists()


def test_validation_normalizes_rooms_and_fills_missing_features():
    normalized, errors = validate_permissions(
        {"features": {"gpt": {"enabled": True, "level": "user", "rooms": [" 봇방 ", "봇방", ""]}}}
    )
    assert not errors
    assert normalized["features"]["gpt"] == {"enabled": True, "level": "user", "rooms": ["봇방"]}
    assert set(normalized["features"]) == {f.id for f in access_control.FEATURES}


def test_seen_users_are_recorded_and_merged(acl, tmp_path):
    acl.record_sender("방1", "철수")
    acl.record_sender("방2", "철수")
    acl.record_sender("방1", "영희")
    acl.record_sender("방1", "  ")

    reader = AccessControl(tmp_path / "permissions.json", tmp_path / "seen.json")
    seen = {entry["name"]: entry for entry in reader.seen_users()}
    assert set(seen) == {"철수", "영희"}
    assert seen["철수"]["rooms"] == ["방1", "방2"]
    assert seen["철수"]["count"] == 2


def test_seen_users_count_is_flushed_periodically(acl, clock, tmp_path):
    acl.record_sender("방", "철수")
    acl.record_sender("방", "철수")
    reader = AccessControl(tmp_path / "permissions.json", tmp_path / "seen.json")
    assert reader.seen_users()[0]["count"] == 1  # repeat messages are buffered

    clock.now += access_control.SEEN_FLUSH_INTERVAL_SECONDS + 1
    acl.record_sender("방", "철수")
    assert reader.seen_users()[0]["count"] == 3
