"""User list and per-feature permissions for chat commands.

The rules live in ``config/permissions.json`` (never in the tracked INI) and
are re-read whenever the file changes, so the web UI can edit them while the
bot worker is running.  A missing file means "everything allowed", which keeps
the behaviour of installations that never opened the permission screen.

KakaoTalk only exposes the sender's display name, so every rule here is keyed
by that name.  In open chats anyone can pick any nickname; treat these rules as
a convenience filter, not as authentication.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Callable, Mapping

from Lib import runtime_paths


@dataclass(frozen=True)
class Feature:
    """One user-facing bot feature and the chat command keys that trigger it."""

    id: str
    label: str
    commands: tuple[str, ...]


# Keep in sync with ``dataManager.chat_command_Map``; a test enforces that every
# registered command key belongs to exactly one feature.
FEATURES: tuple[Feature, ...] = (
    Feature("help", "명령어 도움말 (#command, #?)", ("#?", "#command")),
    Feature("youtube", "유튜브 검색 (#유툽)", ("#유툽",)),
    Feature("kakaomap", "카카오맵 → 네이버지도 변환", ("[카카오맵]",)),
    Feature("mention_all", "전체 멘션 (#all)", ("#all",)),
    Feature("member_count", "방 인원 설정 (#방인원)", ("#방인원",)),
    Feature("gpt_model_change", "GPT 모델 변경 (#model)", ("#model",)),
    Feature("gpt_model_check", "GPT 모델 확인 (#modelcheck)", ("#modelcheck",)),
    Feature("gpt", "GPT 질문 (#gpt)", ("#gpt",)),
    Feature("usage", "API 사용량 확인 (#사용량확인)", ("#사용량확인",)),
    Feature("radar", "게임위키 AI (#radar)", ("#radar",)),
    Feature(
        "instagram",
        "인스타그램 링크 요약",
        ("https://www.instagram.com/", "https://instagram.com/"),
    ),
    Feature("random_pick", "랜덤 선택 (A vs B)", ("vs",)),
    Feature("tts", "음성 읽어주기 (#tts)", ("#tts",)),
    Feature("sound_effect", "배경음악 만들기 (#bgm)", ("#bgm",)),
    # #스프라이트도 같은 PixelLab 계정의 생성 횟수를 쓰므로 같은 권한으로 묶는다
    Feature("pixel_art", "픽셀아트 그리기 (#픽셀, #스프라이트)", ("#픽셀", "#pxicel", "#pixel", "#스프라이트", "#sprite")),
    Feature("image_gen", "AI 그림 그리기 (#지피티이미지)", ("#지피티이미지", "#이미지피티", "#imagegen")),
    Feature("minecraft", "마크 서버 접속자 확인 (#마크)", ("#마크",)),
)
_FEATURE_BY_ID = {feature.id: feature for feature in FEATURES}
_FEATURE_BY_COMMAND = {
    command: feature for feature in FEATURES for command in feature.commands
}

ROLES = ("admin", "user", "blocked")
LEVELS = ("everyone", "user", "admin")
UNREGISTERED_POLICIES = ("allow", "deny")

MAX_NAME_LENGTH = 100
MAX_MEMO_LENGTH = 200
MAX_DENY_MESSAGE_LENGTH = 500
MAX_SEEN_USERS = 1000
DENY_REPLY_COOLDOWN_SECONDS = 60.0
SEEN_FLUSH_INTERVAL_SECONDS = 60.0


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""
    reply: str | None = None


def feature_for_command(command_key: str) -> Feature:
    """Return the feature owning *command_key* (an ad-hoc one when unknown)."""

    feature = _FEATURE_BY_COMMAND.get(command_key)
    if feature is not None:
        return feature
    return Feature(command_key, command_key, (command_key,))


def default_rule() -> dict[str, Any]:
    return {"enabled": True, "level": "everyone", "rooms": []}


def default_permissions() -> dict[str, Any]:
    return {
        "version": 1,
        "unregistered_policy": "allow",
        "deny_message": "",
        "users": [],
        "features": {feature.id: default_rule() for feature in FEATURES},
    }


def validate_permissions(data: Any) -> tuple[dict[str, Any], list[str]]:
    """Return ``(normalized, errors)`` for user-supplied permission data.

    Unknown feature ids are dropped, missing features get the permissive
    default rule, and every string is stripped.  The normalized value is only
    meaningful when ``errors`` is empty.
    """

    errors: list[str] = []
    result = default_permissions()
    if not isinstance(data, Mapping):
        return result, ["권한 설정은 JSON 객체여야 합니다."]

    policy = data.get("unregistered_policy", "allow")
    if policy not in UNREGISTERED_POLICIES:
        errors.append("미등록 사용자 정책은 allow 또는 deny여야 합니다.")
    else:
        result["unregistered_policy"] = policy

    deny_message = data.get("deny_message", "")
    if not isinstance(deny_message, str):
        errors.append("거부 안내 메시지는 문자열이어야 합니다.")
    elif len(deny_message.strip()) > MAX_DENY_MESSAGE_LENGTH:
        errors.append(f"거부 안내 메시지는 {MAX_DENY_MESSAGE_LENGTH}자 이하여야 합니다.")
    else:
        result["deny_message"] = deny_message.strip()

    users = data.get("users", [])
    if not isinstance(users, list):
        errors.append("사용자 목록은 배열이어야 합니다.")
        users = []
    seen_names: set[str] = set()
    for index, user in enumerate(users, start=1):
        if not isinstance(user, Mapping):
            errors.append(f"사용자 {index}번 항목 형식이 올바르지 않습니다.")
            continue
        name = user.get("name")
        name = name.strip() if isinstance(name, str) else ""
        role = user.get("role", "user")
        memo = user.get("memo", "")
        memo = memo.strip() if isinstance(memo, str) else ""
        if not name:
            errors.append(f"사용자 {index}번의 이름이 비어 있습니다.")
            continue
        if len(name) > MAX_NAME_LENGTH:
            errors.append(f"사용자 '{name[:20]}…' 이름이 너무 깁니다.")
            continue
        if name in seen_names:
            errors.append(f"사용자 '{name}'이(가) 중복되었습니다.")
            continue
        if role not in ROLES:
            errors.append(f"사용자 '{name}'의 역할이 올바르지 않습니다: {role}")
            continue
        seen_names.add(name)
        result["users"].append(
            {"name": name, "role": role, "memo": memo[:MAX_MEMO_LENGTH]}
        )

    features = data.get("features", {})
    if not isinstance(features, Mapping):
        errors.append("기능 설정은 객체여야 합니다.")
        features = {}
    for feature_id, rule in features.items():
        if feature_id not in _FEATURE_BY_ID:
            continue
        label = _FEATURE_BY_ID[feature_id].label
        if not isinstance(rule, Mapping):
            errors.append(f"'{label}' 설정 형식이 올바르지 않습니다.")
            continue
        enabled = rule.get("enabled", True)
        level = rule.get("level", "everyone")
        rooms = rule.get("rooms", [])
        if not isinstance(enabled, bool):
            errors.append(f"'{label}' 사용 여부는 true/false여야 합니다.")
            continue
        if level not in LEVELS:
            errors.append(f"'{label}' 사용 권한이 올바르지 않습니다: {level}")
            continue
        if not isinstance(rooms, list) or not all(isinstance(r, str) for r in rooms):
            errors.append(f"'{label}' 허용 방 목록은 문자열 배열이어야 합니다.")
            continue
        clean_rooms = list(dict.fromkeys(r.strip() for r in rooms if r.strip()))
        result["features"][feature_id] = {
            "enabled": enabled,
            "level": level,
            "rooms": clean_rooms,
        }

    return result, errors


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


class AccessControl:
    """Evaluate permissions and remember who has been talking to the bot."""

    def __init__(
        self,
        permissions_path: str | os.PathLike[str] | None = None,
        seen_users_path: str | os.PathLike[str] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        log: Callable[[str], Any] | None = None,
    ) -> None:
        self.permissions_path = Path(
            permissions_path if permissions_path is not None else runtime_paths.PERMISSIONS_FILE
        )
        self.seen_users_path = Path(
            seen_users_path if seen_users_path is not None else runtime_paths.SEEN_USERS_FILE
        )
        self._clock = clock
        self._log = log or (lambda _message: None)
        self._lock = threading.RLock()

        self._cache: dict[str, Any] | None = None
        self._cache_key: tuple[int, int] | None = None
        self._load_failed = False
        self._last_reply: dict[tuple[str, str, str], float] = {}

        self._seen: dict[str, dict[str, Any]] | None = None
        self._seen_dirty = False
        self._seen_last_flush = 0.0

    # Permission file ------------------------------------------------------------------
    def load(self) -> dict[str, Any]:
        """Return the current rules, re-reading the file only when it changed.

        A broken file keeps the last good rules.  If no rules were ever loaded,
        every command is denied (fail closed) rather than silently re-opening
        features an administrator restricted.
        """

        with self._lock:
            try:
                stat = self.permissions_path.stat()
            except FileNotFoundError:
                self._cache = default_permissions()
                self._cache_key = None
                self._load_failed = False
                return copy.deepcopy(self._cache)

            key = (stat.st_mtime_ns, stat.st_size)
            if self._cache is not None and key == self._cache_key:
                return copy.deepcopy(self._cache)

            try:
                with self.permissions_path.open("r", encoding="utf-8-sig") as handle:
                    raw = json.load(handle)
                normalized, errors = validate_permissions(raw)
                if errors:
                    raise ValueError("; ".join(errors))
            except (OSError, ValueError) as exc:
                if not self._load_failed:
                    self._log(f"❌ 권한 설정 파일을 읽을 수 없습니다 ({self.permissions_path}): {exc}")
                self._load_failed = True
                self._cache_key = key
                if self._cache is None:
                    self._cache = {**default_permissions(), "_broken": True}
                return copy.deepcopy(self._cache)

            self._cache = normalized
            self._cache_key = key
            if self._load_failed:
                self._log("✅ 권한 설정 파일을 다시 읽었습니다.")
            self._load_failed = False
            return copy.deepcopy(normalized)

    def save(self, data: Any) -> dict[str, Any]:
        """Validate and atomically persist *data*; raise ``ValueError`` on errors."""

        normalized, errors = validate_permissions(data)
        if errors:
            raise ValueError("\n".join(errors))
        with self._lock:
            _atomic_write_json(self.permissions_path, normalized)
            self._cache = None
            self._cache_key = None
        return normalized

    # Evaluation -----------------------------------------------------------------------
    def check(self, room: str, sender: str, command_key: str) -> Decision:
        rules = self.load()
        if rules.get("_broken"):
            return Decision(False, "권한 설정 파일 오류")

        feature = feature_for_command(command_key)
        rule = rules["features"].get(feature.id, default_rule())
        sender = (sender or "").strip()
        role = next(
            (user["role"] for user in rules["users"] if user["name"] == sender),
            None,
        )

        if not rule["enabled"]:
            return Decision(False, "기능 꺼짐")
        if rule["rooms"] and room not in rule["rooms"]:
            return Decision(False, "허용되지 않은 방")
        if role == "blocked":
            return Decision(False, "차단된 사용자")
        if role == "admin":
            return Decision(True)

        if rule["level"] == "admin":
            return self._deny_with_reply(rules, room, sender, feature, "관리자 전용")
        if rule["level"] == "user" and role != "user":
            return self._deny_with_reply(rules, room, sender, feature, "등록 사용자 전용")
        if role is None and rules["unregistered_policy"] == "deny":
            return self._deny_with_reply(rules, room, sender, feature, "미등록 사용자")
        return Decision(True)

    def _deny_with_reply(
        self,
        rules: Mapping[str, Any],
        room: str,
        sender: str,
        feature: Feature,
        reason: str,
    ) -> Decision:
        message = rules.get("deny_message") or None
        if message is None:
            return Decision(False, reason)
        key = (room, sender, feature.id)
        now = self._clock()
        with self._lock:
            last = self._last_reply.get(key)
            if last is not None and now - last < DENY_REPLY_COOLDOWN_SECONDS:
                return Decision(False, reason)
            self._last_reply[key] = now
        return Decision(False, reason, message)

    # Seen senders ---------------------------------------------------------------------
    def record_sender(self, room: str, name: str) -> None:
        """Remember that *name* spoke in *room* so the UI can offer to register them."""

        name = (name or "").strip()
        if not name:
            return
        now_text = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._lock:
            seen = self._load_seen()
            entry = seen.get(name)
            if entry is None:
                entry = {"name": name, "rooms": [], "last_seen": now_text, "count": 0}
                seen[name] = entry
                self._seen_dirty = True
                flush_now = True
            else:
                flush_now = False
            if room and room not in entry["rooms"]:
                entry["rooms"].append(room)
                flush_now = True
            entry["last_seen"] = now_text
            entry["count"] = int(entry.get("count", 0)) + 1
            self._seen_dirty = True
            if flush_now or self._clock() - self._seen_last_flush >= SEEN_FLUSH_INTERVAL_SECONDS:
                self.flush_seen()

    def flush_seen(self) -> None:
        with self._lock:
            if not self._seen_dirty or self._seen is None:
                return
            entries = sorted(self._seen.values(), key=lambda e: e["last_seen"], reverse=True)
            entries = entries[:MAX_SEEN_USERS]
            self._seen = {entry["name"]: entry for entry in entries}
            try:
                _atomic_write_json(self.seen_users_path, entries)
            except OSError as exc:
                self._log(f"⚠️ 대화 사용자 목록 저장 실패: {exc}")
                return
            self._seen_dirty = False
            self._seen_last_flush = self._clock()

    def seen_users(self) -> list[dict[str, Any]]:
        """Read the seen-users file fresh (it is written by the worker process)."""

        entries = self._read_seen_file()
        return sorted(entries.values(), key=lambda e: e["last_seen"], reverse=True)

    def _load_seen(self) -> dict[str, dict[str, Any]]:
        if self._seen is None:
            self._seen = self._read_seen_file()
        return self._seen

    def _read_seen_file(self) -> dict[str, dict[str, Any]]:
        try:
            with self.seen_users_path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            return {}
        result: dict[str, dict[str, Any]] = {}
        if not isinstance(raw, list):
            return result
        for item in raw:
            if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
                continue
            rooms = item.get("rooms", [])
            result[item["name"]] = {
                "name": item["name"],
                "rooms": [r for r in rooms if isinstance(r, str)] if isinstance(rooms, list) else [],
                "last_seen": str(item.get("last_seen", "")),
                "count": int(item.get("count", 0)) if str(item.get("count", "0")).isdigit() else 0,
            }
        return result


_default_instance: AccessControl | None = None
_default_lock = threading.Lock()


def get_default() -> AccessControl:
    """Process-wide instance used by the chat worker."""

    global _default_instance
    with _default_lock:
        if _default_instance is None:
            try:
                from Lib import Helper

                log = Helper.CustomPrint
            except Exception:
                log = None
            _default_instance = AccessControl(log=log)
        return _default_instance


__all__ = [
    "Decision",
    "Feature",
    "FEATURES",
    "ROLES",
    "LEVELS",
    "AccessControl",
    "default_permissions",
    "default_rule",
    "feature_for_command",
    "get_default",
    "validate_permissions",
]
