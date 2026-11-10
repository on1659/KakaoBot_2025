from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Mirrors worker_main: a thread blocks reading the control pipe while the
# worker spawns git.  Before the fix the git child froze on the inherited pipe.
CHILD = r"""
import subprocess, sys, threading
sys.path.insert(0, sys.argv[1])
import app

control = app._detach_control_stdin()
stop, pause = threading.Event(), threading.Event()
threading.Thread(target=app._read_worker_commands, args=(stop, pause, control), daemon=True).start()
try:
    result = subprocess.run(["git", "--version"], capture_output=True, timeout=10)
    print("GIT_OK" if result.returncode == 0 else "GIT_FAIL", flush=True)
except subprocess.TimeoutExpired:
    print("GIT_HANG", flush=True)
print("STOPPED" if stop.wait(10) else "NO_STOP", flush=True)
"""


@pytest.mark.skipif(sys.platform != "win32", reason="Windows synchronous pipe behaviour")
@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_children_do_not_hang_on_control_pipe():
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", CHILD, str(PROJECT_ROOT)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        first = process.stdout.readline().strip()
        process.stdin.write("stop\n")
        process.stdin.flush()
        second = process.stdout.readline().strip()
    finally:
        process.kill()
        process.wait()
    assert first == "GIT_OK"
    assert second == "STOPPED"
