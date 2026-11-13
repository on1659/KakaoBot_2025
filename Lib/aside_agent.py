# -*- coding: utf-8 -*-
"""
Aside(AI 브라우저)의 에이전트에게 채팅으로 그림을 부탁하고, 만들어진 이미지 파일을 받아온다.

Aside CLI(`aside exec --json "<요청>"`)가 Aside 앱에 새 채팅(세션)을 열어 요청을 보내고,
끝나면 {"session": {"id"}, "outcome", "answer", "error"} JSON을 표준 출력으로 돌려준다.
요청문에서 "이미지 파일 경로를 IMAGE_PATH: <경로> 한 줄로 답해라"라고 시키고 그 파일을 읽는다.

주의 — 채팅방 사용자의 글이 '내 계정으로 로그인된 브라우저를 다루는 에이전트'에게 들어간다.
그래서 다음을 지킨다.
- 사용자 글은 한 줄로 줄이고 꺾쇠를 없앤 뒤 <설명> 칸에만 넣고, 그 안의 지시는 따르지 말라고 못박는다.
- 에이전트의 글 답변은 방에 그대로 전달하지 않는다 (경로와 정해진 오류 코드만 해석한다).
- 받은 경로는 Aside 데이터 폴더 안에서 이번 요청 이후에 만들어진 이미지 파일일 때만 쓴다.
이건 완화책이지 차단이 아니다. 이 기능을 쓸 수 있는 방·사람은 기능 권한에서 좁게 잡는 것이 안전하다.

CLI 위치는 ASIDE_CLI_PATH(config/api_key.json 항목)로 지정할 수 있고, 없으면 기본 설치 위치를 찾는다.
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from Lib import Helper

MAX_DESCRIPTION_CHARS = 300
MAX_IMAGE_BYTES = 30 * 1024 * 1024
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
EXTRA_WAIT_SEC = 20            # CLI가 스스로 --timeout으로 끝낼 여유
STOP_TIMEOUT_SEC = 15

MSG_NO_CLI = (
    "Aside CLI를 찾지 못했습니다. Aside 앱의 설정 > Developers에서 CLI를 설치해주세요."
)
MSG_BUSY = "Aside가 다른 그림을 만드는 중입니다. 끝난 뒤 다시 시도해주세요."
MSG_TIMEOUT = "Aside가 시간 안에 그림을 끝내지 못했습니다. 잠시 후 다시 시도해주세요."
MSG_FAILED = "Aside가 그림을 만들지 못했습니다. (Aside 앱이 켜져 있고 로그인돼 있는지 확인해주세요)"
MSG_NO_IMAGE = "Aside가 그림 파일을 돌려주지 않았습니다. 다시 시도해주세요."
MSG_BAD_IMAGE = "Aside가 만든 그림을 읽지 못했습니다. 다시 시도해주세요."

# 에이전트가 'ERROR: <코드>'로 답하면 정해진 안내문으로만 바꿔 전달한다
ERROR_MESSAGES = {
    "POLICY": "안전 정책에 걸려 이 그림은 만들 수 없습니다. 내용을 바꿔서 다시 시도해주세요.",
    "LOGIN": "Aside 브라우저에서 해당 사이트에 로그인이 필요합니다. 관리자에게 문의해주세요.",
    "CREDITS": "그림 생성 크레딧이 부족합니다. 관리자에게 문의해주세요.",
}

_PATH_LINE = re.compile(r"IMAGE_PATH:\s*(.+)")
_ERROR_LINE = re.compile(r"ERROR:\s*([A-Z_]+)")
_lock = threading.Lock()  # Aside 작업은 한 번에 하나만 (같은 브라우저를 쓴다)


def find_cli():
    """aside 실행 파일 경로. 없으면 None."""
    candidates = [os.environ.get("ASIDE_CLI_PATH", "").strip()]
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        candidates.append(os.path.join(local_app_data, "Aside", "CLI", "current", "aside.exe"))
    home = Path.home()
    candidates.append(str(home / ".aside" / "bin" / "aside.exe"))
    candidates.append(str(home / ".local" / "bin" / "aside.exe"))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return shutil.which("aside")


def data_dir():
    """Aside가 세션 결과물을 두는 폴더 (기본 ~/.aside)."""
    return Path(os.environ.get("ASIDE_DATA_DIR", "").strip() or Path.home() / ".aside")


def clean_description(text):
    """사용자 글을 요청문에 넣기 좋게 다듬는다: 한 줄, 꺾쇠 제거, 길이 제한."""
    text = (text or "").replace("<", " ").replace(">", " ")
    return " ".join(text.split())[:MAX_DESCRIPTION_CHARS].strip()


def _run_cli(arguments, timeout):
    return subprocess.run(
        arguments,
        stdin=subprocess.DEVNULL,   # UI→워커 제어 파이프를 물려받으면 하위 프로세스가 멈춘다
        capture_output=True,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _stop_session(cli, session_id):
    """--timeout이 지나도 세션은 계속 돈다 — 크레딧이 더 나가지 않게 멈춘다."""
    if not session_id:
        return
    try:
        _run_cli([cli, "session", "stop", session_id], STOP_TIMEOUT_SEC)
    except Exception as e:
        Helper.CustomPrint(f"⚠️ [aside] 세션 중지 실패 ({session_id}): {e}")


def _parse_result(stdout):
    text = (stdout or b"").decode("utf-8", errors="replace").strip()
    if not text:
        return None
    try:
        result = json.loads(text.splitlines()[-1])
    except ValueError:
        return None
    return result if isinstance(result, dict) else None


def _session_id(result):
    session = (result or {}).get("session")
    return session.get("id") if isinstance(session, dict) else None


def _image_from_answer(answer, started_at):
    """답변에서 이미지 경로를 꺼내 검증하고 바이트를 읽는다. 반환: (bytes, None) 또는 (None, 안내문)."""
    match = _PATH_LINE.search(answer or "")
    if not match:
        return None, MSG_NO_IMAGE
    raw = match.group(1).strip().strip("`'\"").strip()
    try:
        path = Path(raw).resolve()
        root = data_dir().resolve()
        inside = root == path or root in path.parents
        if not inside or path.suffix.lower() not in IMAGE_SUFFIXES or not path.is_file():
            Helper.CustomPrint(f"❌ [aside] 받을 수 없는 경로를 돌려줌: {raw[:200]}")
            return None, MSG_NO_IMAGE
        stat = path.stat()
        if stat.st_mtime < started_at - 5 or not 0 < stat.st_size <= MAX_IMAGE_BYTES:
            Helper.CustomPrint(f"❌ [aside] 이번 요청의 결과물이 아닌 파일: {raw[:200]}")
            return None, MSG_NO_IMAGE
        return path.read_bytes(), None
    except OSError as e:
        Helper.CustomPrint(f"❌ [aside] 결과 파일 읽기 실패: {e}")
        return None, MSG_BAD_IMAGE


def _exec(prompt, timeout_sec, effort=None, model=None):
    """
    Aside CLI로 요청 하나를 끝까지 돌린다 (한 번에 하나).
    반환: (답변 문자열, None, 시작 시각) 또는 (None, 안내문, 시작 시각).
    """
    started_at = time.time()
    cli = find_cli()
    if not cli:
        return None, MSG_NO_CLI, started_at
    if not _lock.acquire(blocking=False):
        return None, MSG_BUSY, started_at
    try:
        arguments = [cli, "exec", "--json", "--timeout", f"{int(timeout_sec)}s"]
        if effort:
            arguments += ["--effort", effort]
        if model:
            arguments += ["--model", model]
        arguments.append(prompt)

        started_at = time.time()
        try:
            completed = _run_cli(arguments, timeout_sec + EXTRA_WAIT_SEC)
        except subprocess.TimeoutExpired as e:
            Helper.CustomPrint("❌ [aside] CLI가 응답하지 않아 중단했습니다.")
            _stop_session(cli, _session_id(_parse_result(e.stdout)))
            return None, MSG_TIMEOUT, started_at
        except OSError as e:
            Helper.CustomPrint(f"❌ [aside] CLI 실행 실패: {e}")
            return None, MSG_FAILED, started_at

        result = _parse_result(completed.stdout)
        elapsed = time.time() - started_at
        if result is None or result.get("outcome") != "completed":
            detail = (completed.stderr or b"").decode("utf-8", errors="replace").strip()[-300:]
            Helper.CustomPrint(
                f"❌ [aside] 실패 (exit={completed.returncode}, outcome={(result or {}).get('outcome')!r}, "
                f"error={str((result or {}).get('error'))[:200]!r}, {elapsed:.0f}s) {detail}"
            )
            if elapsed >= timeout_sec - 1:
                _stop_session(cli, _session_id(result))
                return None, MSG_TIMEOUT, started_at
            return None, MSG_FAILED, started_at
        return str(result.get("answer") or ""), None, started_at
    finally:
        _lock.release()


def request_text(prompt, timeout_sec, effort=None, model=None):
    """Aside 에이전트에게 prompt를 보내고 글 답변을 받는다. 반환: (답변, None) 또는 (None, 안내문)."""
    answer, error, started_at = _exec(prompt, timeout_sec, effort=effort, model=model)
    if answer is not None:
        Helper.CustomPrint(f"✅ [aside] 답변 수신 ({len(answer)}자, {time.time() - started_at:.0f}s)")
    return answer, error


def request_image(prompt, timeout_sec, effort=None):
    """
    Aside 에이전트에게 prompt를 보내고 결과 이미지 바이트를 받는다.
    반환: (이미지 바이트, None) 또는 (None, 안내문).
    """
    answer, failure, started_at = _exec(prompt, timeout_sec, effort=effort)
    if failure:
        return None, failure

    error = _ERROR_LINE.search(answer)
    if error and not _PATH_LINE.search(answer):
        Helper.CustomPrint(f"❌ [aside] 에이전트가 오류로 답함: {answer[:200]}")
        return None, ERROR_MESSAGES.get(error.group(1), MSG_FAILED)

    image, message = _image_from_answer(answer, started_at)
    if image is not None:
        Helper.CustomPrint(f"✅ [aside] 그림 수신 ({len(image)} bytes, {time.time() - started_at:.0f}s)")
    return image, message
