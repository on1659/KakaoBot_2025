# -*- coding: utf-8 -*-
from __future__ import annotations

import configparser
import json
from pathlib import Path

import pytest

from Lib.settings_manager import (
    BotSettings,
    FeatherServer,
    GptModel,
    SettingsManager,
)


FULL_INI = """\
[BotName]
name = 테스트봇🤖

[RoomList]
가족방💖
개발 토론방

[APIKey]
path = config/비밀키.json

[ChattingRoomSetting]
path = config/chatrooms.json

[EveryMentionDefaultDelayTime]
value = 0.025

[GPT]
maxToken = 2048
defaultModel = gpt-test-mini
answerLengthLimit = 답변은 700자 이내로 정리해줘 ✨

[GPT_MODEL]
gpt-test-mini / 75
gpt-test-pro / 125.5

[RADAR]
baseUrl = https://radar.example.test/api/
apiKeyEnv = GAME_WIKI_API_KEY

[GitHub]
autoUpdate = false
branch = develop/ui

[FeatherMonitor]
enabled = true
notification_room = 가족방💖
log_filename = latest.log
server_names = 생존 서버, 모드 서버
server_paths = C:\\Feather\\생존, D:\\Feather\\모드
"""


def test_loads_every_ini_section_with_unicode(tmp_path: Path) -> None:
    settings_file = tmp_path / "DefaultSetting.ini"
    settings_file.write_text(FULL_INI, encoding="utf-8")

    manager = SettingsManager(settings_file, tmp_path / "api_key.json")
    settings = manager.load()

    assert settings.bot_name == "테스트봇🤖"
    assert settings.rooms == ["가족방💖", "개발 토론방"]
    assert settings.api_key_path == "config/비밀키.json"
    assert settings.chatroom_settings_path == "config/chatrooms.json"
    assert settings.every_mention_delay == pytest.approx(0.025)
    assert settings.gpt_max_token == 2048
    assert settings.gpt_default_model == "gpt-test-mini"
    assert settings.gpt_answer_length_limit.endswith("✨")
    assert settings.gpt_models == [
        GptModel("gpt-test-mini", 75.0),
        GptModel("gpt-test-pro", 125.5),
    ]
    assert settings.radar_base_url == "https://radar.example.test/api"
    assert settings.radar_api_key_env == "GAME_WIKI_API_KEY"
    assert settings.github_auto_update is False
    assert settings.github_branch == "develop/ui"
    assert settings.feather_enabled is True
    assert settings.feather_notification_room == "가족방💖"
    assert settings.feather_log_filename == "latest.log"
    assert settings.feather_servers == [
        FeatherServer("생존 서버", r"C:\Feather\생존"),
        FeatherServer("모드 서버", r"D:\Feather\모드"),
    ]
    assert manager.validate(settings) == []


def test_save_round_trip_preserves_all_sections_and_creates_backup(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "config" / "DefaultSetting.ini"
    settings_file.parent.mkdir()
    old_contents = "[BotName]\nname = 이전봇\n"
    settings_file.write_text(old_contents, encoding="utf-8")

    settings = BotSettings(
        bot_name="새봇🚀",
        rooms=["첫 번째 방", "두번째방💬"],
        api_key_path="config/api_key.json",
        chatroom_settings_path="config/chatrooms.json",
        every_mention_delay=0.01,
        gpt_max_token=4096,
        gpt_default_model="gpt-테스트",
        gpt_answer_length_limit="한국어로 간단히 답변해줘",
        gpt_models=[GptModel("gpt-테스트", 80), GptModel("gpt-pro", 130.25)],
        radar_base_url="https://radar.example.test",
        radar_api_key_env="RADAR_SECRET",
        github_auto_update=False,
        github_branch="release/ui",
        feather_enabled=True,
        feather_notification_room="첫 번째 방",
        feather_log_filename="latest.log",
        feather_servers=[
            FeatherServer("메인 서버", r"C:\Servers\메인"),
            FeatherServer("보조 서버", r"D:\Servers\보조"),
        ],
    )
    manager = SettingsManager(settings_file, tmp_path / "api_key.json")

    manager.save(settings)

    assert settings_file.with_suffix(".ini.bak").read_text(encoding="utf-8") == old_contents
    assert not list(settings_file.parent.glob("*.tmp"))
    assert manager.load() == settings

    parser = configparser.ConfigParser(allow_no_value=True)
    parser.optionxform = str
    parser.read(settings_file, encoding="utf-8")
    assert parser.sections() == [
        "BotName",
        "RoomList",
        "APIKey",
        "ChattingRoomSetting",
        "EveryMentionDefaultDelayTime",
        "GPT",
        "GPT_MODEL",
        "RADAR",
        "GitHub",
        "FeatherMonitor",
    ]
    assert parser.get("FeatherMonitor", "log_filename") == "latest.log"


def test_validate_reports_bad_numbers_duplicates_and_cross_references() -> None:
    settings = BotSettings(
        bot_name="",
        rooms=["중복방", "중복방", "  "],
        every_mention_delay=-1,
        gpt_max_token="not-a-number",  # type: ignore[arg-type]
        gpt_default_model="missing-model",
        gpt_models=[
            GptModel("same", 80),
            GptModel("same", "invalid"),  # type: ignore[arg-type]
        ],
        radar_base_url="not-a-url",
        radar_api_key_env="INVALID ENV NAME",
        github_auto_update="maybe",  # type: ignore[arg-type]
        feather_enabled=True,
        feather_notification_room="없는방",
        feather_servers=[
            FeatherServer("서버", r"C:\Server"),
            FeatherServer("서버", r"C:\Server"),
        ],
    )

    errors = SettingsManager("unused.ini", "unused.json").validate(settings)
    combined = "\n".join(errors)

    assert "봇 이름" in combined
    assert "중복된 채팅방" in combined
    assert "전체 멘션 기본 지연" in combined
    assert "최대 토큰" in combined
    assert "중복된 GPT 모델명" in combined
    assert "비용 비율" in combined
    assert "기본 모델" in combined
    assert "Radar Base URL" in combined
    assert "환경변수" in combined
    assert "Git 자동 업데이트" in combined
    assert "알림 채팅방은 등록된 채팅방" in combined
    assert "중복된 Feather 서버 이름" in combined
    assert "중복된 Feather 서버 경로" in combined


def test_malformed_numeric_values_load_for_ui_then_validate(tmp_path: Path) -> None:
    contents = FULL_INI.replace("value = 0.025", "value = fast").replace(
        "maxToken = 2048", "maxToken = many"
    ).replace("gpt-test-mini / 75", "gpt-test-mini / expensive")
    settings_file = tmp_path / "DefaultSetting.ini"
    settings_file.write_text(contents, encoding="utf-8")
    manager = SettingsManager(settings_file, tmp_path / "keys.json")

    settings = manager.load()
    errors = "\n".join(manager.validate(settings))

    assert settings.every_mention_delay == "fast"
    assert settings.gpt_max_token == "many"
    assert settings.gpt_models[0].cost_percent == "expensive"
    assert "전체 멘션 기본 지연" in errors
    assert "최대 토큰" in errors
    assert "비용 비율" in errors


def test_load_retains_duplicate_valueless_entries_for_validation(
    tmp_path: Path,
) -> None:
    contents = FULL_INI.replace(
        "가족방💖\n개발 토론방", "가족방💖\n가족방💖"
    ).replace(
        "gpt-test-mini / 75\ngpt-test-pro / 125.5",
        "gpt-test-mini / 75\ngpt-test-mini / 125.5",
    )
    settings_file = tmp_path / "DefaultSetting.ini"
    settings_file.write_text(contents, encoding="utf-8")
    manager = SettingsManager(settings_file, tmp_path / "keys.json")

    settings = manager.load()
    errors = "\n".join(manager.validate(settings))

    assert settings.rooms == ["가족방💖", "가족방💖"]
    assert [model.name for model in settings.gpt_models] == [
        "gpt-test-mini",
        "gpt-test-mini",
    ]
    assert "중복된 채팅방" in errors
    assert "중복된 GPT 모델명" in errors


def test_invalid_save_does_not_touch_existing_file(tmp_path: Path) -> None:
    settings_file = tmp_path / "DefaultSetting.ini"
    settings_file.write_text("do not replace", encoding="utf-8")
    manager = SettingsManager(settings_file, tmp_path / "keys.json")

    with pytest.raises(ValueError, match="봇 이름"):
        manager.save(BotSettings(bot_name=""))

    assert settings_file.read_text(encoding="utf-8") == "do not replace"
    assert not settings_file.with_suffix(".ini.bak").exists()


def test_api_keys_support_legacy_load_and_atomic_save(tmp_path: Path) -> None:
    keys_file = tmp_path / "config" / "api_key.json"
    keys_file.parent.mkdir()
    original = [
        {"name": "OPENAI_API_KEY", "key": "secret-one"},
        {"name": "IG_PASSWORD", "key": "한글비밀번호🔒"},
    ]
    keys_file.write_text(
        json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manager = SettingsManager(tmp_path / "settings.ini", keys_file)

    assert manager.load_api_keys() == {
        "OPENAI_API_KEY": "secret-one",
        "IG_PASSWORD": "한글비밀번호🔒",
    }

    replacement = {
        "OPENAI_API_KEY": "new-secret",
        "GAME_WIKI_API_KEY": "레이더키✨",
    }
    manager.save_api_keys(replacement)

    assert json.loads(keys_file.with_suffix(".json.bak").read_text(encoding="utf-8")) == original
    assert manager.load_api_keys() == replacement
    on_disk = json.loads(keys_file.read_text(encoding="utf-8"))
    assert on_disk == [
        {"name": "OPENAI_API_KEY", "key": "new-secret"},
        {"name": "GAME_WIKI_API_KEY", "key": "레이더키✨"},
    ]
    assert not list(keys_file.parent.glob("*.tmp"))


def test_duplicate_api_keys_keep_legacy_last_value_and_warn(tmp_path: Path) -> None:
    keys_file = tmp_path / "api_key.json"
    keys_file.write_text(
        json.dumps(
            [
                {"name": "KAKAO_ACCESS_TOKEN", "key": "old"},
                {"name": "KAKAO_ACCESS_TOKEN", "key": "new"},
            ]
        ),
        encoding="utf-8",
    )
    manager = SettingsManager(tmp_path / "settings.ini", keys_file)

    assert manager.load_api_keys() == {"KAKAO_ACCESS_TOKEN": "new"}
    assert manager.api_key_warnings and "중복된 API 키" in manager.api_key_warnings[0]


def test_percent_signs_round_trip_and_remain_legacy_configparser_compatible(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "DefaultSetting.ini"
    manager = SettingsManager(settings_file, tmp_path / "keys.json")
    settings = BotSettings(
        bot_name="100% 봇",
        gpt_answer_length_limit="핵심만 80% 분량으로 답변",
    )

    manager.save(settings)

    assert manager.load() == settings
    parser = configparser.ConfigParser(allow_no_value=True)
    parser.optionxform = str
    parser.read(settings_file, encoding="utf-8")
    assert parser.get("BotName", "name") == "100% 봇"
    assert parser.get("GPT", "answerLengthLimit") == "핵심만 80% 분량으로 답변"


def test_missing_files_return_empty_ui_values_and_template_is_valid(
    tmp_path: Path,
) -> None:
    manager = SettingsManager(tmp_path / "missing.ini", tmp_path / "missing.json")

    defaults = manager.load()
    assert isinstance(defaults, BotSettings)
    assert manager.load_api_keys() == {}
    assert manager.validate(defaults) == []

    template = Path(__file__).resolve().parents[1] / "config" / "DefaultSetting.template.ini"
    template_settings = SettingsManager(template, tmp_path / "missing.json").load()
    assert SettingsManager(template, tmp_path / "missing.json").validate(template_settings) == []


@pytest.mark.parametrize(
    ("mapping", "message"),
    [
        ({"INVALID NAME": "secret"}, "올바르지 않은 API 키 이름"),
        ({"VALID_NAME": 123}, "문자열"),
    ],
)
def test_rejects_invalid_api_key_mapping(
    tmp_path: Path, mapping: dict[str, object], message: str
) -> None:
    manager = SettingsManager(tmp_path / "settings.ini", tmp_path / "keys.json")

    with pytest.raises(ValueError, match=message):
        manager.save_api_keys(mapping)  # type: ignore[arg-type]

    assert not manager.api_keys_path.exists()
