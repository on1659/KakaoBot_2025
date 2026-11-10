from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from Lib.bot_engine import BotEngine, BotEngineDependencies
from Lib import runtime_paths


@pytest.fixture
def no_runtime_layout(monkeypatch):
    monkeypatch.setattr("Lib.bot_engine.ensure_runtime_layout", lambda: None)


def test_runtime_paths_resolve_relative_to_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "DATA_DIR", tmp_path)

    assert runtime_paths.resolve_data_path("config/example.json") == (
        tmp_path / "config" / "example.json"
    ).resolve()

    absolute = (tmp_path.parent / "elsewhere.json").resolve()
    assert runtime_paths.resolve_data_path(absolute) == absolute


def test_frozen_layout_copies_settings_template_once(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    bundle_dir = tmp_path / "bundle"
    template = bundle_dir / "config" / "DefaultSetting.template.ini"
    template.parent.mkdir(parents=True)
    template.write_text("[BotName]\nname = template\n", encoding="utf-8")

    monkeypatch.setattr(runtime_paths, "CONFIG_DIR", data_dir / "config")
    monkeypatch.setattr(runtime_paths, "SAVED_DIR", data_dir / "saved")
    monkeypatch.setattr(
        runtime_paths, "INSTAGRAM_SESSION_DIR", data_dir / "saved" / "instagram"
    )
    monkeypatch.setattr(
        runtime_paths,
        "SETTINGS_FILE",
        data_dir / "config" / "DefaultSetting.ini",
    )
    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime_paths.sys, "_MEIPASS", str(bundle_dir), raising=False)

    runtime_paths.ensure_runtime_layout()

    assert runtime_paths.SETTINGS_FILE.read_text(encoding="utf-8") == template.read_text(
        encoding="utf-8"
    )
    assert runtime_paths.INSTAGRAM_SESSION_DIR.is_dir()

    runtime_paths.SETTINGS_FILE.write_text("user value", encoding="utf-8")
    runtime_paths.ensure_runtime_layout()
    assert runtime_paths.SETTINGS_FILE.read_text(encoding="utf-8") == "user value"


def test_engine_lifecycle_and_cleanup(no_runtime_layout):
    stop_event = threading.Event()
    calls: list[object] = []
    events: list[dict] = []

    class FakeChat:
        IsLoad = 1

        def __init__(self, room_name):
            self.chatroom_name = room_name

        def run(self):
            calls.append(("run", self.chatroom_name))
            stop_event.set()

    monitor = object()
    dependencies = BotEngineDependencies(
        room_names=["room-a", "room-b"],
        chat_factory=FakeChat,
        load_api_keys=lambda: calls.append("load_keys"),
        set_global_chat_list=lambda chats: calls.append(
            ("global", [chat.chatroom_name for chat in chats])
        ),
        start_feather_monitoring=lambda: (calls.append("start_monitor"), monitor)[1],
        stop_feather_monitoring=lambda: calls.append("stop_monitor"),
        close_log_file=lambda: calls.append("close_log"),
    )
    engine = BotEngine(event_callback=events.append, dependencies=dependencies)

    engine.run(stop_event=stop_event)

    assert engine.state == "stopped"
    assert calls[0] == "load_keys"
    assert ("global", ["room-a", "room-b"]) in calls
    assert "start_monitor" in calls
    assert "stop_monitor" in calls
    assert ("global", []) in calls
    assert "close_log" in calls
    assert ("run", "room-a") in calls
    assert ("run", "room-b") not in calls
    assert all(chat.stop_event is stop_event for chat in engine.chats)

    statuses = [
        event["status"] for event in events if event["type"] == "engine_status"
    ]
    assert statuses == ["starting", "running", "stopping", "stopped"]
    room_events = [event for event in events if event["type"] == "chat_status"]
    assert [(event["room"], event["status"]) for event in room_events] == [
        ("room-a", "ready"),
        ("room-b", "ready"),
    ]
    assert all("timestamp" in event and "message" in event for event in events)


def test_engine_passes_stop_event_to_supported_chat_factory(no_runtime_layout):
    stop_event = threading.Event()
    received: list[object] = []

    class StopAwareChat:
        IsLoad = 1

        def __init__(self, room_name, *, stop_event):
            self.chatroom_name = room_name
            self.stop_event = stop_event
            received.append(stop_event)

        def run(self):
            self.stop_event.set()

    engine = BotEngine(
        dependencies=BotEngineDependencies(["room"], StopAwareChat),
        poll_interval=0.01,
    )
    engine.run(stop_event=stop_event)

    assert received == [stop_event]


def test_pause_event_blocks_polling_until_resumed(no_runtime_layout):
    stop_event = threading.Event()
    pause_event = threading.Event()
    pause_event.set()
    paused_seen = threading.Event()
    ran = threading.Event()
    events: list[dict] = []

    class FakeChat:
        IsLoad = 1
        chatroom_name = "room"

        def __init__(self, _room_name):
            pass

        def run(self):
            ran.set()
            stop_event.set()

    def callback(event):
        events.append(event)
        if event["type"] == "engine_status" and event["status"] == "paused":
            paused_seen.set()

    engine = BotEngine(
        event_callback=callback,
        dependencies=BotEngineDependencies(["room"], FakeChat),
        poll_interval=0.01,
    )
    worker = threading.Thread(
        target=engine.run, args=(stop_event, pause_event), daemon=True
    )
    worker.start()

    assert paused_seen.wait(timeout=1)
    assert not ran.is_set()

    pause_event.clear()
    assert ran.wait(timeout=1)
    worker.join(timeout=1)
    assert not worker.is_alive()

    statuses = [
        event["status"] for event in events if event["type"] == "engine_status"
    ]
    assert "paused" in statuses
    assert statuses.count("running") == 2
    assert statuses[-1] == "stopped"


def test_chat_exception_is_reported_without_skipping_cleanup(no_runtime_layout):
    stop_event = threading.Event()
    events: list[dict] = []
    cleanup: list[str] = []

    class BrokenChat:
        IsLoad = 1
        chatroom_name = "broken-room"

        def __init__(self, _room_name):
            pass

        def run(self):
            stop_event.set()
            raise RuntimeError("poll failed")

    dependencies = BotEngineDependencies(
        ["broken-room"],
        BrokenChat,
        stop_feather_monitoring=lambda: cleanup.append("monitor"),
        close_log_file=lambda: cleanup.append("log"),
    )
    engine = BotEngine(event_callback=events.append, dependencies=dependencies)

    engine.run(stop_event=stop_event)

    errors = [
        event
        for event in events
        if event["type"] == "chat_status" and event["status"] == "error"
    ]
    assert errors and errors[0]["room"] == "broken-room"
    assert cleanup == ["monitor", "log"]
    assert engine.state == "stopped"


def test_fatal_initialization_error_emits_final_error_and_cleans_up(no_runtime_layout):
    events: list[dict] = []
    cleanup: list[str] = []

    def fail_loading_keys():
        raise ValueError("invalid key file")

    dependencies = BotEngineDependencies(
        [],
        lambda _name: None,
        load_api_keys=fail_loading_keys,
        stop_feather_monitoring=lambda: cleanup.append("monitor"),
        close_log_file=lambda: cleanup.append("log"),
    )
    engine = BotEngine(event_callback=events.append, dependencies=dependencies)

    engine.run()

    assert engine.state == "error"
    assert engine.last_error == "invalid key file"
    assert cleanup == ["monitor", "log"]
    assert events[-1]["type"] == "engine_status"
    assert events[-1]["status"] == "error"
    assert "ValueError" in events[-1]["traceback"]


def test_importing_main_does_not_start_engine():
    import main

    assert callable(main.main)


def test_packaged_mode_always_skips_git_update(monkeypatch):
    import main
    from Lib import Helper

    def unexpected_git_call():
        raise AssertionError("Git must not be used by a packaged executable")

    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(Helper, "CustomPrint", lambda _message: None)
    monkeypatch.setattr(Helper, "check_git_configuration", unexpected_git_call)

    main.check_and_update()


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _idle_engine(clock, logs):
    dependencies = BotEngineDependencies(room_names=[], chat_factory=lambda name: None, log=logs.append)
    engine = BotEngine(
        dependencies=dependencies,
        poll_interval=0.1,
        idle_steps=((60, 0.5), (300, 1.0), (1800, 2.0)),
        clock=clock,
    )
    return engine, dependencies


def test_idle_backoff_slows_down_and_wakes_on_activity():
    clock = _Clock()
    logs: list[str] = []
    engine, deps = _idle_engine(clock, logs)

    class Chat:
        last_activity = 0.0

    chat = Chat()
    engine.chats = [chat]

    assert engine._current_interval(deps) == 0.1  # just started counts as activity
    clock.now += 59
    assert engine._current_interval(deps) == 0.1
    clock.now += 2
    assert engine._current_interval(deps) == 0.5
    clock.now += 300
    assert engine._current_interval(deps) == 1.0
    clock.now += 3600
    assert engine._current_interval(deps) == 2.0

    chat.last_activity = clock.now  # a new message arrives
    assert engine._current_interval(deps) == 0.1

    assert sum("대기 모드" in line for line in logs) == 3
    assert sum("빠른 모드" in line for line in logs) == 1


def test_idle_backoff_uses_most_recent_room_and_ignores_missing_attribute():
    clock = _Clock()
    logs: list[str] = []
    engine, deps = _idle_engine(clock, logs)

    class Quiet:
        last_activity = 0.0

    class Busy:
        last_activity = 0.0

    class Legacy:  # chat objects without last_activity keep working
        pass

    busy = Busy()
    engine.chats = [Quiet(), busy, Legacy()]
    clock.now += 4000
    busy.last_activity = clock.now - 10
    assert engine._current_interval(deps) == 0.1


def test_idle_steps_can_be_disabled():
    clock = _Clock()
    engine = BotEngine(
        dependencies=BotEngineDependencies(room_names=[], chat_factory=lambda name: None),
        poll_interval=0.1,
        idle_steps=(),
        clock=clock,
    )
    clock.now += 99999
    assert engine._current_interval(engine._get_dependencies()) == 0.1
