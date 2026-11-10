from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from Lib import desktop_ui


def test_decode_worker_line_handles_event_and_log():
    event = {"type": "engine_status", "status": "running", "message": "ok"}
    line = desktop_ui.WORKER_EVENT_PREFIX + json.dumps(event)

    assert desktop_ui.decode_worker_line(line) == ("event", event)
    assert desktop_ui.decode_worker_line("plain log\n") == ("log", "plain log")


def test_decode_worker_line_treats_malformed_event_as_log():
    line = desktop_ui.WORKER_EVENT_PREFIX + "{broken"
    assert desktop_ui.decode_worker_line(line) == ("log", line)


def test_build_worker_command_source(monkeypatch):
    monkeypatch.delattr(desktop_ui.sys, "frozen", raising=False)
    command = desktop_ui.build_worker_command()

    assert command[0] == sys.executable
    assert command[-1] == "--worker"
    assert command[-2].endswith("app.py")


def test_build_worker_command_frozen(monkeypatch):
    monkeypatch.setattr(desktop_ui.sys, "frozen", True, raising=False)
    monkeypatch.setattr(desktop_ui.sys, "executable", r"C:\Apps\KakaoBot.exe")

    assert desktop_ui.build_worker_command() == [r"C:\Apps\KakaoBot.exe", "--worker"]


def test_worker_controller_reads_structured_event_and_plain_log():
    events = []
    logs = []
    exit_codes = []
    finished = threading.Event()
    payload = {"type": "engine_status", "status": "running", "message": "ready"}
    child_code = (
        "import json; "
        f"print({desktop_ui.WORKER_EVENT_PREFIX!r} + json.dumps({payload!r})); "
        "print('plain-child-log')"
    )

    controller = desktop_ui.WorkerController(
        event_sink=events.append,
        log_sink=logs.append,
        exit_sink=lambda code: (exit_codes.append(code), finished.set()),
        command_factory=lambda: [sys.executable, "-u", "-c", child_code],
    )
    controller.start()

    assert finished.wait(timeout=5)
    assert events == [payload]
    assert "plain-child-log" in logs
    assert exit_codes == [0]
    assert not controller.is_running


def test_app_self_check_does_not_start_bot(tmp_path):
    app_file = Path(__file__).resolve().parents[1] / "app.py"
    environment = os.environ.copy()
    environment["KAKAOBOT_DATA_DIR"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(app_file), "--self-check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True
