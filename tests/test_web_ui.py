from __future__ import annotations

import base64
import http.client
import json
import shutil
import threading
from pathlib import Path

import pytest

from Lib import web_ui
from Lib.access_control import AccessControl
from Lib.settings_manager import SettingsManager


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeController:
    def __init__(self, event_sink, log_sink, exit_sink):
        self.event_sink = event_sink
        self.log_sink = log_sink
        self.exit_sink = exit_sink
        self.running = False
        self.commands: list[str] = []
        self.starts = 0

    @property
    def is_running(self):
        return self.running

    @property
    def pid(self):
        return 4321 if self.running else None

    def start(self):
        self.running = True
        self.starts += 1
        return 4321

    def _send(self, command):
        if not self.running:
            return False
        self.commands.append(command)
        return True

    def pause(self):
        return self._send("pause")

    def resume(self):
        return self._send("resume")

    def stop(self):
        return self._send("stop")

    def terminate(self):
        self.commands.append("terminate")

    def kill(self):
        self.commands.append("kill")

    def finish(self, code=0):
        self.running = False
        self.exit_sink(code)


@pytest.fixture
def settings_path(tmp_path):
    target = tmp_path / "DefaultSetting.ini"
    shutil.copy(PROJECT_ROOT / "config" / "DefaultSetting.template.ini", target)
    return target


@pytest.fixture
def env(tmp_path, settings_path):
    def settings_factory():
        return SettingsManager(settings_path, tmp_path / "api_key.json")

    supervisor = web_ui.BotSupervisor(
        controller_factory=FakeController,
        settings_factory=settings_factory,
        restart_delay=0.01,
        stop_grace=0.05,
        kill_grace=0.05,
    )
    shutdown_called = threading.Event()
    app = web_ui.WebApp(
        supervisor,
        permissions=AccessControl(tmp_path / "permissions.json", tmp_path / "seen.json"),
        settings_factory=settings_factory,
        request_shutdown=shutdown_called.set,
    )
    server = web_ui.WebServer(("127.0.0.1", 0), app)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    yield {
        "server": server,
        "app": app,
        "supervisor": supervisor,
        "controller": supervisor.controller,
        "port": server.server_address[1],
        "shutdown_called": shutdown_called,
        "tmp": tmp_path,
    }
    server.shutdown()
    server.server_close()


def request(env, method, path, body=None, *, headers=None, csrf=True):
    conn = http.client.HTTPConnection("127.0.0.1", env["port"], timeout=5)
    all_headers = {"Host": f"127.0.0.1:{env['port']}"}
    if csrf:
        all_headers["X-KakaoBot-Request"] = "1"
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        all_headers["Content-Type"] = "application/json"
    all_headers.update(headers or {})
    conn.request(method, path, body=payload, headers=all_headers)
    response = conn.getresponse()
    raw = response.read()
    conn.close()
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        data = raw.decode("utf-8", "replace")
    return response.status, data, response


def test_index_page_is_served_with_security_headers(env):
    status, body, response = request(env, "GET", "/")
    assert status == 200
    assert "KakaoBot 관리" in body
    assert response.getheader("X-Frame-Options") == "DENY"
    assert "frame-ancestors 'none'" in response.getheader("Content-Security-Policy")


def test_mutations_require_csrf_header(env):
    status, body, _ = request(env, "POST", "/api/bot/start", csrf=False)
    assert status == 403
    assert env["controller"].starts == 0


def test_foreign_host_header_is_rejected(env):
    status, _, _ = request(env, "GET", "/api/state", headers={"Host": "evil.example:8765"})
    assert status == 403


def test_bot_lifecycle(env):
    controller = env["controller"]
    status, body, _ = request(env, "POST", "/api/bot/start")
    assert status == 200 and body["ok"]
    assert controller.starts == 1

    _, state, _ = request(env, "GET", "/api/state")
    assert state["status"] == "starting" and state["pid"] == 4321
    assert any("PID=4321" in line["text"] for line in state["logs"])

    controller.event_sink({"type": "engine_status", "status": "running", "message": "봇이 실행 중입니다."})
    controller.event_sink({"type": "chat_status", "status": "ready", "message": "ok", "room": "봇방"})
    controller.log_sink("일반 로그")
    _, state2, _ = request(env, "GET", f"/api/state?after={state['log_seq']}")
    assert state2["status"] == "running"
    assert {"name": "봇방", "status": "ready", "message": "ok"} in state2["rooms"]
    assert [line["text"] for line in state2["logs"]][-1] == "일반 로그"

    assert request(env, "POST", "/api/bot/pause")[1]["ok"]
    assert controller.commands[-1] == "pause"
    assert request(env, "POST", "/api/bot/resume")[1]["ok"]
    assert controller.commands[-1] == "resume"

    assert request(env, "POST", "/api/bot/stop")[1]["ok"]
    assert controller.commands[-1] == "stop"
    controller.finish(0)
    _, state3, _ = request(env, "GET", "/api/state")
    assert state3["status"] == "stopped" and not state3["running"]


def test_restart_starts_again_after_exit(env):
    controller = env["controller"]
    request(env, "POST", "/api/bot/start")
    request(env, "POST", "/api/bot/restart")
    assert controller.commands[-1] == "stop"
    controller.finish(0)
    for _ in range(100):
        if controller.starts == 2:
            break
        threading.Event().wait(0.01)
    assert controller.starts == 2 and controller.running


def test_stop_deadline_terminates_hung_worker(env):
    controller = env["controller"]
    request(env, "POST", "/api/bot/start")
    request(env, "POST", "/api/bot/stop")
    for _ in range(100):
        if "kill" in controller.commands:
            break
        threading.Event().wait(0.01)
    assert "terminate" in controller.commands and "kill" in controller.commands


def test_start_refuses_invalid_settings(env, settings_path):
    settings_path.write_text("[BotName]\nname =\n", encoding="utf-8")
    status, body, _ = request(env, "POST", "/api/bot/start")
    assert status == 400
    assert body["errors"]
    assert env["controller"].starts == 0


def test_settings_roundtrip(env):
    status, body, _ = request(env, "GET", "/api/settings")
    assert status == 200
    settings = body["settings"]
    settings["bot_name"] = "새봇"
    settings["rooms"] = ["봇방", "테스트방"]

    status, saved, _ = request(env, "PUT", "/api/settings", {"settings": settings})
    assert status == 200, saved
    _, again, _ = request(env, "GET", "/api/settings")
    assert again["settings"]["bot_name"] == "새봇"
    assert again["settings"]["rooms"] == ["봇방", "테스트방"]


def test_settings_validation_errors_are_returned(env):
    _, body, _ = request(env, "GET", "/api/settings")
    settings = body["settings"]
    settings["rooms"] = ["같은방", "같은방"]
    settings["gpt_default_model"] = "없는모델"
    status, error, _ = request(env, "PUT", "/api/settings", {"settings": settings})
    assert status == 400
    assert len(error["errors"]) >= 2


def test_permissions_roundtrip(env):
    status, body, _ = request(env, "GET", "/api/permissions")
    assert status == 200
    assert {f["id"] for f in body["features"]} >= {"gpt", "instagram"}
    permissions = body["permissions"]
    permissions["users"] = [{"name": "철수", "role": "admin", "memo": ""}]
    permissions["features"]["gpt"]["level"] = "admin"

    status, saved, _ = request(env, "PUT", "/api/permissions", {"permissions": permissions})
    assert status == 200, saved
    acl = env["app"].permissions
    assert acl.check("방", "철수", "#gpt").allowed
    assert not acl.check("방", "영희", "#gpt").allowed


def test_permissions_validation(env):
    status, body, _ = request(
        env, "PUT", "/api/permissions", {"permissions": {"users": [{"name": "x", "role": "boss"}]}}
    )
    assert status == 400 and body["errors"]


def test_seen_users_are_listed(env):
    env["app"].permissions.record_sender("봇방", "<img src=x onerror=alert(1)>")
    _, body, _ = request(env, "GET", "/api/permissions")
    assert body["seen_users"][0]["name"] == "<img src=x onerror=alert(1)>"


def test_api_keys_are_write_only(env):
    status, _, _ = request(env, "PUT", "/api/api-keys", {"name": "OPENAI_API_KEY", "value": "sk-secret"})
    assert status == 200
    status, body, _ = request(env, "GET", "/api/api-keys")
    assert status == 200
    assert "sk-secret" not in json.dumps(body)
    assert {"name": "OPENAI_API_KEY", "set": True} in body["keys"]

    status, _, _ = request(env, "DELETE", "/api/api-keys?name=OPENAI_API_KEY")
    assert status == 200
    _, body, _ = request(env, "GET", "/api/api-keys")
    assert {"name": "OPENAI_API_KEY", "set": False} in body["keys"]

    status, _, _ = request(env, "PUT", "/api/api-keys", {"name": "bad name", "value": "x"})
    assert status == 400


def test_shutdown_endpoint(env):
    status, body, _ = request(env, "POST", "/api/shutdown")
    assert status == 200 and body["ok"]
    assert env["shutdown_called"].is_set()


def test_password_protection(tmp_path, settings_path):
    supervisor = web_ui.BotSupervisor(controller_factory=FakeController)
    app = web_ui.WebApp(supervisor, permissions=AccessControl(tmp_path / "p.json", tmp_path / "s.json"))
    server = web_ui.WebServer(("127.0.0.1", 0), app, password="pw")
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    env = {"port": server.server_address[1]}
    try:
        status, _, response = request(env, "GET", "/api/state")
        assert status == 401
        assert "Basic" in response.getheader("WWW-Authenticate")
        wrong = "Basic " + base64.b64encode(b"admin:nope").decode()
        assert request(env, "GET", "/api/state", headers={"Authorization": wrong})[0] == 401
        right = "Basic " + base64.b64encode(b"admin:pw").decode()
        assert request(env, "GET", "/api/state", headers={"Authorization": right})[0] == 200
    finally:
        server.shutdown()
        server.server_close()


def test_non_loopback_requires_password(monkeypatch):
    monkeypatch.setattr(web_ui.runtime_paths, "ensure_runtime_layout", lambda: None)
    assert web_ui.run_web("0.0.0.0", 0, password=None, open_browser=False) == 2


@pytest.mark.parametrize(
    "host,expected",
    [("127.0.0.1", True), ("localhost", True), ("::1", True), ("0.0.0.0", False), ("192.168.0.2", False)],
)
def test_is_loopback_host(host, expected):
    assert web_ui.is_loopback_host(host) is expected
