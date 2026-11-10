"""Typed loading and safe persistence for KakaoBot user settings.

The desktop UI works with the dataclasses in this module instead of editing the
INI file directly.  The serialized format intentionally remains compatible
with the existing ``dataManager`` module: room and GPT model entries are stored
as valueless INI options, and API keys remain a list of ``name``/``key`` JSON
objects on disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import configparser
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Mapping
from urllib.parse import urlparse


try:
    from Lib import runtime_paths as _runtime_paths
except ImportError:  # Allows this module to be used before packaging helpers exist.
    _runtime_paths = None


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_SETTINGS_PATH = (
    Path(_runtime_paths.SETTINGS_FILE)
    if _runtime_paths is not None and hasattr(_runtime_paths, "SETTINGS_FILE")
    else _PROJECT_ROOT / "config" / "DefaultSetting.ini"
)
_DEFAULT_API_KEYS_PATH = (
    Path(_runtime_paths.API_KEYS_FILE)
    if _runtime_paths is not None and hasattr(_runtime_paths, "API_KEYS_FILE")
    else _PROJECT_ROOT / "config" / "api_key.json"
)

_DEFAULT_GPT_MODELS = (
    ("gpt-4o-mini", 80.0),
    ("gpt-5-nano", 70.0),
    ("gpt-5-mini", 90.0),
    ("gpt-5", 120.0),
)
_ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class GptModel:
    """One selectable GPT model and its relative cost percentage."""

    name: str = ""
    cost_percent: float = 100.0


@dataclass
class FeatherServer:
    """One Feather server row as displayed by the settings UI."""

    name: str = ""
    path: str = ""


def _default_gpt_models() -> list[GptModel]:
    return [GptModel(name, cost) for name, cost in _DEFAULT_GPT_MODELS]


@dataclass
class BotSettings:
    """All settings currently represented by ``DefaultSetting.ini``."""

    bot_name: str = "카카오봇"
    rooms: list[str] = field(default_factory=list)
    api_key_path: str = "config/api_key.json"
    chatroom_settings_path: str = "config/chatrooms.json"
    every_mention_delay: float = 0.005
    gpt_max_token: int = 1000
    gpt_default_model: str = "gpt-5-nano"
    gpt_answer_length_limit: str = "답변은 500자 이내로 정리해줘"
    gpt_models: list[GptModel] = field(default_factory=_default_gpt_models)
    radar_base_url: str = "https://awhirl-preimpressive-carina.ngrok-free.dev"
    radar_api_key_env: str = "GAME_WIKI_API_KEY"
    github_auto_update: bool = True
    github_branch: str = "main"
    feather_enabled: bool = False
    feather_notification_room: str = ""
    feather_log_filename: str = "latest.log"
    feather_servers: list[FeatherServer] = field(default_factory=list)


class SettingsManager:
    """Load, validate, and atomically save INI and API-key settings."""

    def __init__(
        self,
        settings_path: str | os.PathLike[str] | None = None,
        api_keys_path: str | os.PathLike[str] | None = None,
    ) -> None:
        self._api_keys_path_explicit = api_keys_path is not None
        self.api_key_warnings: list[str] = []
        self.settings_path = self._absolute_path(
            settings_path if settings_path is not None else _DEFAULT_SETTINGS_PATH
        )
        self.api_keys_path = self._absolute_path(
            api_keys_path if api_keys_path is not None else _DEFAULT_API_KEYS_PATH
        )

    @staticmethod
    def _absolute_path(path: str | os.PathLike[str]) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            data_dir = (
                Path(_runtime_paths.DATA_DIR)
                if _runtime_paths is not None and hasattr(_runtime_paths, "DATA_DIR")
                else _PROJECT_ROOT
            )
            candidate = data_dir / candidate
        return candidate.resolve()

    def load(self) -> BotSettings:
        """Return the INI contents as a UI-friendly typed settings object.

        Missing sections and options use the dataclass defaults.  A completely
        missing file also returns defaults so a first-run UI can still open and
        create the settings file.
        """

        defaults = BotSettings()
        if not self.settings_path.exists():
            return defaults

        parser = self._new_parser()
        try:
            with self.settings_path.open("r", encoding="utf-8-sig") as handle:
                contents = handle.read()
            parser.read_string(contents, source=str(self.settings_path))
        except (configparser.Error, UnicodeError) as exc:
            raise ValueError(f"설정 파일을 읽을 수 없습니다: {exc}") from exc

        rooms = self._load_rooms(parser, contents)
        gpt_models = self._load_gpt_models(parser, defaults.gpt_models, contents)
        feather_servers = self._load_feather_servers(parser)

        settings = BotSettings(
            bot_name=self._get(parser, "BotName", "name", defaults.bot_name),
            rooms=rooms,
            api_key_path=self._get(
                parser, "APIKey", "path", defaults.api_key_path
            ),
            chatroom_settings_path=self._get(
                parser,
                "ChattingRoomSetting",
                "path",
                defaults.chatroom_settings_path,
            ),
            every_mention_delay=self._number_or_raw(
                self._get(
                    parser,
                    "EveryMentionDefaultDelayTime",
                    "value",
                    str(defaults.every_mention_delay),
                ),
                float,
            ),
            gpt_max_token=self._number_or_raw(
                self._get(parser, "GPT", "maxToken", str(defaults.gpt_max_token)),
                int,
            ),
            gpt_default_model=self._get(
                parser, "GPT", "defaultModel", defaults.gpt_default_model
            ),
            gpt_answer_length_limit=self._get(
                parser,
                "GPT",
                "answerLengthLimit",
                defaults.gpt_answer_length_limit,
            ),
            gpt_models=gpt_models,
            radar_base_url=self._get(
                parser, "RADAR", "baseUrl", defaults.radar_base_url
            ).rstrip("/"),
            radar_api_key_env=self._get(
                parser, "RADAR", "apiKeyEnv", defaults.radar_api_key_env
            ),
            github_auto_update=self._bool_or_raw(
                self._get(
                    parser,
                    "GitHub",
                    "autoUpdate",
                    "true" if defaults.github_auto_update else "false",
                )
            ),
            github_branch=self._get(
                parser, "GitHub", "branch", defaults.github_branch
            ),
            feather_enabled=self._bool_or_raw(
                self._get(
                    parser,
                    "FeatherMonitor",
                    "enabled",
                    "true" if defaults.feather_enabled else "false",
                )
            ),
            feather_notification_room=self._get(
                parser,
                "FeatherMonitor",
                "notification_room",
                defaults.feather_notification_room,
            ),
            feather_log_filename=self._get(
                parser,
                "FeatherMonitor",
                "log_filename",
                defaults.feather_log_filename,
            ),
            feather_servers=feather_servers,
        )
        if not self._api_keys_path_explicit:
            self.api_keys_path = self._absolute_path(settings.api_key_path)
        return settings

    def validate(self, settings: BotSettings) -> list[str]:
        """Return human-readable validation errors; an empty list is valid."""

        if not isinstance(settings, BotSettings):
            return ["BotSettings 형식의 설정 객체가 필요합니다."]

        errors: list[str] = []

        if not self._nonempty_text(settings.bot_name):
            errors.append("봇 이름을 입력해주세요.")

        rooms = settings.rooms if isinstance(settings.rooms, list) else []
        if not isinstance(settings.rooms, list):
            errors.append("채팅방 목록 형식이 올바르지 않습니다.")
        self._validate_named_rows(rooms, "채팅방", errors)

        if not self._nonempty_text(settings.api_key_path):
            errors.append("API 키 파일 경로를 입력해주세요.")
        if not self._nonempty_text(settings.chatroom_settings_path):
            errors.append("채팅방 데이터 파일 경로를 입력해주세요.")

        delay = self._finite_number(settings.every_mention_delay)
        if delay is None or delay < 0:
            errors.append("전체 멘션 기본 지연은 0 이상의 숫자여야 합니다.")

        max_token = self._positive_integer(settings.gpt_max_token)
        if max_token is None:
            errors.append("GPT 최대 토큰은 1 이상의 정수여야 합니다.")

        models = settings.gpt_models if isinstance(settings.gpt_models, list) else []
        if not isinstance(settings.gpt_models, list):
            errors.append("GPT 모델 목록 형식이 올바르지 않습니다.")
        if not models:
            errors.append("GPT 모델을 하나 이상 등록해주세요.")

        model_names: list[str] = []
        for index, model in enumerate(models, start=1):
            if not isinstance(model, GptModel):
                errors.append(f"GPT 모델 {index}행 형식이 올바르지 않습니다.")
                continue
            name = model.name.strip() if isinstance(model.name, str) else ""
            if not name:
                errors.append(f"GPT 모델 {index}행의 모델명을 입력해주세요.")
            else:
                model_names.append(name)
                if self._unsafe_valueless_option(name) or "/" in name:
                    errors.append(
                        f"GPT 모델 '{name}' 이름에 INI 예약문자나 줄바꿈을 사용할 수 없습니다."
                    )
            cost = self._finite_number(model.cost_percent)
            if cost is None or cost < 0:
                errors.append(
                    f"GPT 모델 '{name or index}'의 비용 비율은 0 이상의 숫자여야 합니다."
                )

        duplicates = self._duplicates(model_names)
        if duplicates:
            errors.append(f"중복된 GPT 모델명이 있습니다: {', '.join(duplicates)}")

        default_model = (
            settings.gpt_default_model.strip()
            if isinstance(settings.gpt_default_model, str)
            else ""
        )
        if not default_model:
            errors.append("GPT 기본 모델을 선택해주세요.")
        elif default_model not in model_names:
            errors.append("GPT 기본 모델은 등록된 모델 목록에 있어야 합니다.")

        if not isinstance(settings.gpt_answer_length_limit, str):
            errors.append("GPT 답변 길이 지시문 형식이 올바르지 않습니다.")

        if not self._valid_http_url(settings.radar_base_url):
            errors.append("Radar Base URL은 http 또는 https URL이어야 합니다.")
        if not self._valid_env_name(settings.radar_api_key_env):
            errors.append("Radar API 키 환경변수 이름이 올바르지 않습니다.")

        if not isinstance(settings.github_auto_update, bool):
            errors.append("Git 자동 업데이트 값은 true 또는 false여야 합니다.")
        if not self._nonempty_text(settings.github_branch):
            errors.append("Git 브랜치를 입력해주세요.")

        if not isinstance(settings.feather_enabled, bool):
            errors.append("Feather 모니터 사용 여부는 true 또는 false여야 합니다.")
        if not isinstance(settings.feather_notification_room, str):
            errors.append("Feather 알림 채팅방 형식이 올바르지 않습니다.")
        if not self._valid_filename(settings.feather_log_filename):
            errors.append("Feather 로그 파일명에는 폴더 경로를 사용할 수 없습니다.")

        servers = (
            settings.feather_servers
            if isinstance(settings.feather_servers, list)
            else []
        )
        if not isinstance(settings.feather_servers, list):
            errors.append("Feather 서버 목록 형식이 올바르지 않습니다.")

        server_names: list[str] = []
        server_paths: list[str] = []
        for index, server in enumerate(servers, start=1):
            if not isinstance(server, FeatherServer):
                errors.append(f"Feather 서버 {index}행 형식이 올바르지 않습니다.")
                continue
            name = server.name.strip() if isinstance(server.name, str) else ""
            path = server.path.strip() if isinstance(server.path, str) else ""
            if not name:
                errors.append(f"Feather 서버 {index}행의 이름을 입력해주세요.")
            else:
                server_names.append(name)
                if "," in name or "\n" in name or "\r" in name:
                    errors.append(
                        f"Feather 서버 '{name}' 이름에는 쉼표나 줄바꿈을 사용할 수 없습니다."
                    )
            if not path:
                errors.append(f"Feather 서버 {index}행의 경로를 입력해주세요.")
            else:
                server_paths.append(path)
                if "," in path or "\n" in path or "\r" in path:
                    errors.append(
                        f"Feather 서버 '{name or index}' 경로에는 쉼표나 줄바꿈을 사용할 수 없습니다."
                    )

        duplicate_server_names = self._duplicates(server_names)
        if duplicate_server_names:
            errors.append(
                f"중복된 Feather 서버 이름이 있습니다: {', '.join(duplicate_server_names)}"
            )
        duplicate_server_paths = self._duplicates(server_paths)
        if duplicate_server_paths:
            errors.append(
                f"중복된 Feather 서버 경로가 있습니다: {', '.join(duplicate_server_paths)}"
            )

        if settings.feather_enabled is True:
            notification_room = (
                settings.feather_notification_room.strip()
                if isinstance(settings.feather_notification_room, str)
                else ""
            )
            if not notification_room:
                errors.append("Feather 알림 채팅방을 선택해주세요.")
            elif notification_room not in {
                room.strip() for room in rooms if isinstance(room, str)
            }:
                errors.append("Feather 알림 채팅방은 등록된 채팅방이어야 합니다.")
            if not servers:
                errors.append("Feather 모니터를 사용하려면 서버를 하나 이상 등록해주세요.")

        return errors

    def save(self, settings: BotSettings) -> None:
        """Validate, back up, and atomically replace the INI settings file."""

        errors = self.validate(settings)
        if errors:
            raise ValueError("설정을 저장할 수 없습니다:\n" + "\n".join(errors))

        parser = self._new_parser()
        parser["BotName"] = {"name": self._encode_ini_value(settings.bot_name.strip())}
        parser.add_section("RoomList")
        for room in settings.rooms:
            parser.set("RoomList", room.strip(), None)
        parser["APIKey"] = {"path": self._encode_ini_value(settings.api_key_path.strip())}
        parser["ChattingRoomSetting"] = {
            "path": self._encode_ini_value(settings.chatroom_settings_path.strip())
        }
        parser["EveryMentionDefaultDelayTime"] = {
            "value": self._format_number(settings.every_mention_delay)
        }
        parser["GPT"] = {
            "maxToken": str(int(settings.gpt_max_token)),
            "defaultModel": self._encode_ini_value(settings.gpt_default_model.strip()),
            "answerLengthLimit": self._encode_ini_value(
                settings.gpt_answer_length_limit
            ),
        }
        parser.add_section("GPT_MODEL")
        for model in settings.gpt_models:
            entry = f"{model.name.strip()} / {self._format_number(model.cost_percent)}"
            parser.set("GPT_MODEL", entry, None)
        parser["RADAR"] = {
            "baseUrl": self._encode_ini_value(
                settings.radar_base_url.strip().rstrip("/")
            ),
            "apiKeyEnv": self._encode_ini_value(settings.radar_api_key_env.strip()),
        }
        parser["GitHub"] = {
            "autoUpdate": self._format_bool(settings.github_auto_update),
            "branch": self._encode_ini_value(settings.github_branch.strip()),
        }
        parser["FeatherMonitor"] = {
            "enabled": self._format_bool(settings.feather_enabled),
            "notification_room": self._encode_ini_value(
                settings.feather_notification_room.strip()
            ),
            "log_filename": self._encode_ini_value(
                settings.feather_log_filename.strip()
            ),
            "server_names": self._encode_ini_value(
                ", ".join(server.name.strip() for server in settings.feather_servers)
            ),
            "server_paths": self._encode_ini_value(
                ", ".join(server.path.strip() for server in settings.feather_servers)
            ),
        }

        from io import StringIO

        output = StringIO(newline="\n")
        parser.write(output, space_around_delimiters=True)
        self._backup_existing(self.settings_path)
        self._atomic_write_text(self.settings_path, output.getvalue())
        if not self._api_keys_path_explicit:
            self.api_keys_path = self._absolute_path(settings.api_key_path)

    def load_api_keys(self) -> dict[str, str]:
        """Load API keys as a mapping without writing them to logs or env vars."""

        self.api_key_warnings = []
        if not self.api_keys_path.exists():
            return {}
        try:
            with self.api_keys_path.open("r", encoding="utf-8-sig") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise ValueError(f"API 키 파일을 읽을 수 없습니다: {exc}") from exc

        if isinstance(data, dict):
            entries = list(data.items())
        elif isinstance(data, list):
            entries = []
            for index, item in enumerate(data, start=1):
                if not isinstance(item, dict) or "name" not in item or "key" not in item:
                    raise ValueError(
                        f"API 키 파일의 {index}번째 항목 형식이 올바르지 않습니다."
                    )
                entries.append((item["name"], item["key"]))
        else:
            raise ValueError("API 키 파일의 최상위 값은 목록 또는 객체여야 합니다.")

        result: dict[str, str] = {}
        for raw_name, raw_value in entries:
            if not isinstance(raw_name, str) or not self._valid_env_name(raw_name):
                raise ValueError(f"올바르지 않은 API 키 이름입니다: {raw_name!r}")
            if not isinstance(raw_value, str):
                raise ValueError(f"API 키 '{raw_name}'의 값은 문자열이어야 합니다.")
            if raw_name in result:
                # 기존 로더도 같은 이름을 순서대로 환경변수에 넣어 마지막 값을
                # 사용했다. UI 최초 실행이 막히지 않도록 그 동작을 유지하고 저장
                # 시 하나의 항목으로 정규화한다.
                self.api_key_warnings.append(
                    f"중복된 API 키 '{raw_name}'의 마지막 값을 사용했습니다."
                )
            result[raw_name] = raw_value
        return result

    def save_api_keys(self, mapping: Mapping[str, str]) -> None:
        """Back up and atomically save API keys in the legacy list format."""

        if not isinstance(mapping, Mapping):
            raise ValueError("API 키는 이름과 값의 매핑 형식이어야 합니다.")

        serialized: list[dict[str, str]] = []
        for name, value in mapping.items():
            if not isinstance(name, str) or not self._valid_env_name(name):
                raise ValueError(f"올바르지 않은 API 키 이름입니다: {name!r}")
            if not isinstance(value, str):
                raise ValueError(f"API 키 '{name}'의 값은 문자열이어야 합니다.")
            serialized.append({"name": name, "key": value})

        contents = json.dumps(serialized, ensure_ascii=False, indent=2) + "\n"
        self._backup_existing(self.api_keys_path)
        self._atomic_write_text(self.api_keys_path, contents)

    @staticmethod
    def _new_parser() -> configparser.ConfigParser:
        parser = configparser.ConfigParser(
            allow_no_value=True,
            delimiters=("=",),
            comment_prefixes=("#", ";"),
            inline_comment_prefixes=None,
            interpolation=None,
            strict=False,
            empty_lines_in_values=False,
        )
        parser.optionxform = str
        return parser

    @staticmethod
    def _get(
        parser: configparser.ConfigParser,
        section: str,
        option: str,
        fallback: str,
    ) -> str:
        if not parser.has_section(section):
            return fallback
        value = parser.get(section, option, fallback=fallback, raw=True)
        return fallback if value is None else SettingsManager._decode_ini_value(value.strip())

    @staticmethod
    def _load_rooms(
        parser: configparser.ConfigParser, contents: str | None = None
    ) -> list[str]:
        if not parser.has_section("RoomList"):
            return []
        raw_entries = SettingsManager._valueless_section_entries(contents, "RoomList")
        if raw_entries is not None:
            return raw_entries
        rooms: list[str] = []
        for name, value in parser.items("RoomList", raw=True):
            clean_name = name.strip()
            # Ignore the obsolete ``rooms =`` marker used by an old dist file.
            if clean_name.casefold() == "rooms" and value is not None:
                continue
            if clean_name:
                rooms.append(clean_name)
        return rooms

    @classmethod
    def _load_gpt_models(
        cls,
        parser: configparser.ConfigParser,
        fallback: list[GptModel],
        contents: str | None = None,
    ) -> list[GptModel]:
        if not parser.has_section("GPT_MODEL"):
            return [GptModel(model.name, model.cost_percent) for model in fallback]

        models: list[GptModel] = []
        raw_entries = cls._valueless_section_entries(contents, "GPT_MODEL")
        entries = (
            [(entry, None) for entry in raw_entries]
            if raw_entries is not None
            else list(parser.items("GPT_MODEL", raw=True))
        )
        for entry, value in entries:
            if "/" in entry:
                name, raw_cost = entry.split("/", 1)
            else:
                name = entry
                raw_cost = value if value not in (None, "") else "100"
            clean_name = name.strip()
            if not clean_name:
                continue
            models.append(
                GptModel(
                    clean_name,
                    cls._number_or_raw(str(raw_cost).strip(), float),
                )
            )
        return models

    @staticmethod
    def _load_feather_servers(
        parser: configparser.ConfigParser,
    ) -> list[FeatherServer]:
        if not parser.has_section("FeatherMonitor"):
            return []
        names_raw = parser.get(
            "FeatherMonitor", "server_names", fallback="", raw=True
        )
        paths_raw = parser.get(
            "FeatherMonitor", "server_paths", fallback="", raw=True
        )
        names = SettingsManager._split_csv(names_raw)
        paths = SettingsManager._split_csv(paths_raw)

        servers: list[FeatherServer] = []
        for index in range(max(len(names), len(paths))):
            path = paths[index] if index < len(paths) else ""
            name = names[index] if index < len(names) else ""
            if not name and path:
                name = Path(path).name
            servers.append(FeatherServer(name=name, path=path))
        return servers

    @staticmethod
    def _split_csv(value: str | None) -> list[str]:
        if value is None or not value.strip():
            return []
        return [
            SettingsManager._decode_ini_value(item.strip())
            for item in value.split(",")
        ]

    @staticmethod
    def _valueless_section_entries(
        contents: str | None, section: str
    ) -> list[str] | None:
        """Extract valueless options while retaining duplicates and order."""

        if contents is None:
            return None
        active = False
        found = False
        entries: list[str] = []
        for raw_line in contents.splitlines():
            line = raw_line.strip()
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                if active and current_section != section:
                    break
                active = current_section == section
                found = found or active
                continue
            if not active or not line or line.startswith(("#", ";")):
                continue
            if "=" not in line:
                entries.append(line)
        return entries if found else None

    @staticmethod
    def _number_or_raw(value: str, number_type: type[int] | type[float]):
        try:
            return number_type(value)
        except (TypeError, ValueError):
            # Keeping the raw value lets the UI display it and validate it instead
            # of making a malformed user INI prevent the entire app from opening.
            return value

    @staticmethod
    def _bool_or_raw(value: str):
        normalized = value.strip().casefold()
        if normalized in {"1", "yes", "true", "on"}:
            return True
        if normalized in {"0", "no", "false", "off"}:
            return False
        return value

    @staticmethod
    def _finite_number(value: object) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @classmethod
    def _positive_integer(cls, value: object) -> int | None:
        number = cls._finite_number(value)
        if number is None or number < 1 or not number.is_integer():
            return None
        return int(number)

    @staticmethod
    def _nonempty_text(value: object) -> bool:
        return isinstance(value, str) and bool(value.strip())

    @staticmethod
    def _valid_env_name(value: object) -> bool:
        return isinstance(value, str) and bool(_ENV_NAME_PATTERN.fullmatch(value.strip()))

    @staticmethod
    def _valid_http_url(value: object) -> bool:
        if not isinstance(value, str):
            return False
        parsed = urlparse(value.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _valid_filename(value: object) -> bool:
        if not isinstance(value, str) or not value.strip():
            return False
        clean = value.strip()
        return Path(clean).name == clean and "/" not in clean and "\\" not in clean

    @staticmethod
    def _unsafe_valueless_option(value: str) -> bool:
        return (
            any(character in value for character in ("=", ":", "\n", "\r"))
            or value.startswith(("#", ";"))
            or (value.startswith("[") and value.endswith("]"))
        )

    @classmethod
    def _validate_named_rows(
        cls, values: list[object], label: str, errors: list[str]
    ) -> None:
        clean_values: list[str] = []
        for index, value in enumerate(values, start=1):
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{label} {index}행의 이름을 입력해주세요.")
                continue
            clean = value.strip()
            clean_values.append(clean)
            if cls._unsafe_valueless_option(clean):
                errors.append(
                    f"{label} '{clean}' 이름에 INI 예약문자나 줄바꿈을 사용할 수 없습니다."
                )
        duplicates = cls._duplicates(clean_values)
        if duplicates:
            errors.append(f"중복된 {label} 이름이 있습니다: {', '.join(duplicates)}")

    @staticmethod
    def _duplicates(values: list[str]) -> list[str]:
        seen: set[str] = set()
        duplicates: list[str] = []
        for value in values:
            if value in seen and value not in duplicates:
                duplicates.append(value)
            seen.add(value)
        return duplicates

    @staticmethod
    def _format_bool(value: bool) -> str:
        return "true" if value else "false"

    @staticmethod
    def _format_number(value: object) -> str:
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return format(number, ".15g")

    @staticmethod
    def _encode_ini_value(value: str) -> str:
        # The legacy dataManager uses ConfigParser interpolation.  Escaping
        # percent signs keeps values such as "80%" readable there as well.
        return value.replace("%", "%%")

    @staticmethod
    def _decode_ini_value(value: str) -> str:
        return value.replace("%%", "%")

    @classmethod
    def _backup_existing(cls, path: Path) -> None:
        if path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            cls._atomic_write_bytes(backup_path, path.read_bytes())

    @classmethod
    def _atomic_write_text(cls, path: Path, contents: str) -> None:
        cls._atomic_write_bytes(path, contents.encode("utf-8"))

    @staticmethod
    def _atomic_write_bytes(path: Path, contents: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(contents)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except BaseException:
            try:
                temporary_path.unlink(missing_ok=True)
            finally:
                raise


__all__ = [
    "BotSettings",
    "FeatherServer",
    "GptModel",
    "SettingsManager",
]
