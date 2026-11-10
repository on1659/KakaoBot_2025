"""Browser-based control panel for KakaoBot.

Runs a small standard-library HTTP server (no extra dependencies) that
supervises the same hidden worker process as the desktop UI and exposes the
settings, the user list, and per-feature permissions as a JSON API consumed by
``Lib/web/index.html``.

Security model
--------------
* Default bind is ``127.0.0.1``: only this PC can reach the panel.  Requests
  whose ``Host`` header is not a loopback name are rejected to stop DNS
  rebinding attacks from web pages open in the same browser.
* Every state-changing request must carry ``X-KakaoBot-Request: 1``.  Browsers
  cannot add that header cross-origin without a CORS preflight, which this
  server never approves, so other sites cannot drive the bot (CSRF).
* Binding to any other address requires a password (HTTP Basic auth).  The
  connection is plain HTTP, so only do that on a trusted network.
* API key values are write-only: the API never returns them.
"""

from __future__ import annotations

from collections import deque
import dataclasses
import base64
import errno
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import ipaddress
import json
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlsplit

from Lib import access_control, runtime_paths
from Lib.settings_manager import BotSettings, FeatherServer, GptModel, SettingsManager
from Lib.worker_controller import WorkerController


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
CSRF_HEADER = "X-KakaoBot-Request"
MAX_BODY_BYTES = 1024 * 1024
LOG_BUFFER_LINES = 3000
STOP_GRACE_SECONDS = 8.0
KILL_GRACE_SECONDS = 2.0
INDEX_FILE = Path(__file__).resolve().parent / "web" / "index.html"
KNOWN_API_KEYS = (
    "OPENAI_API_KEY",
    "YOUTUBE_API_KEY",
    "GEMINI_API_KEY",
    "GAME_WIKI_API_KEY",
    "KAKAO_REST_API_KEY",
    "IG_USERNAME",
    "ELEVENLABS_API_KEY",
    "PIXELLAB_API_KEY",
)
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_print(message: str) -> None:
    # A windowed PyInstaller build has no stdout.
    if sys.stdout is None:
        return
    try:
        print(message, flush=True)
    except (OSError, ValueError):
        pass


def is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


# Worker supervision --------------------------------------------------------------------
class BotSupervisor:
    """Own the worker process and keep a snapshot of its state for the browser."""

    def __init__(
        self,
        *,
        controller_factory: Callable[..., Any] = WorkerController,
        settings_factory: Callable[[], SettingsManager] = SettingsManager,
        restart_delay: float = 0.3,
        stop_grace: float = STOP_GRACE_SECONDS,
        kill_grace: float = KILL_GRACE_SECONDS,
    ) -> None:
        self._lock = threading.RLock()
        self._settings_factory = settings_factory
        self._restart_delay = restart_delay
        self._stop_grace = stop_grace
        self._kill_grace = kill_grace
        self._logs: deque[tuple[int, str]] = deque(maxlen=LOG_BUFFER_LINES)
        self._log_seq = 0
        self.status = "stopped"
        self.status_message = "정지"
        self.started_at: float | None = None
        self.last_exit_code: int | None = None
        self.rooms: dict[str, dict[str, str]] = {}
        self._pending_restart = False
        self._stop_generation = 0
        self._exited = threading.Event()
        self._exited.set()
        self.controller = controller_factory(
            self._on_event, self._on_log, self._on_exit
        )

    # Commands ------------------------------------------------------------------------
    def start(self) -> tuple[bool, list[str]]:
        with self._lock:
            if self.controller.is_running:
                return True, []
            try:
                manager = self._settings_factory()
                settings = manager.load()
                errors = manager.validate(settings)
            except Exception as exc:
                errors = [str(exc)]
            if errors:
                self._append_log("[ERROR] 설정 오류로 봇을 시작할 수 없습니다: " + " / ".join(errors))
                return False, errors
            self.rooms = {
                room: {"status": "waiting", "message": "초기화 대기"} for room in settings.rooms
            }
            try:
                pid = self.controller.start()
            except Exception as exc:
                self._set_status("error", f"시작 실패: {exc}")
                self._append_log(f"[ERROR] 봇 워커를 시작하지 못했습니다: {exc}")
                return False, [str(exc)]
            self._exited.clear()
            self.started_at = time.time()
            self.last_exit_code = None
            self._set_status("starting", "시작 중")
            self._append_log(f"[INFO] 봇 워커를 시작했습니다. PID={pid}")
            return True, []

    def pause(self) -> bool:
        with self._lock:
            if self.status != "running" or not self.controller.pause():
                return False
            self._set_status("paused", "일시정지 요청됨")
            return True

    def resume(self) -> bool:
        with self._lock:
            if self.status != "paused" or not self.controller.resume():
                return False
            self._set_status("running", "재개 요청됨")
            return True

    def stop(self) -> bool:
        with self._lock:
            self._pending_restart = False
            return self._request_stop()

    def restart(self) -> tuple[bool, list[str]]:
        with self._lock:
            if not self.controller.is_running:
                return self.start()
            self._pending_restart = True
            self._request_stop()
            return True, []

    def shutdown(self, timeout: float = STOP_GRACE_SECONDS + KILL_GRACE_SECONDS + 2) -> None:
        """Stop the worker and wait for it; used when the web server exits."""

        with self._lock:
            self._pending_restart = False
            self._request_stop()
        self._exited.wait(timeout)

    def _request_stop(self) -> bool:
        if not self.controller.is_running:
            return False
        self.controller.stop()
        self._set_status("stopping", "종료 중")
        self._stop_generation += 1
        generation = self._stop_generation
        threading.Thread(
            target=self._enforce_stop_deadline,
            args=(generation,),
            name="kakaobot-stop-deadline",
            daemon=True,
        ).start()
        return True

    def _enforce_stop_deadline(self, generation: int) -> None:
        if self._exited.wait(self._stop_grace):
            return
        with self._lock:
            if generation != self._stop_generation or not self.controller.is_running:
                return
            self._append_log("[WARN] 정상 종료 제한 시간을 넘어 워커를 강제 종료합니다.")
            self.controller.terminate()
        if self._exited.wait(self._kill_grace):
            return
        with self._lock:
            if generation == self._stop_generation and self.controller.is_running:
                self.controller.kill()

    # Worker callbacks (reader thread) -------------------------------------------------
    def _on_event(self, event: Mapping[str, Any]) -> None:
        with self._lock:
            event_type = event.get("type")
            status = str(event.get("status", ""))
            message = str(event.get("message", ""))
            if event_type == "engine_status" and status:
                if not (self.status == "stopping" and status in {"running", "paused"}):
                    self._set_status(status, message or status)
            elif event_type == "chat_status":
                room = str(event.get("room", ""))
                if room:
                    self.rooms[room] = {"status": status, "message": message}
            if message:
                level = "ERROR" if status == "error" else "STATUS"
                self._append_log(f"[{level}] {message}")

    def _on_log(self, line: str) -> None:
        with self._lock:
            self._append_log(line)

    def _on_exit(self, return_code: int) -> None:
        with self._lock:
            self.last_exit_code = return_code
            self.started_at = None
            restart = self._pending_restart
            self._pending_restart = False
            if restart:
                self._set_status("stopped", "재시작 중")
            elif return_code == 0:
                self._set_status("stopped", "정지")
                self._append_log("[INFO] 봇 워커가 종료되었습니다.")
            else:
                self._set_status("error", f"워커 오류 (종료 코드 {return_code})")
                self._append_log(f"[ERROR] 봇 워커가 종료 코드 {return_code}로 끝났습니다.")
            self._exited.set()
        if restart:
            timer = threading.Timer(self._restart_delay, self.start)
            timer.daemon = True
            timer.start()

    # Snapshot ------------------------------------------------------------------------
    def _set_status(self, status: str, message: str) -> None:
        self.status = status
        self.status_message = message

    def _append_log(self, line: str) -> None:
        line = line.rstrip("\r\n")
        if not line:
            return
        self._log_seq += 1
        self._logs.append((self._log_seq, line))

    def snapshot(self, after: int = 0) -> dict[str, Any]:
        with self._lock:
            logs = [
                {"seq": seq, "text": text} for seq, text in self._logs if seq > after
            ]
            oldest = self._logs[0][0] if self._logs else self._log_seq + 1
            return {
                "status": self.status,
                "status_message": self.status_message,
                "running": self.controller.is_running,
                "pid": self.controller.pid,
                "started_at": self.started_at,
                "last_exit_code": self.last_exit_code,
                "rooms": [
                    {"name": name, **info} for name, info in self.rooms.items()
                ],
                "logs": logs,
                "log_seq": self._log_seq,
                "logs_truncated": after > 0 and after + 1 < oldest,
            }


# Settings (de)serialization ------------------------------------------------------------
def settings_to_json(settings: BotSettings) -> dict[str, Any]:
    return dataclasses.asdict(settings)


def settings_from_json(data: Any, base: BotSettings | None = None) -> BotSettings:
    """Build ``BotSettings`` from browser JSON; bad shapes are left for ``validate``."""

    if not isinstance(data, Mapping):
        raise ValueError("설정은 JSON 객체여야 합니다.")
    values = dataclasses.asdict(base or BotSettings())
    names = {field.name for field in dataclasses.fields(BotSettings)}
    for key, value in data.items():
        if key in names:
            values[key] = value

    def rows(raw: Any, factory: Callable[..., Any], keys: tuple[str, str]) -> Any:
        if not isinstance(raw, list):
            return raw
        result = []
        for item in raw:
            if isinstance(item, Mapping):
                result.append(factory(item.get(keys[0], ""), item.get(keys[1], "")))
            else:
                result.append(item)
        return result

    values["gpt_models"] = rows(values["gpt_models"], GptModel, ("name", "cost_percent"))
    values["feather_servers"] = rows(values["feather_servers"], FeatherServer, ("name", "path"))
    if isinstance(values["rooms"], list):
        values["rooms"] = [r.strip() if isinstance(r, str) else r for r in values["rooms"]]
    return BotSettings(**values)


# HTTP application ----------------------------------------------------------------------
class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.errors = errors or [message]


class WebApp:
    """Route table and handlers, independent of the socket server for testing."""

    def __init__(
        self,
        supervisor: BotSupervisor,
        *,
        permissions: access_control.AccessControl | None = None,
        settings_factory: Callable[[], SettingsManager] = SettingsManager,
        index_file: Path = INDEX_FILE,
        request_shutdown: Callable[[], None] | None = None,
    ) -> None:
        self.supervisor = supervisor
        self.permissions = permissions or access_control.AccessControl()
        self.settings_factory = settings_factory
        self.index_file = index_file
        self.request_shutdown = request_shutdown or (lambda: None)
        self._settings_lock = threading.Lock()

    def handle(self, method: str, path: str, query: Mapping[str, list[str]], body: Any) -> Any:
        routes: dict[tuple[str, str], Callable[[], Any]] = {
            ("GET", "/api/state"): lambda: self.supervisor.snapshot(
                self._int_query(query, "after")
            ),
            ("POST", "/api/bot/start"): self._start,
            ("POST", "/api/bot/stop"): lambda: {"ok": self.supervisor.stop()},
            ("POST", "/api/bot/pause"): lambda: {"ok": self.supervisor.pause()},
            ("POST", "/api/bot/resume"): lambda: {"ok": self.supervisor.resume()},
            ("POST", "/api/bot/restart"): self._restart,
            ("GET", "/api/settings"): self._get_settings,
            ("PUT", "/api/settings"): lambda: self._put_settings(body),
            ("GET", "/api/permissions"): self._get_permissions,
            ("PUT", "/api/permissions"): lambda: self._put_permissions(body),
            ("GET", "/api/api-keys"): self._get_api_keys,
            ("PUT", "/api/api-keys"): lambda: self._put_api_key(body),
            ("DELETE", "/api/api-keys"): lambda: self._delete_api_key(query),
            ("POST", "/api/shutdown"): self._shutdown,
        }
        handler = routes.get((method, path))
        if handler is None:
            if any(route_path == path for _, route_path in routes):
                raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "지원하지 않는 요청 방식입니다.")
            raise ApiError(HTTPStatus.NOT_FOUND, "요청한 API가 없습니다.")
        return handler()

    @staticmethod
    def _int_query(query: Mapping[str, list[str]], name: str) -> int:
        try:
            return max(0, int(query.get(name, ["0"])[0]))
        except ValueError:
            return 0

    def _start(self) -> dict[str, Any]:
        ok, errors = self.supervisor.start()
        if not ok:
            raise ApiError(HTTPStatus.BAD_REQUEST, "봇을 시작할 수 없습니다.", errors)
        return {"ok": True}

    def _restart(self) -> dict[str, Any]:
        ok, errors = self.supervisor.restart()
        if not ok:
            raise ApiError(HTTPStatus.BAD_REQUEST, "봇을 재시작할 수 없습니다.", errors)
        return {"ok": True}

    def _shutdown(self) -> dict[str, Any]:
        self.request_shutdown()
        return {"ok": True}

    # Settings --------------------------------------------------------------------------
    def _load_settings(self) -> tuple[SettingsManager, BotSettings]:
        manager = self.settings_factory()
        try:
            settings = manager.load()
        except ValueError as exc:
            raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)) from exc
        return manager, settings

    def _get_settings(self) -> dict[str, Any]:
        manager, settings = self._load_settings()
        return {
            "settings": settings_to_json(settings),
            "errors": manager.validate(settings),
            "path": str(manager.settings_path),
        }

    def _put_settings(self, body: Any) -> dict[str, Any]:
        with self._settings_lock:
            manager, current = self._load_settings()
            try:
                new_settings = settings_from_json(
                    body.get("settings") if isinstance(body, Mapping) else None, current
                )
            except (TypeError, ValueError) as exc:
                raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
            errors = manager.validate(new_settings)
            if errors:
                raise ApiError(HTTPStatus.BAD_REQUEST, "설정을 확인해주세요.", errors)
            try:
                manager.save(new_settings)
            except (OSError, ValueError) as exc:
                raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, f"설정 저장 실패: {exc}") from exc
        restarted = False
        if isinstance(body, Mapping) and body.get("restart") and self.supervisor.controller.is_running:
            restarted, _errors = self.supervisor.restart()
        return {"ok": True, "restarted": restarted, "settings": settings_to_json(new_settings)}

    # Permissions -----------------------------------------------------------------------
    def _get_permissions(self) -> dict[str, Any]:
        rules = self.permissions.load()
        broken = bool(rules.pop("_broken", False))
        try:
            rooms = self.settings_factory().load().rooms
        except Exception:
            rooms = []
        return {
            "permissions": rules,
            "broken": broken,
            "features": [
                {"id": f.id, "label": f.label, "commands": list(f.commands)}
                for f in access_control.FEATURES
            ],
            "rooms": rooms,
            "seen_users": self.permissions.seen_users(),
            "path": str(self.permissions.permissions_path),
        }

    def _put_permissions(self, body: Any) -> dict[str, Any]:
        data = body.get("permissions") if isinstance(body, Mapping) else None
        try:
            saved = self.permissions.save(data)
        except ValueError as exc:
            raise ApiError(
                HTTPStatus.BAD_REQUEST, "권한 설정을 확인해주세요.", str(exc).splitlines()
            ) from exc
        except OSError as exc:
            raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, f"권한 저장 실패: {exc}") from exc
        return {"ok": True, "permissions": saved}

    # API keys (write-only) -------------------------------------------------------------
    def _api_key_manager(self) -> SettingsManager:
        manager, settings = self._load_settings()
        manager.api_keys_path = runtime_paths.resolve_data_path(settings.api_key_path)
        return manager

    def _read_api_keys(self, manager: SettingsManager) -> dict[str, str]:
        try:
            return manager.load_api_keys()
        except ValueError as exc:
            raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)) from exc

    def _get_api_keys(self) -> dict[str, Any]:
        manager = self._api_key_manager()
        keys = self._read_api_keys(manager)
        names = list(keys) + [name for name in KNOWN_API_KEYS if name not in keys]
        return {
            "keys": [{"name": name, "set": bool(keys.get(name))} for name in names],
            "path": str(manager.api_keys_path),
        }

    def _put_api_key(self, body: Any) -> dict[str, Any]:
        if not isinstance(body, Mapping):
            raise ApiError(HTTPStatus.BAD_REQUEST, "요청 형식이 올바르지 않습니다.")
        name = body.get("name")
        value = body.get("value")
        if not isinstance(name, str) or not _ENV_NAME_RE.match(name.strip()):
            raise ApiError(HTTPStatus.BAD_REQUEST, "키 이름은 영문/숫자/밑줄만 사용할 수 있습니다.")
        if not isinstance(value, str) or not value.strip():
            raise ApiError(HTTPStatus.BAD_REQUEST, "키 값을 입력해주세요.")
        with self._settings_lock:
            manager = self._api_key_manager()
            keys = self._read_api_keys(manager)
            keys[name.strip()] = value.strip()
            manager.save_api_keys(keys)
        return {"ok": True}

    def _delete_api_key(self, query: Mapping[str, list[str]]) -> dict[str, Any]:
        name = query.get("name", [""])[0]
        with self._settings_lock:
            manager = self._api_key_manager()
            keys = self._read_api_keys(manager)
            if name not in keys:
                raise ApiError(HTTPStatus.NOT_FOUND, "등록되지 않은 키입니다.")
            del keys[name]
            manager.save_api_keys(keys)
        return {"ok": True}


class WebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        address: tuple[str, int],
        app: WebApp,
        *,
        password: str | None = None,
    ) -> None:
        super().__init__(address, RequestHandler)
        self.app = app
        self.password = password or None
        self.loopback_only = is_loopback_host(address[0])


class RequestHandler(BaseHTTPRequestHandler):
    server: WebServer
    server_version = "KakaoBotWeb/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return  # keep the console for bot logs

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        try:
            if not self._host_allowed():
                raise ApiError(HTTPStatus.FORBIDDEN, "허용되지 않은 Host 헤더입니다.")
            if not self._authorized():
                self._send_unauthorized()
                return
            url = urlsplit(self.path)
            if method == "GET" and url.path in {"/", "/index.html"}:
                self._send_index()
                return
            if not url.path.startswith("/api/"):
                raise ApiError(HTTPStatus.NOT_FOUND, "페이지를 찾을 수 없습니다.")
            if method != "GET" and self.headers.get(CSRF_HEADER) != "1":
                raise ApiError(HTTPStatus.FORBIDDEN, "잘못된 요청 출처입니다.")
            body = self._read_json_body() if method in {"POST", "PUT"} else None
            result = self.server.app.handle(method, url.path, parse_qs(url.query), body)
            self._send_json(HTTPStatus.OK, result)
        except ApiError as exc:
            self._send_json(exc.status, {"ok": False, "error": exc.message, "errors": exc.errors})
        except Exception as exc:  # pragma: no cover - last-resort guard
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": f"서버 오류: {exc}", "errors": [str(exc)]},
            )

    def _host_allowed(self) -> bool:
        if not self.server.loopback_only:
            return True
        host = (self.headers.get("Host") or "").strip().lower()
        if host.startswith("["):
            hostname = host[: host.find("]") + 1]
        else:
            hostname = host.rsplit(":", 1)[0] if ":" in host else host
        return hostname in {"localhost", "127.0.0.1", "[::1]"}

    def _authorized(self) -> bool:
        password = self.server.password
        if password is None:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        supplied = decoded.split(":", 1)[1] if ":" in decoded else ""
        return hmac.compare_digest(supplied.encode("utf-8"), password.encode("utf-8"))

    def _read_json_body(self) -> Any:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "잘못된 요청 길이입니다.")
        if length > MAX_BODY_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "요청이 너무 큽니다.")
        if length == 0:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "JSON 형식이 올바르지 않습니다.")

    def _common_headers(self, content_type: str, length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )

    def _send_json(self, status: HTTPStatus, payload: Any) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._common_headers("application/json; charset=utf-8", len(data))
        self.end_headers()
        self.wfile.write(data)

    def _send_index(self) -> None:
        try:
            data = self.server.app.index_file.read_bytes()
        except OSError as exc:
            raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, f"화면 파일을 찾을 수 없습니다: {exc}")
        self.send_response(HTTPStatus.OK)
        self._common_headers("text/html; charset=utf-8", len(data))
        self.end_headers()
        self.wfile.write(data)

    def _send_unauthorized(self) -> None:
        data = "로그인이 필요합니다.".encode("utf-8")
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="KakaoBot", charset="UTF-8"')
        self._common_headers("text/plain; charset=utf-8", len(data))
        self.end_headers()
        self.wfile.write(data)


# Entry point ---------------------------------------------------------------------------
def run_web(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    password: str | None = None,
    open_browser: bool = True,
    autostart: bool = False,
) -> int:
    runtime_paths.ensure_runtime_layout()
    if not is_loopback_host(host) and not password:
        _safe_print(
            "[ERROR] 127.0.0.1 이외의 주소로 열려면 비밀번호가 필요합니다. "
            "--password 또는 KAKAOBOT_WEB_PASSWORD 환경변수를 지정하세요."
        )
        return 2

    browse_host = "127.0.0.1" if host in {"0.0.0.0", "::", ""} else host
    url = f"http://{browse_host}:{port}/"
    supervisor = BotSupervisor()
    app = WebApp(supervisor)
    try:
        server = WebServer((host, port), app, password=password)
    except OSError as exc:
        if exc.errno in {errno.EADDRINUSE, 10048}:
            _safe_print(f"[INFO] 포트 {port}가 이미 사용 중입니다. 이미 실행 중인 화면을 엽니다: {url}")
            if open_browser:
                import webbrowser

                webbrowser.open(url)
            return 1
        raise

    def request_shutdown() -> None:
        threading.Thread(target=server.shutdown, name="kakaobot-web-shutdown", daemon=True).start()

    app.request_shutdown = request_shutdown
    _safe_print(f"[INFO] KakaoBot 웹 관리 화면: {url}  (종료: Ctrl+C 또는 화면의 '웹 서버 종료')")
    if not is_loopback_host(host):
        _safe_print("[WARN] 외부 접속이 허용되었습니다. 신뢰할 수 있는 네트워크에서만 사용하세요 (HTTP 평문).")
    if open_browser:
        import webbrowser

        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    if autostart:
        supervisor.start()

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        _safe_print("[INFO] 웹 서버를 종료합니다. 실행 중인 봇을 정리하는 중...")
        supervisor.shutdown()
        server.server_close()
    return 0


__all__ = [
    "BotSupervisor",
    "WebApp",
    "WebServer",
    "run_web",
    "settings_from_json",
    "settings_to_json",
    "is_loopback_host",
]
