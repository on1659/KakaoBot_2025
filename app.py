"""KakaoBot desktop entry point and hidden worker mode."""

from __future__ import annotations

import argparse
import faulthandler
import json
import os
import sys
import threading
from typing import TextIO


WORKER_EVENT_PREFIX = "@@KAKAOBOT_EVENT@@"
# 시작이 이 시간 안에 끝나지 않으면 모든 스레드의 스택을 로그로 남긴다 (멈춤 진단용).
STARTUP_STACK_DUMP_SECONDS = 120


def _restore_worker_streams() -> None:
    """Restore piped stdio for a PyInstaller windowed child process.

    A windowed PyInstaller executable normally sets ``sys.std*`` to ``None``.
    The UI launches worker mode with real pipe handles, so binding file
    descriptors 0 and 1 lets the same executable use a private text protocol
    without opening a console window.
    """

    if sys.stdin is None:
        try:
            sys.stdin = os.fdopen(0, "r", encoding="utf-8", errors="replace", closefd=False)
        except OSError:
            pass
    if sys.stdout is None:
        try:
            sys.stdout = os.fdopen(1, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)
        except OSError:
            pass
    if sys.stderr is None:
        sys.stderr = sys.stdout


def _write_event(event: dict) -> None:
    stream: TextIO | None = sys.stdout
    if stream is None:
        return
    try:
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        stream.write(WORKER_EVENT_PREFIX + payload + "\n")
        stream.flush()
    except (BrokenPipeError, OSError, ValueError):
        pass


def _detach_control_stdin() -> TextIO | None:
    """Move the UI control pipe off the process standard-input handle.

    The control reader keeps a blocking read pending on that pipe.  On Windows
    every child that inherits it as stdin (``git``, KakaoTalk launch, ...) can
    freeze while initializing, because operations on a synchronous pipe wait
    behind the pending read.  Children now inherit NUL instead, and the pipe is
    read through a private, non-inheritable duplicate.
    """

    if sys.platform != "win32" or sys.stdin is None:
        return sys.stdin
    try:
        control = os.fdopen(os.dup(0), "r", encoding="utf-8", errors="replace")
        null_fd = os.open(os.devnull, os.O_RDONLY)
        try:
            os.dup2(null_fd, 0)
        finally:
            os.close(null_fd)
        import ctypes
        import msvcrt

        STD_INPUT_HANDLE = -10
        ctypes.windll.kernel32.SetStdHandle(STD_INPUT_HANDLE, msvcrt.get_osfhandle(0))
        sys.stdin = os.fdopen(0, "r", encoding="utf-8", errors="replace", closefd=False)
        return control
    except (OSError, ValueError):
        return sys.stdin


def _read_worker_commands(stop_event, pause_event, stream: TextIO | None = None) -> None:
    if stream is None:
        stream = sys.stdin
    if stream is None:
        stop_event.set()
        return
    try:
        for raw_line in stream:
            command = raw_line.strip().lower()
            if command == "pause":
                pause_event.set()
            elif command == "resume":
                pause_event.clear()
            elif command in {"stop", "quit", "exit"}:
                stop_event.set()
                return
    except (OSError, ValueError):
        pass
    finally:
        # The UI pipe closing means its owning process is gone.
        stop_event.set()


def worker_main() -> int:
    _restore_worker_streams()

    from Lib.bot_engine import BotEngine
    from Lib.runtime_paths import ensure_runtime_layout

    ensure_runtime_layout()
    control_stream = _detach_control_stdin()
    stop_event = threading.Event()
    pause_event = threading.Event()
    command_reader = threading.Thread(
        target=_read_worker_commands,
        args=(stop_event, pause_event, control_stream),
        name="ui-control-reader",
        daemon=True,
    )
    command_reader.start()

    try:
        # Preserve the source-checkout update behavior; main.check_and_update
        # itself always skips Git in a frozen executable.
        from main import check_and_update

        _arm_startup_stack_dump()
        check_and_update()
        engine = BotEngine(event_callback=_startup_aware_event_callback)
        engine.run(stop_event=stop_event, pause_event=pause_event)
        return 0 if engine.state == "stopped" else 1
    except SystemExit as exc:
        return int(exc.code or 0)
    except BaseException as exc:
        _write_event(
            {
                "type": "engine_status",
                "status": "error",
                "message": f"워커 시작에 실패했습니다: {exc}",
                "error": repr(exc),
            }
        )
        return 1
    finally:
        _disarm_startup_stack_dump()
        stop_event.set()


def _arm_startup_stack_dump() -> None:
    """Dump every thread's stack to the log if startup stalls.

    Uses faulthandler's C watchdog thread, so it still fires when the main
    thread is stuck inside a blocking native call.
    """

    try:
        faulthandler.dump_traceback_later(STARTUP_STACK_DUMP_SECONDS, file=sys.stdout)
    except (AttributeError, OSError, ValueError, RuntimeError):
        pass


def _disarm_startup_stack_dump() -> None:
    faulthandler.cancel_dump_traceback_later()


def _startup_aware_event_callback(event: dict) -> None:
    if event.get("type") == "engine_status" and event.get("status") in {"running", "stopped", "error"}:
        _disarm_startup_stack_dump()
    _write_event(event)


def self_check() -> int:
    """Validate packaged resources and settings without starting KakaoTalk."""

    from Lib.runtime_paths import ensure_runtime_layout
    from Lib.settings_manager import SettingsManager

    ensure_runtime_layout()
    manager = SettingsManager()
    try:
        settings = manager.load()
        errors = manager.validate(settings)
        manager.load_api_keys()
    except Exception as exc:
        errors = [str(exc)]

    result = {"ok": not errors, "errors": errors}
    if sys.stdout is not None:
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if not errors else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--web", action="store_true", help="브라우저용 관리 화면으로 실행")
    parser.add_argument("--host", default=None, help="웹 서버 주소 (기본 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="웹 서버 포트 (기본 8765)")
    parser.add_argument(
        "--password",
        default=None,
        help="외부 접속용 비밀번호 (환경변수 KAKAOBOT_WEB_PASSWORD로도 지정 가능)",
    )
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    parser.add_argument("--autostart", action="store_true", help="웹 서버와 함께 봇도 바로 시작")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.worker:
        return worker_main()
    if args.self_check:
        _restore_worker_streams()
        return self_check()
    if args.web:
        _restore_worker_streams()
        from Lib import web_ui

        return web_ui.run_web(
            host=args.host or web_ui.DEFAULT_HOST,
            port=args.port or web_ui.DEFAULT_PORT,
            password=args.password or os.environ.get("KAKAOBOT_WEB_PASSWORD") or None,
            open_browser=not args.no_browser,
            autostart=args.autostart,
        )

    from Lib.desktop_ui import launch_desktop_app

    launch_desktop_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
