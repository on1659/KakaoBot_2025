"""Launch and control the hidden bot worker process.

Shared by the Tkinter desktop UI and the web UI.  Nothing here touches a GUI
toolkit; sinks are called from a background reader thread.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from typing import Callable

from Lib import runtime_paths


WORKER_EVENT_PREFIX = "@@KAKAOBOT_EVENT@@"


def build_worker_command() -> list[str]:
    """Return the source or frozen command used by :class:`WorkerController`."""

    if getattr(sys, "frozen", False):
        return [sys.executable, "--worker"]
    return [sys.executable, "-u", str(runtime_paths.PROJECT_ROOT / "app.py"), "--worker"]


def decode_worker_line(line: str) -> tuple[str, object]:
    """Classify one worker stdout line as a structured event or normal log."""

    text = line.rstrip("\r\n")
    if not text.startswith(WORKER_EVENT_PREFIX):
        return "log", text
    payload = text[len(WORKER_EVENT_PREFIX) :]
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return "log", text
    return ("event", event) if isinstance(event, dict) else ("log", text)


class WorkerController:
    """Start and control the hidden bot worker without touching Tk widgets."""

    def __init__(
        self,
        event_sink: Callable[[dict], None],
        log_sink: Callable[[str], None],
        exit_sink: Callable[[int], None],
        *,
        command_factory: Callable[[], list[str]] = build_worker_command,
    ) -> None:
        self.event_sink = event_sink
        self.log_sink = log_sink
        self.exit_sink = exit_sink
        self.command_factory = command_factory
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._lock = threading.RLock()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    @property
    def pid(self) -> int | None:
        with self._lock:
            return self._process.pid if self._process and self._process.poll() is None else None

    def start(self) -> int:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return self._process.pid

            environment = os.environ.copy()
            environment["PYTHONUTF8"] = "1"
            environment["PYTHONUNBUFFERED"] = "1"
            environment["KAKAOBOT_DATA_DIR"] = str(runtime_paths.DATA_DIR)
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            process = subprocess.Popen(
                self.command_factory(),
                cwd=str(runtime_paths.PROJECT_ROOT),
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags,
            )
            self._process = process
            self._reader = threading.Thread(
                target=self._read_output,
                args=(process,),
                name="kakaobot-worker-output",
                daemon=True,
            )
            self._reader.start()
            return process.pid

    def _read_output(self, process: subprocess.Popen[str]) -> None:
        stream = process.stdout
        if stream is not None:
            try:
                for line in stream:
                    kind, payload = decode_worker_line(line)
                    try:
                        if kind == "event":
                            self.event_sink(payload)  # type: ignore[arg-type]
                        else:
                            self.log_sink(str(payload))
                    except Exception:
                        pass
            except (OSError, ValueError):
                pass
        return_code = process.wait()
        with self._lock:
            if self._process is process:
                self._process = None
        try:
            self.exit_sink(return_code)
        except Exception:
            pass

    def send(self, command: str) -> bool:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None or process.stdin is None:
                return False
            try:
                process.stdin.write(command.strip().lower() + "\n")
                process.stdin.flush()
                return True
            except (BrokenPipeError, OSError, ValueError):
                return False

    def pause(self) -> bool:
        return self.send("pause")

    def resume(self) -> bool:
        return self.send("resume")

    def stop(self) -> bool:
        return self.send("stop")

    def terminate(self) -> None:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                self._process.terminate()

    def kill(self) -> None:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                self._process.kill()
