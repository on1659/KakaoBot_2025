"""Controllable runtime engine for the KakaoBot console and desktop UI."""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from .runtime_paths import ensure_runtime_layout


EventCallback = Callable[[dict[str, Any]], None]


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


@dataclass
class BotEngineDependencies:
    """Injectable adapters around the legacy modules.

    Supplying this object lets tests exercise the engine without importing
    Windows automation, pandas, OpenAI, or any other production dependency.
    ``room_names`` may be an iterable or a zero-argument provider callable.
    """

    room_names: Iterable[str] | Callable[[], Iterable[str]]
    chat_factory: Callable[[str], Any]
    load_api_keys: Callable[[], Any] = _noop
    set_global_chat_list: Callable[[list[Any]], Any] = _noop
    start_feather_monitoring: Callable[[], Any] = _noop
    stop_feather_monitoring: Callable[[], Any] = _noop
    close_log_file: Callable[[], Any] = _noop
    log: Callable[[str], Any] = _noop


# (조용한 시간(초) 이상이면, 이 간격(초)으로 확인) — 대화가 없으면 점점 천천히 확인해 PC 부담을
# 줄이고, 새 메시지가 보이면 즉시 poll_interval로 돌아온다. 조용할 때 첫 응답만 최대 간격만큼 늦다.
IDLE_STEPS: tuple[tuple[float, float], ...] = (
    (60.0, 0.5),
    (300.0, 1.0),
    (1800.0, 2.0),
)


class BotEngine:
    """Run the existing bot with cooperative pause and stop controls.

    ``pause_event`` follows the standard event convention used by the UI:
    set means paused and clear means running.  A pause or stop takes effect at
    the next polling boundary; an in-progress Windows automation operation is
    allowed to finish first so clipboard and keyboard state are not abandoned.
    """

    def __init__(
        self,
        event_callback: EventCallback | None = None,
        *,
        dependencies: BotEngineDependencies | Mapping[str, Any] | Any | None = None,
        poll_interval: float = 0.1,
        idle_steps: Iterable[tuple[float, float]] = IDLE_STEPS,
        sleep: Callable[[float], Any] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be greater than zero")

        self.event_callback = event_callback
        self.dependencies = dependencies
        self.poll_interval = float(poll_interval)
        self.idle_steps = tuple(sorted((float(t), float(i)) for t, i in idle_steps))
        self._sleep = sleep
        self._clock = clock
        self._started_monotonic = clock()
        self._announced_interval: float | None = None

        self._local_stop_event = threading.Event()
        self._local_pause_event = threading.Event()
        self._active_stop_event: Any = self._local_stop_event
        self._active_pause_event: Any = self._local_pause_event
        self._run_lock = threading.Lock()

        self.chats: list[Any] = []
        self.feather_monitor: Any = None
        self.state = "stopped"
        self.last_error: str | None = None

    def stop(self) -> None:
        """Request a cooperative stop from this or another thread."""

        self._local_stop_event.set()
        setter = getattr(self._active_stop_event, "set", None)
        if callable(setter):
            setter()

    def pause(self) -> None:
        """Pause before the next chat polling operation."""

        self._local_pause_event.set()
        setter = getattr(self._active_pause_event, "set", None)
        if callable(setter):
            setter()

    def resume(self) -> None:
        """Resume a paused engine."""

        self._local_pause_event.clear()
        clearer = getattr(self._active_pause_event, "clear", None)
        if callable(clearer):
            clearer()

    @property
    def is_running(self) -> bool:
        return self.state in {"starting", "running", "paused", "stopping"}

    def run(self, stop_event: Any | None = None, pause_event: Any | None = None) -> None:
        """Run until stopped, cleaning monitors and the log file on every exit."""

        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("BotEngine is already running")

        self._active_stop_event = stop_event or self._local_stop_event
        self._active_pause_event = pause_event or self._local_pause_event
        if self._local_stop_event.is_set():
            self._set_event(self._active_stop_event)
        if self._local_pause_event.is_set():
            self._set_event(self._active_pause_event)

        dependencies: BotEngineDependencies | None = None
        fatal_error: BaseException | None = None
        self.chats = []
        self.feather_monitor = None
        self.last_error = None
        self._started_monotonic = self._clock()
        self._announced_interval = None

        try:
            ensure_runtime_layout()
            self._set_state("starting", "봇을 시작하는 중입니다.")
            dependencies = self._get_dependencies()
            dependencies.load_api_keys()

            room_names = self._get_room_names(dependencies.room_names)
            for room_name in room_names:
                if self._is_set(self._active_stop_event):
                    break
                self._create_chat(room_name, dependencies)

            dependencies.set_global_chat_list(self.chats)
            self.feather_monitor = dependencies.start_feather_monitoring()
            if self.feather_monitor is None:
                self._emit(
                    "feather_status",
                    "disabled",
                    "Feather 로그 모니터링이 비활성화되어 있습니다.",
                )
            else:
                self._emit(
                    "feather_status",
                    "running",
                    "Feather 로그 모니터링을 시작했습니다.",
                )

            if not self._is_set(self._active_stop_event):
                self._set_state("running", "봇이 실행 중입니다.")
                self._poll_chats(dependencies)

        except KeyboardInterrupt:
            self.stop()
        except BaseException as exc:
            fatal_error = exc
            self.last_error = str(exc)
        finally:
            if self.state not in {"stopping", "stopped"}:
                self._set_state("stopping", "봇을 종료하는 중입니다.")
            self._cleanup(dependencies)

            if fatal_error is None:
                self._set_state("stopped", "봇이 종료되었습니다.")
            else:
                self._set_state(
                    "error",
                    f"봇 실행 중 오류가 발생했습니다: {fatal_error}",
                    error=repr(fatal_error),
                    traceback="".join(
                        traceback.format_exception(
                            type(fatal_error), fatal_error, fatal_error.__traceback__
                        )
                    ),
                )

            self._active_stop_event = self._local_stop_event
            self._active_pause_event = self._local_pause_event
            self._run_lock.release()

    def _get_dependencies(self) -> BotEngineDependencies:
        if self.dependencies is None:
            return self._load_default_dependencies()

        if isinstance(self.dependencies, BotEngineDependencies):
            return self.dependencies

        def value(name: str, default: Any = _noop) -> Any:
            if isinstance(self.dependencies, Mapping):
                return self.dependencies.get(name, default)
            return getattr(self.dependencies, name, default)

        room_names = value("room_names", ())
        chat_factory = value("chat_factory", None)
        if chat_factory is None:
            raise ValueError("Injected dependencies must provide chat_factory")
        return BotEngineDependencies(
            room_names=room_names,
            chat_factory=chat_factory,
            load_api_keys=value("load_api_keys"),
            set_global_chat_list=value("set_global_chat_list"),
            start_feather_monitoring=value("start_feather_monitoring"),
            stop_feather_monitoring=value("stop_feather_monitoring"),
            close_log_file=value("close_log_file"),
            log=value("log"),
        )

    @staticmethod
    def _load_default_dependencies() -> BotEngineDependencies:
        # Deliberately late: importing ChatProcess initializes Windows-only
        # automation dependencies and importing dataManager loads the INI.
        from Lib import Helper, chat_process, dataManager, json_data_manager, log_monitor

        return BotEngineDependencies(
            room_names=lambda: list(dataManager.kakao_opentalk_name_List),
            chat_factory=chat_process.ChatProcess,
            load_api_keys=json_data_manager.load_api_keys,
            set_global_chat_list=log_monitor.set_global_chat_list,
            start_feather_monitoring=log_monitor.start_feather_monitoring_from_config,
            stop_feather_monitoring=log_monitor.stop_feather_monitoring,
            close_log_file=Helper.close_log_file,
            log=Helper.CustomPrint,
        )

    @staticmethod
    def _get_room_names(
        room_names: Iterable[str] | Callable[[], Iterable[str]],
    ) -> list[str]:
        supplied = room_names() if callable(room_names) else room_names
        return [str(name) for name in supplied]

    def _create_chat(self, room_name: str, dependencies: BotEngineDependencies) -> None:
        try:
            try:
                chat = dependencies.chat_factory(
                    room_name, stop_event=self._active_stop_event
                )
            except TypeError as exc:
                # Compatibility with the original ChatProcess constructor and
                # lightweight test doubles that only accept the room name.
                if "stop_event" not in str(exc):
                    raise
                chat = dependencies.chat_factory(room_name)
            try:
                chat.stop_event = self._active_stop_event
            except (AttributeError, TypeError):
                pass
            self.chats.append(chat)
            loaded = getattr(chat, "IsLoad", 1)
            if loaded:
                self._emit(
                    "chat_status",
                    "ready",
                    f"채팅방 '{room_name}' 초기화가 완료되었습니다.",
                    room=room_name,
                )
            else:
                self._emit(
                    "chat_status",
                    "retrying",
                    f"채팅방 '{room_name}' 초기화에 실패해 실행 중 재시도합니다.",
                    room=room_name,
                )
        except Exception as exc:
            self._emit(
                "chat_status",
                "error",
                f"채팅방 '{room_name}' 초기화에 실패했습니다: {exc}",
                room=room_name,
                error=repr(exc),
            )

    def _poll_chats(self, dependencies: BotEngineDependencies) -> None:
        pause_announced = False
        while not self._is_set(self._active_stop_event):
            if self._is_set(self._active_pause_event):
                if not pause_announced:
                    pause_announced = True
                    self._set_state("paused", "봇이 일시정지되었습니다.")
                self._wait_for_stop(self.poll_interval)
                continue

            if pause_announced:
                pause_announced = False
                self._set_state("running", "봇 실행을 재개했습니다.")

            for chat in self.chats:
                if self._is_set(self._active_stop_event) or self._is_set(
                    self._active_pause_event
                ):
                    break
                try:
                    chat.run()
                except Exception as exc:
                    room_name = str(getattr(chat, "chatroom_name", "알 수 없는 방"))
                    dependencies.log(
                        f"❌ [{room_name}] 실행 오류 - 다음 주기에 재시도합니다: {exc}"
                    )
                    self._emit(
                        "chat_status",
                        "error",
                        f"채팅방 '{room_name}' 실행 중 오류가 발생했습니다: {exc}",
                        room=room_name,
                        error=repr(exc),
                    )

            self._wait_for_stop(self._current_interval(dependencies))

    def _current_interval(self, dependencies: BotEngineDependencies) -> float:
        """Pick the polling interval from how long every room has been quiet.

        Chats expose ``last_activity`` (a ``time.monotonic`` timestamp of the
        last new message).  The engine start counts as activity, so a fresh
        start is responsive.  Mode changes are logged once per transition.
        """

        latest = self._started_monotonic
        for chat in self.chats:
            value = getattr(chat, "last_activity", None)
            if isinstance(value, (int, float)) and value > latest:
                latest = value
        idle = self._clock() - latest

        interval = self.poll_interval
        for threshold, step_interval in self.idle_steps:
            if idle >= threshold:
                interval = step_interval

        if interval != self._announced_interval:
            if interval > self.poll_interval:
                dependencies.log(
                    f"💤 {int(idle // 60)}분째 조용해서 대기 모드로 전환합니다 (확인 간격 {interval:g}초)"
                )
            elif self._announced_interval is not None:
                dependencies.log(
                    f"⚡ 새 메시지 감지 - 빠른 모드로 전환합니다 (확인 간격 {interval:g}초)"
                )
            self._announced_interval = interval
        return interval

    def _cleanup(self, dependencies: BotEngineDependencies | None) -> None:
        if dependencies is None:
            return

        cleanup_errors: list[str] = []
        for name, cleanup in (
            ("Feather monitor", dependencies.stop_feather_monitoring),
            ("global chat list", lambda: dependencies.set_global_chat_list([])),
            ("log file", dependencies.close_log_file),
        ):
            try:
                cleanup()
            except Exception as exc:
                cleanup_errors.append(f"{name}: {exc}")

        self.feather_monitor = None
        if cleanup_errors:
            self._emit(
                "cleanup_status",
                "error",
                "일부 종료 정리에 실패했습니다: " + "; ".join(cleanup_errors),
                errors=cleanup_errors,
            )
        else:
            self._emit("feather_status", "stopped", "Feather 로그 모니터링을 종료했습니다.")

    def _set_state(self, status: str, message: str, **fields: Any) -> None:
        self.state = status
        self._emit("engine_status", status, message, **fields)

    def _emit(self, event_type: str, status: str, message: str, **fields: Any) -> None:
        callback = self.event_callback
        if callback is None:
            return

        event: dict[str, Any] = {
            "type": event_type,
            "status": status,
            "message": message,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        event.update(fields)
        try:
            callback(event)
        except Exception:
            # A broken UI/IPC callback must never take down the bot worker.
            return

    def _wait_for_stop(self, timeout: float) -> bool:
        waiter = getattr(self._active_stop_event, "wait", None)
        if callable(waiter):
            return bool(waiter(timeout))
        self._sleep(timeout)
        return self._is_set(self._active_stop_event)

    @staticmethod
    def _is_set(event: Any) -> bool:
        checker = getattr(event, "is_set", None)
        return bool(checker()) if callable(checker) else False

    @staticmethod
    def _set_event(event: Any) -> None:
        setter = getattr(event, "set", None)
        if callable(setter):
            setter()


__all__ = ["BotEngine", "BotEngineDependencies", "EventCallback"]
