"""Runtime data paths shared by source and packaged KakaoBot builds.

The application must never depend on the current working directory.  In a
source checkout data lives beside ``main.py``; in a frozen build it lives
beside the executable.  ``KAKAOBOT_DATA_DIR`` can be used to put writable
data somewhere else (and is especially useful for tests and portable builds).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Union


PathLike = Union[str, os.PathLike[str]]


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _application_root() -> Path:
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


PROJECT_ROOT = _application_root()


def _data_root() -> Path:
    override = os.environ.get("KAKAOBOT_DATA_DIR", "").strip()
    if not override:
        return PROJECT_ROOT

    candidate = Path(override).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


DATA_DIR = _data_root()
CONFIG_DIR = DATA_DIR / "config"
SAVED_DIR = DATA_DIR / "saved"

SETTINGS_FILE = CONFIG_DIR / "DefaultSetting.ini"
API_KEYS_FILE = CONFIG_DIR / "api_key.json"
CHATROOMS_FILE = CONFIG_DIR / "chatrooms.json"
API_USAGE_FILE = CONFIG_DIR / "api_usage.json"
PERMISSIONS_FILE = CONFIG_DIR / "permissions.json"
SEEN_USERS_FILE = SAVED_DIR / "seen_users.json"
YOUTUBE_TOKEN_FILE = DATA_DIR / "token.pickle"
YOUTUBE_CLIENT_SECRETS_FILE = CONFIG_DIR / "youtube_client_secrets.json"
INSTAGRAM_SESSION_DIR = SAVED_DIR / "instagram"
INSTAGRAM_ERROR_LOG_FILE = SAVED_DIR / "instagram_errors.log"


def resolve_data_path(path: PathLike) -> Path:
    """Return *path* as an absolute path under :data:`DATA_DIR`.

    Absolute paths are preserved.  Relative paths from the legacy INI file
    (for example ``config/api_key.json``) are resolved below the writable
    runtime data directory, independent of the process CWD.
    """

    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (DATA_DIR / candidate).resolve()


def _bundled_settings_template() -> Path | None:
    """Locate the read-only settings template embedded by PyInstaller."""

    bundle_root_value = getattr(sys, "_MEIPASS", None)
    if not bundle_root_value:
        return None

    bundle_root = Path(bundle_root_value)
    candidates = (
        bundle_root / "config" / "DefaultSetting.template.ini",
        bundle_root / "config" / SETTINGS_FILE.name,
        bundle_root / "DefaultSetting.template.ini",
        bundle_root / SETTINGS_FILE.name,
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def ensure_runtime_layout() -> None:
    """Create writable runtime folders and seed frozen settings once.

    User settings are never overwritten.  The template copy only applies to
    frozen builds because source checkouts already contain the canonical INI.
    Secret-bearing files are deliberately not created or copied here.
    """

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SAVED_DIR.mkdir(parents=True, exist_ok=True)
    INSTAGRAM_SESSION_DIR.mkdir(parents=True, exist_ok=True)

    if _is_frozen() and not SETTINGS_FILE.exists():
        template = _bundled_settings_template()
        if template is not None:
            shutil.copy2(template, SETTINGS_FILE)


__all__ = [
    "PROJECT_ROOT",
    "DATA_DIR",
    "CONFIG_DIR",
    "SAVED_DIR",
    "SETTINGS_FILE",
    "API_KEYS_FILE",
    "CHATROOMS_FILE",
    "API_USAGE_FILE",
    "PERMISSIONS_FILE",
    "SEEN_USERS_FILE",
    "YOUTUBE_TOKEN_FILE",
    "YOUTUBE_CLIENT_SECRETS_FILE",
    "INSTAGRAM_SESSION_DIR",
    "INSTAGRAM_ERROR_LOG_FILE",
    "resolve_data_path",
    "ensure_runtime_layout",
]
