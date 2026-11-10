"""Tkinter desktop UI for configuring and supervising KakaoBot."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from typing import Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from Lib import runtime_paths
from Lib.settings_manager import BotSettings, FeatherServer, GptModel, SettingsManager
from Lib.worker_controller import (  # noqa: F401 - re-exported for callers/tests
    WORKER_EVENT_PREFIX,
    WorkerController,
    build_worker_command,
    decode_worker_line,
)


KNOWN_API_KEYS = (
    "YOUTUBE_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GAME_WIKI_API_KEY",
    "ELEVENLABS_API_KEY",
    "PIXELLAB_API_KEY",
    "KAKAO_REST_API_KEY",
    "KAKAO_ACCESS_TOKEN",
    "KAKAO_REDIRECT_CODE",
    "IG_APP_ID",
    "IG_APP_KEY",
    "IG_ACCESS_TOKEN",
    "IG_USERNAME",
    "FMP_API_KEY",
    "SRT_API_KEY",
)
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")



class DesktopApp:
    """KakaoBot dashboard and complete INI/API-key settings editor."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        settings_manager: SettingsManager | None = None,
        worker_controller: WorkerController | None = None,
    ) -> None:
        runtime_paths.ensure_runtime_layout()
        self.root = root
        self.root.title("KakaoBot")
        self.root.geometry("1220x820")
        self.root.minsize(1040, 700)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.manager = settings_manager or SettingsManager()
        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.controller = worker_controller or WorkerController(
            event_sink=lambda event: self.ui_queue.put(("event", event)),
            log_sink=lambda line: self.ui_queue.put(("log", line)),
            exit_sink=lambda code: self.ui_queue.put(("exit", code)),
        )
        self.settings = BotSettings()
        self.api_keys: dict[str, str] = {}
        self.room_status_items: dict[str, str] = {}
        self.worker_status = "stopped"
        self.started_at: float | None = None
        self.pending_restart = False
        self.closing = False
        self.stop_deadline: float | None = None
        self.force_kill_deadline: float | None = None

        self._create_variables()
        self._configure_style()
        self._build_ui()
        self._load_from_disk(show_errors=False)
        self.root.after(100, self._drain_ui_queue)
        self.root.after(1000, self._update_uptime)

    def _create_variables(self) -> None:
        master = self.root
        self.status_var = tk.StringVar(master, "정지")
        self.pid_var = tk.StringVar(master, "-")
        self.uptime_var = tk.StringVar(master, "00:00:00")
        self.settings_notice_var = tk.StringVar(master, "")
        self.error_only_var = tk.BooleanVar(master, False)
        self.auto_scroll_var = tk.BooleanVar(master, True)

        self.bot_name_var = tk.StringVar(master)
        self.mention_delay_var = tk.StringVar(master)
        self.api_key_path_var = tk.StringVar(master)
        self.chatroom_path_var = tk.StringVar(master)
        self.room_name_var = tk.StringVar(master)

        self.gpt_max_token_var = tk.StringVar(master)
        self.gpt_default_model_var = tk.StringVar(master)
        self.gpt_model_name_var = tk.StringVar(master)
        self.gpt_model_cost_var = tk.StringVar(master)

        self.radar_url_var = tk.StringVar(master)
        self.radar_env_var = tk.StringVar(master)
        self.youtube_status_var = tk.StringVar(master)
        self.instagram_status_var = tk.StringVar(master)

        self.feather_enabled_var = tk.BooleanVar(master)
        self.feather_room_var = tk.StringVar(master)
        self.feather_log_var = tk.StringVar(master)
        self.server_name_var = tk.StringVar(master)
        self.server_path_var = tk.StringVar(master)

        self.github_auto_var = tk.BooleanVar(master)
        self.github_branch_var = tk.StringVar(master)

        self.api_name_var = tk.StringVar(master)
        self.api_value_var = tk.StringVar(master)
        self.api_show_var = tk.BooleanVar(master, False)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        available = style.theme_names()
        if "vista" in available:
            style.theme_use("vista")
        elif "clam" in available:
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("맑은 고딕", 18, "bold"))
        style.configure("Status.TLabel", font=("맑은 고딕", 13, "bold"))
        style.configure("Section.TLabelframe.Label", font=("맑은 고딕", 10, "bold"))

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="KakaoBot Control Center", style="Title.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.settings_notice_var).pack(side="right")

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(fill="both", expand=True)
        self._build_dashboard_tab()
        self._build_general_tab()
        self._build_rooms_tab()
        self._build_gpt_tab()
        self._build_integrations_tab()
        self._build_feather_tab()
        self._build_advanced_tab()
        self._build_api_keys_tab()

        footer = ttk.Frame(container)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Button(footer, text="디스크에서 다시 불러오기", command=self._reload_settings).pack(side="left")
        ttk.Button(footer, text="기본값 불러오기", command=self._load_defaults).pack(side="left", padx=6)
        ttk.Button(footer, text="저장 및 적용", command=self._save_and_apply).pack(side="right")

    def _new_tab(self, title: str) -> ttk.Frame:
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text=title)
        return frame

    def _build_dashboard_tab(self) -> None:
        tab = self._new_tab("대시보드")
        status = ttk.LabelFrame(tab, text="실행 상태", style="Section.TLabelframe", padding=10)
        status.pack(fill="x")
        self.status_label = ttk.Label(status, textvariable=self.status_var, style="Status.TLabel", foreground="#666666")
        self.status_label.grid(row=0, column=0, sticky="w")
        ttk.Label(status, text="PID").grid(row=0, column=1, padx=(40, 5))
        ttk.Label(status, textvariable=self.pid_var).grid(row=0, column=2, sticky="w")
        ttk.Label(status, text="가동 시간").grid(row=0, column=3, padx=(40, 5))
        ttk.Label(status, textvariable=self.uptime_var).grid(row=0, column=4, sticky="w")

        buttons = ttk.Frame(status)
        buttons.grid(row=1, column=0, columnspan=5, sticky="w", pady=(10, 0))
        self.start_button = ttk.Button(buttons, text="시작", command=self._start_worker)
        self.start_button.pack(side="left")
        self.pause_button = ttk.Button(buttons, text="일시정지", command=self._pause_or_resume, state="disabled")
        self.pause_button.pack(side="left", padx=6)
        self.restart_button = ttk.Button(buttons, text="재시작", command=self._request_restart, state="disabled")
        self.restart_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="종료", command=self._request_stop, state="disabled")
        self.stop_button.pack(side="left", padx=6)
        ttk.Button(buttons, text="설정 폴더", command=lambda: self._open_path(runtime_paths.CONFIG_DIR)).pack(side="left", padx=(18, 6))
        ttk.Button(buttons, text="로그 폴더", command=lambda: self._open_path(runtime_paths.SAVED_DIR)).pack(side="left")

        body = ttk.Panedwindow(tab, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(10, 0))
        rooms_frame = ttk.LabelFrame(body, text="채팅방 상태", padding=6)
        logs_frame = ttk.LabelFrame(body, text="실시간 로그", padding=6)
        body.add(rooms_frame, weight=1)
        body.add(logs_frame, weight=3)

        self.room_status_tree = ttk.Treeview(rooms_frame, columns=("room", "status", "detail"), show="headings", height=18)
        self.room_status_tree.heading("room", text="채팅방")
        self.room_status_tree.heading("status", text="상태")
        self.room_status_tree.heading("detail", text="최근 내용")
        self.room_status_tree.column("room", width=160)
        self.room_status_tree.column("status", width=90, anchor="center")
        self.room_status_tree.column("detail", width=260)
        self.room_status_tree.pack(fill="both", expand=True)

        log_controls = ttk.Frame(logs_frame)
        log_controls.pack(fill="x", pady=(0, 5))
        ttk.Checkbutton(log_controls, text="오류만 보기", variable=self.error_only_var).pack(side="left")
        ttk.Checkbutton(log_controls, text="자동 스크롤", variable=self.auto_scroll_var).pack(side="left", padx=8)
        ttk.Button(log_controls, text="화면 지우기", command=self._clear_log).pack(side="right")
        self.log_text = tk.Text(logs_frame, wrap="word", state="disabled", font=("Consolas", 9))
        log_scroll = ttk.Scrollbar(logs_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

    def _entry_row(self, parent, row: int, label: str, variable: tk.Variable, *, browse=None, width=70) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        if browse is not None:
            ttk.Button(parent, text="찾기", command=browse).grid(row=row, column=2, padx=(6, 0), pady=6)
        return entry

    def _build_general_tab(self) -> None:
        tab = self._new_tab("기본 설정")
        form = ttk.LabelFrame(tab, text="일반", padding=14)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self._entry_row(form, 0, "봇 이름", self.bot_name_var)
        self._entry_row(form, 1, "#all 기본 지연(초)", self.mention_delay_var)
        self._entry_row(
            form,
            2,
            "API 키 JSON",
            self.api_key_path_var,
            browse=lambda: self._choose_json_path(self.api_key_path_var, "API 키 파일 선택"),
        )
        self._entry_row(
            form,
            3,
            "채팅방 데이터 JSON",
            self.chatroom_path_var,
            browse=lambda: self._choose_json_path(self.chatroom_path_var, "채팅방 데이터 파일 선택"),
        )
        ttk.Label(
            tab,
            text="상대경로는 배포 폴더 기준으로 저장됩니다. 설정은 저장 후 워커 재시작 시 적용됩니다.",
            foreground="#555555",
        ).pack(anchor="w", pady=12)

    def _build_rooms_tab(self) -> None:
        tab = self._new_tab("채팅방")
        left = ttk.Frame(tab)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.LabelFrame(tab, text="채팅방 편집", padding=12)
        right.pack(side="right", fill="y", padx=(12, 0))
        self.room_tree = ttk.Treeview(left, columns=("room",), show="headings")
        self.room_tree.heading("room", text="채팅방 이름")
        self.room_tree.column("room", width=440)
        self.room_tree.pack(fill="both", expand=True)
        self.room_tree.bind("<<TreeviewSelect>>", self._select_room)
        ttk.Label(right, text="이름").pack(anchor="w")
        ttk.Entry(right, textvariable=self.room_name_var, width=34).pack(fill="x", pady=(3, 10))
        ttk.Button(right, text="추가", command=self._add_room).pack(fill="x")
        ttk.Button(right, text="선택 항목 수정", command=self._update_room).pack(fill="x", pady=5)
        ttk.Button(right, text="삭제", command=self._remove_room).pack(fill="x")
        ttk.Separator(right).pack(fill="x", pady=10)
        ttk.Button(right, text="위로", command=lambda: self._move_tree_item(self.room_tree, -1)).pack(fill="x")
        ttk.Button(right, text="아래로", command=lambda: self._move_tree_item(self.room_tree, 1)).pack(fill="x", pady=5)

    def _build_gpt_tab(self) -> None:
        tab = self._new_tab("GPT")
        top = ttk.LabelFrame(tab, text="기본 GPT 설정", padding=12)
        top.pack(fill="x")
        top.columnconfigure(1, weight=1)
        self._entry_row(top, 0, "최대 토큰", self.gpt_max_token_var, width=24)
        ttk.Label(top, text="기본 모델").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        self.gpt_default_combo = ttk.Combobox(top, textvariable=self.gpt_default_model_var, state="readonly")
        self.gpt_default_combo.grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(top, text="답변 길이 지시문").grid(row=2, column=0, sticky="nw", padx=(0, 12), pady=6)
        self.gpt_answer_text = tk.Text(top, height=3, wrap="word")
        self.gpt_answer_text.grid(row=2, column=1, sticky="ew", pady=6)

        lower = ttk.Panedwindow(tab, orient="horizontal")
        lower.pack(fill="both", expand=True, pady=(12, 0))
        table_frame = ttk.LabelFrame(lower, text="사용 가능 모델", padding=6)
        edit_frame = ttk.LabelFrame(lower, text="모델 편집", padding=12)
        lower.add(table_frame, weight=3)
        lower.add(edit_frame, weight=1)
        self.gpt_model_tree = ttk.Treeview(table_frame, columns=("name", "cost"), show="headings")
        self.gpt_model_tree.heading("name", text="모델")
        self.gpt_model_tree.heading("cost", text="비용 비율(%)")
        self.gpt_model_tree.column("name", width=300)
        self.gpt_model_tree.column("cost", width=120, anchor="e")
        self.gpt_model_tree.pack(fill="both", expand=True)
        self.gpt_model_tree.bind("<<TreeviewSelect>>", self._select_gpt_model)
        ttk.Label(edit_frame, text="모델명").pack(anchor="w")
        ttk.Entry(edit_frame, textvariable=self.gpt_model_name_var).pack(fill="x", pady=(2, 8))
        ttk.Label(edit_frame, text="비용 비율(%)").pack(anchor="w")
        ttk.Entry(edit_frame, textvariable=self.gpt_model_cost_var).pack(fill="x", pady=(2, 10))
        ttk.Button(edit_frame, text="추가", command=self._add_gpt_model).pack(fill="x")
        ttk.Button(edit_frame, text="선택 항목 수정", command=self._update_gpt_model).pack(fill="x", pady=5)
        ttk.Button(edit_frame, text="삭제", command=self._remove_gpt_model).pack(fill="x")

    def _build_integrations_tab(self) -> None:
        tab = self._new_tab("연동")
        radar = ttk.LabelFrame(tab, text="Radar", padding=12)
        radar.pack(fill="x")
        radar.columnconfigure(1, weight=1)
        self._entry_row(radar, 0, "Base URL", self.radar_url_var)
        self._entry_row(radar, 1, "API 키 환경변수", self.radar_env_var)

        diagnostics = ttk.LabelFrame(tab, text="인증 파일 진단", padding=12)
        diagnostics.pack(fill="x", pady=(12, 0))
        ttk.Label(diagnostics, text="YouTube OAuth").grid(row=0, column=0, sticky="w", padx=(0, 20), pady=5)
        ttk.Label(diagnostics, textvariable=self.youtube_status_var).grid(row=0, column=1, sticky="w")
        ttk.Label(diagnostics, text="Instagram 세션").grid(row=1, column=0, sticky="w", padx=(0, 20), pady=5)
        ttk.Label(diagnostics, textvariable=self.instagram_status_var).grid(row=1, column=1, sticky="w")
        ttk.Button(diagnostics, text="상태 새로고침", command=self._refresh_diagnostics).grid(row=2, column=0, pady=(10, 0), sticky="w")
        ttk.Button(
            diagnostics,
            text="Instagram 세션 폴더 열기",
            command=lambda: self._open_path(runtime_paths.INSTAGRAM_SESSION_DIR),
        ).grid(row=2, column=1, pady=(10, 0), sticky="w")

    def _build_feather_tab(self) -> None:
        tab = self._new_tab("Feather 모니터")
        top = ttk.LabelFrame(tab, text="모니터 설정", padding=12)
        top.pack(fill="x")
        top.columnconfigure(1, weight=1)
        ttk.Checkbutton(top, text="Feather 로그 모니터 사용", variable=self.feather_enabled_var).grid(row=0, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(top, text="알림 채팅방").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        self.feather_room_combo = ttk.Combobox(top, textvariable=self.feather_room_var, state="readonly")
        self.feather_room_combo.grid(row=1, column=1, sticky="ew", pady=6)
        self._entry_row(top, 2, "로그 파일명", self.feather_log_var)

        lower = ttk.Panedwindow(tab, orient="horizontal")
        lower.pack(fill="both", expand=True, pady=(12, 0))
        table = ttk.LabelFrame(lower, text="서버 목록", padding=6)
        edit = ttk.LabelFrame(lower, text="서버 편집", padding=12)
        lower.add(table, weight=3)
        lower.add(edit, weight=2)
        self.server_tree = ttk.Treeview(table, columns=("name", "path"), show="headings")
        self.server_tree.heading("name", text="서버 이름")
        self.server_tree.heading("path", text="서버 경로")
        self.server_tree.column("name", width=180)
        self.server_tree.column("path", width=460)
        self.server_tree.pack(fill="both", expand=True)
        self.server_tree.bind("<<TreeviewSelect>>", self._select_server)
        ttk.Label(edit, text="서버 이름").pack(anchor="w")
        ttk.Entry(edit, textvariable=self.server_name_var).pack(fill="x", pady=(2, 8))
        ttk.Label(edit, text="서버 경로").pack(anchor="w")
        path_row = ttk.Frame(edit)
        path_row.pack(fill="x", pady=(2, 10))
        ttk.Entry(path_row, textvariable=self.server_path_var).pack(side="left", fill="x", expand=True)
        ttk.Button(path_row, text="찾기", command=self._choose_server_path).pack(side="right", padx=(5, 0))
        ttk.Button(edit, text="추가", command=self._add_server).pack(fill="x")
        ttk.Button(edit, text="선택 항목 수정", command=self._update_server).pack(fill="x", pady=5)
        ttk.Button(edit, text="삭제", command=self._remove_server).pack(fill="x")

    def _build_advanced_tab(self) -> None:
        tab = self._new_tab("고급")
        git_frame = ttk.LabelFrame(tab, text="소스 실행용 Git 업데이트", padding=12)
        git_frame.pack(fill="x")
        git_frame.columnconfigure(1, weight=1)
        self.github_auto_check = ttk.Checkbutton(git_frame, text="시작 시 Git 자동 업데이트", variable=self.github_auto_var)
        self.github_auto_check.grid(row=0, column=0, columnspan=2, sticky="w", pady=5)
        self._entry_row(git_frame, 1, "브랜치", self.github_branch_var)
        if getattr(sys, "frozen", False):
            self.github_auto_check.configure(state="disabled")
            ttk.Label(git_frame, text="EXE에서는 Git 업데이트를 실행하지 않습니다.", foreground="#7a4d00").grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        paths = ttk.LabelFrame(tab, text="런타임 경로", padding=12)
        paths.pack(fill="x", pady=(12, 0))
        ttk.Label(paths, text="데이터 루트").grid(row=0, column=0, sticky="w", padx=(0, 15), pady=4)
        ttk.Label(paths, text=str(runtime_paths.DATA_DIR)).grid(row=0, column=1, sticky="w")
        ttk.Label(paths, text="설정 파일").grid(row=1, column=0, sticky="w", padx=(0, 15), pady=4)
        ttk.Label(paths, text=str(runtime_paths.SETTINGS_FILE)).grid(row=1, column=1, sticky="w")

    def _build_api_keys_tab(self) -> None:
        tab = self._new_tab("API 키")
        left = ttk.Frame(tab)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.LabelFrame(tab, text="키 편집", padding=12)
        right.pack(side="right", fill="y", padx=(12, 0))
        self.api_tree = ttk.Treeview(left, columns=("name", "status"), show="headings")
        self.api_tree.heading("name", text="환경변수 이름")
        self.api_tree.heading("status", text="상태")
        self.api_tree.column("name", width=360)
        self.api_tree.column("status", width=100, anchor="center")
        self.api_tree.pack(fill="both", expand=True)
        self.api_tree.bind("<<TreeviewSelect>>", self._select_api_key)
        ttk.Label(right, text="이름").pack(anchor="w")
        ttk.Entry(right, textvariable=self.api_name_var, width=38).pack(fill="x", pady=(2, 8))
        ttk.Label(right, text="값").pack(anchor="w")
        self.api_value_entry = ttk.Entry(right, textvariable=self.api_value_var, show="*")
        self.api_value_entry.pack(fill="x", pady=(2, 4))
        ttk.Checkbutton(right, text="값 표시", variable=self.api_show_var, command=self._toggle_api_visibility).pack(anchor="w", pady=(0, 10))
        ttk.Button(right, text="추가 / 수정", command=self._upsert_api_key).pack(fill="x")
        ttk.Button(right, text="선택 키 삭제", command=self._remove_api_key).pack(fill="x", pady=5)
        ttk.Label(
            right,
            text="키 값은 외부 JSON에만 저장되며\nEXE와 로그에는 포함되지 않습니다.",
            foreground="#555555",
            justify="left",
        ).pack(anchor="w", pady=(14, 0))

    # Settings loading and persistence -------------------------------------------------
    def _load_from_disk(self, *, show_errors: bool) -> bool:
        try:
            settings = self.manager.load()
            self.manager.api_keys_path = runtime_paths.resolve_data_path(settings.api_key_path)
            api_keys = self.manager.load_api_keys()
        except Exception as exc:
            if show_errors:
                messagebox.showerror("설정 불러오기 실패", str(exc), parent=self.root)
            self._append_log(f"[ERROR] 설정 불러오기 실패: {exc}")
            return False

        self.settings = settings
        self.api_keys = dict(api_keys)
        for name in KNOWN_API_KEYS:
            self.api_keys.setdefault(name, "")
        self._populate_form(settings)
        self._refresh_api_tree()
        self._refresh_diagnostics()
        for warning in self.manager.api_key_warnings:
            self._append_log(f"[WARN] {warning}")
        self.settings_notice_var.set(f"설정: {self.manager.settings_path}")
        return True

    def _populate_form(self, settings: BotSettings) -> None:
        self.bot_name_var.set(str(settings.bot_name))
        self.mention_delay_var.set(str(settings.every_mention_delay))
        self.api_key_path_var.set(str(settings.api_key_path))
        self.chatroom_path_var.set(str(settings.chatroom_settings_path))
        self._replace_tree(self.room_tree, [(room,) for room in settings.rooms])

        self.gpt_max_token_var.set(str(settings.gpt_max_token))
        self.gpt_default_model_var.set(str(settings.gpt_default_model))
        self.gpt_answer_text.delete("1.0", "end")
        self.gpt_answer_text.insert("1.0", str(settings.gpt_answer_length_limit))
        self._replace_tree(
            self.gpt_model_tree,
            [(model.name, model.cost_percent) for model in settings.gpt_models],
        )

        self.radar_url_var.set(str(settings.radar_base_url))
        self.radar_env_var.set(str(settings.radar_api_key_env))
        self.feather_enabled_var.set(bool(settings.feather_enabled) if isinstance(settings.feather_enabled, bool) else False)
        self.feather_room_var.set(str(settings.feather_notification_room))
        self.feather_log_var.set(str(settings.feather_log_filename))
        self._replace_tree(
            self.server_tree,
            [(server.name, server.path) for server in settings.feather_servers],
        )
        self.github_auto_var.set(bool(settings.github_auto_update) if isinstance(settings.github_auto_update, bool) else False)
        self.github_branch_var.set(str(settings.github_branch))
        self._sync_room_choices()
        self._sync_model_choices()

    @staticmethod
    def _replace_tree(tree: ttk.Treeview, rows) -> None:
        tree.delete(*tree.get_children())
        for row in rows:
            tree.insert("", "end", values=row)

    def _collect_settings(self) -> BotSettings:
        rooms = [str(self.room_tree.item(item, "values")[0]).strip() for item in self.room_tree.get_children()]
        models = [
            GptModel(str(values[0]).strip(), str(values[1]).strip())
            for item in self.gpt_model_tree.get_children()
            if (values := self.gpt_model_tree.item(item, "values"))
        ]
        servers = [
            FeatherServer(str(values[0]).strip(), str(values[1]).strip())
            for item in self.server_tree.get_children()
            if (values := self.server_tree.item(item, "values"))
        ]
        return BotSettings(
            bot_name=self.bot_name_var.get(),
            rooms=rooms,
            api_key_path=self.api_key_path_var.get(),
            chatroom_settings_path=self.chatroom_path_var.get(),
            every_mention_delay=self.mention_delay_var.get(),  # type: ignore[arg-type]
            gpt_max_token=self.gpt_max_token_var.get(),  # type: ignore[arg-type]
            gpt_default_model=self.gpt_default_model_var.get(),
            gpt_answer_length_limit=self.gpt_answer_text.get("1.0", "end-1c"),
            gpt_models=models,
            radar_base_url=self.radar_url_var.get(),
            radar_api_key_env=self.radar_env_var.get(),
            github_auto_update=self.github_auto_var.get(),
            github_branch=self.github_branch_var.get(),
            feather_enabled=self.feather_enabled_var.get(),
            feather_notification_room=self.feather_room_var.get(),
            feather_log_filename=self.feather_log_var.get(),
            feather_servers=servers,
        )

    def _save_settings(self, *, restart: bool, quiet: bool = False) -> bool:
        settings = self._collect_settings()
        errors = self.manager.validate(settings)
        if errors:
            messagebox.showerror("설정 확인", "\n".join(errors), parent=self.root)
            return False
        try:
            self.manager.save(settings)
            self.manager.api_keys_path = runtime_paths.resolve_data_path(settings.api_key_path)
            self.manager.save_api_keys(self.api_keys)
        except Exception as exc:
            messagebox.showerror("설정 저장 실패", str(exc), parent=self.root)
            return False

        self.settings = settings
        self._sync_room_choices()
        self._sync_model_choices()
        self._refresh_diagnostics()
        self.settings_notice_var.set("설정을 저장했습니다.")
        if not quiet:
            self._append_log("[INFO] 설정과 API 키를 안전하게 저장했습니다.")
        if restart and self.controller.is_running:
            self._request_restart()
        return True

    def _save_and_apply(self) -> None:
        self._save_settings(restart=True)

    def _reload_settings(self) -> None:
        if self._load_from_disk(show_errors=True):
            self.settings_notice_var.set("디스크의 설정을 다시 불러왔습니다.")

    def _load_defaults(self) -> None:
        self.settings = BotSettings()
        self._populate_form(self.settings)
        self.settings_notice_var.set("기본값을 불러왔습니다. 저장 전에는 적용되지 않습니다.")

    # Worker lifecycle -----------------------------------------------------------------
    def _start_worker(self) -> None:
        if self.controller.is_running:
            return
        if not self._save_settings(restart=False, quiet=True):
            return
        try:
            pid = self.controller.start()
        except Exception as exc:
            messagebox.showerror("봇 시작 실패", str(exc), parent=self.root)
            self._set_worker_status("error", "시작 실패")
            return
        self.started_at = time.monotonic()
        self.pid_var.set(str(pid))
        self._set_worker_status("starting", "시작 중")
        self._append_log(f"[INFO] 봇 워커를 시작했습니다. PID={pid}")

    def _pause_or_resume(self) -> None:
        if self.worker_status == "paused":
            if self.controller.resume():
                self._set_worker_status("running", "재개 중")
        elif self.controller.is_running and self.controller.pause():
            self._set_worker_status("paused", "일시정지 요청")

    def _request_restart(self) -> None:
        if not self.controller.is_running:
            self._start_worker()
            return
        self.pending_restart = True
        self._request_stop()

    def _request_stop(self) -> None:
        if not self.controller.is_running:
            return
        self.controller.stop()
        self.stop_deadline = time.monotonic() + 8
        self.force_kill_deadline = None
        self._set_worker_status("stopping", "종료 중")
        self.root.after(250, self._enforce_stop_deadline)

    def _enforce_stop_deadline(self) -> None:
        if not self.controller.is_running:
            return
        now = time.monotonic()
        if self.stop_deadline is not None and now >= self.stop_deadline:
            self._append_log("[WARN] 정상 종료 제한 시간을 넘어 워커를 종료합니다.")
            self.controller.terminate()
            self.stop_deadline = None
            self.force_kill_deadline = now + 2
        elif self.force_kill_deadline is not None and now >= self.force_kill_deadline:
            self.controller.kill()
            self.force_kill_deadline = None
        self.root.after(250, self._enforce_stop_deadline)

    def _set_worker_status(self, status: str, text: str | None = None) -> None:
        self.worker_status = status
        labels = {
            "stopped": "정지",
            "starting": "시작 중",
            "running": "실행 중",
            "paused": "일시정지",
            "stopping": "종료 중",
            "error": "오류",
        }
        colors = {
            "stopped": "#666666",
            "starting": "#986800",
            "running": "#17833b",
            "paused": "#986800",
            "stopping": "#986800",
            "error": "#b3261e",
        }
        self.status_var.set(text or labels.get(status, status))
        self.status_label.configure(foreground=colors.get(status, "#333333"))
        running = status in {"starting", "running", "paused", "stopping"}
        self.start_button.configure(state="disabled" if running else "normal")
        self.pause_button.configure(state="normal" if status in {"running", "paused"} else "disabled")
        self.pause_button.configure(text="재개" if status == "paused" else "일시정지")
        self.restart_button.configure(state="normal" if running else "disabled")
        self.stop_button.configure(state="normal" if running else "disabled")

    # Worker events and logs ------------------------------------------------------------
    def _drain_ui_queue(self) -> None:
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "event" and isinstance(payload, dict):
                    self._handle_worker_event(payload)
                elif kind == "log":
                    self._append_log(str(payload))
                elif kind == "exit":
                    self._handle_worker_exit(int(payload))
        except queue.Empty:
            pass
        try:
            if self.root.winfo_exists():
                self.root.after(100, self._drain_ui_queue)
        except tk.TclError:
            pass

    def _handle_worker_event(self, event: dict) -> None:
        event_type = event.get("type")
        status = str(event.get("status", ""))
        message = str(event.get("message", ""))
        if event_type == "engine_status":
            self._set_worker_status(status, None)
        elif event_type == "chat_status":
            self._set_room_status(str(event.get("room", "")), status, message)
        if message:
            level = "ERROR" if status == "error" else "STATUS"
            self._append_log(f"[{level}] {message}")

    def _handle_worker_exit(self, return_code: int) -> None:
        self.pid_var.set("-")
        self.started_at = None
        if self.closing:
            self.root.destroy()
            return
        if self.pending_restart:
            self.pending_restart = False
            self._set_worker_status("stopped")
            self.root.after(300, self._start_worker)
            return
        if return_code == 0:
            self._set_worker_status("stopped")
            self._append_log("[INFO] 봇 워커가 종료되었습니다.")
        else:
            self._set_worker_status("error", f"워커 오류 (코드 {return_code})")
            self._append_log(f"[ERROR] 봇 워커가 종료 코드 {return_code}로 끝났습니다.")

    def _append_log(self, line: str) -> None:
        if not line:
            return
        if self.error_only_var.get():
            upper = line.upper()
            if not any(token in upper for token in ("ERROR", "FAIL", "EXCEPTION", "❌", "⚠")):
                return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        # Bound memory usage even when the app is left open for weeks.
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > 5000:
            self.log_text.delete("1.0", "1000.0")
        if self.auto_scroll_var.get():
            self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _update_uptime(self) -> None:
        if self.started_at is None:
            self.uptime_var.set("00:00:00")
        else:
            elapsed = max(0, int(time.monotonic() - self.started_at))
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.uptime_var.set(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        try:
            if self.root.winfo_exists():
                self.root.after(1000, self._update_uptime)
        except tk.TclError:
            pass

    # Room editor -----------------------------------------------------------------------
    def _select_room(self, _event=None) -> None:
        selection = self.room_tree.selection()
        if selection:
            self.room_name_var.set(str(self.room_tree.item(selection[0], "values")[0]))

    def _add_room(self) -> None:
        name = self.room_name_var.get().strip()
        if name:
            self.room_tree.insert("", "end", values=(name,))
            self.room_name_var.set("")
            self._sync_room_choices()

    def _update_room(self) -> None:
        selection = self.room_tree.selection()
        name = self.room_name_var.get().strip()
        if selection and name:
            self.room_tree.item(selection[0], values=(name,))
            self._sync_room_choices()

    def _remove_room(self) -> None:
        selection = self.room_tree.selection()
        if selection:
            self.room_tree.delete(*selection)
            self.room_name_var.set("")
            self._sync_room_choices()

    def _sync_room_choices(self) -> None:
        rooms = [str(self.room_tree.item(item, "values")[0]) for item in self.room_tree.get_children()]
        self.feather_room_combo.configure(values=rooms)
        existing_status = {room: self._room_status_values(room) for room in rooms}
        self.room_status_tree.delete(*self.room_status_tree.get_children())
        self.room_status_items.clear()
        for room in rooms:
            status, detail = existing_status.get(room, ("대기", ""))
            item = self.room_status_tree.insert("", "end", values=(room, status, detail))
            self.room_status_items[room] = item

    def _room_status_values(self, room: str) -> tuple[str, str]:
        item = self.room_status_items.get(room)
        if not item:
            return "대기", ""
        values = self.room_status_tree.item(item, "values")
        return (str(values[1]), str(values[2])) if len(values) >= 3 else ("대기", "")

    def _set_room_status(self, room: str, status: str, detail: str) -> None:
        labels = {"ready": "준비", "retrying": "재시도", "error": "오류"}
        item = self.room_status_items.get(room)
        if item:
            self.room_status_tree.item(item, values=(room, labels.get(status, status), detail))

    @staticmethod
    def _move_tree_item(tree: ttk.Treeview, delta: int) -> None:
        selection = tree.selection()
        if not selection:
            return
        item = selection[0]
        children = list(tree.get_children())
        index = children.index(item)
        new_index = max(0, min(len(children) - 1, index + delta))
        tree.move(item, "", new_index)
        tree.selection_set(item)

    # GPT model editor ------------------------------------------------------------------
    def _select_gpt_model(self, _event=None) -> None:
        selection = self.gpt_model_tree.selection()
        if selection:
            values = self.gpt_model_tree.item(selection[0], "values")
            self.gpt_model_name_var.set(str(values[0]))
            self.gpt_model_cost_var.set(str(values[1]))

    def _add_gpt_model(self) -> None:
        name, cost = self.gpt_model_name_var.get().strip(), self.gpt_model_cost_var.get().strip()
        if name and cost:
            self.gpt_model_tree.insert("", "end", values=(name, cost))
            self._sync_model_choices()

    def _update_gpt_model(self) -> None:
        selection = self.gpt_model_tree.selection()
        name, cost = self.gpt_model_name_var.get().strip(), self.gpt_model_cost_var.get().strip()
        if selection and name and cost:
            self.gpt_model_tree.item(selection[0], values=(name, cost))
            self._sync_model_choices()

    def _remove_gpt_model(self) -> None:
        selection = self.gpt_model_tree.selection()
        if selection:
            self.gpt_model_tree.delete(*selection)
            self._sync_model_choices()

    def _sync_model_choices(self) -> None:
        models = [str(self.gpt_model_tree.item(item, "values")[0]) for item in self.gpt_model_tree.get_children()]
        self.gpt_default_combo.configure(values=models)
        if models and self.gpt_default_model_var.get() not in models:
            self.gpt_default_model_var.set(models[0])

    # Feather server editor -------------------------------------------------------------
    def _select_server(self, _event=None) -> None:
        selection = self.server_tree.selection()
        if selection:
            values = self.server_tree.item(selection[0], "values")
            self.server_name_var.set(str(values[0]))
            self.server_path_var.set(str(values[1]))

    def _add_server(self) -> None:
        name, path = self.server_name_var.get().strip(), self.server_path_var.get().strip()
        if name and path:
            self.server_tree.insert("", "end", values=(name, path))

    def _update_server(self) -> None:
        selection = self.server_tree.selection()
        name, path = self.server_name_var.get().strip(), self.server_path_var.get().strip()
        if selection and name and path:
            self.server_tree.item(selection[0], values=(name, path))

    def _remove_server(self) -> None:
        selection = self.server_tree.selection()
        if selection:
            self.server_tree.delete(*selection)

    # API key editor --------------------------------------------------------------------
    def _refresh_api_tree(self) -> None:
        self.api_tree.delete(*self.api_tree.get_children())
        for name in sorted(self.api_keys):
            self.api_tree.insert("", "end", values=(name, "설정됨" if self.api_keys[name] else "미설정"))

    def _select_api_key(self, _event=None) -> None:
        selection = self.api_tree.selection()
        if selection:
            name = str(self.api_tree.item(selection[0], "values")[0])
            self.api_name_var.set(name)
            self.api_value_var.set(self.api_keys.get(name, ""))

    def _upsert_api_key(self) -> None:
        name = self.api_name_var.get().strip()
        if not _ENV_NAME_RE.fullmatch(name):
            messagebox.showerror("API 키 이름", "환경변수 형식의 이름을 입력해주세요.", parent=self.root)
            return
        self.api_keys[name] = self.api_value_var.get()
        self._refresh_api_tree()

    def _remove_api_key(self) -> None:
        name = self.api_name_var.get().strip()
        if name in self.api_keys:
            del self.api_keys[name]
        self.api_name_var.set("")
        self.api_value_var.set("")
        self._refresh_api_tree()

    def _toggle_api_visibility(self) -> None:
        self.api_value_entry.configure(show="" if self.api_show_var.get() else "*")

    # Files, diagnostics, and shutdown --------------------------------------------------
    def _choose_json_path(self, variable: tk.StringVar, title: str) -> None:
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title=title,
            initialdir=str(runtime_paths.CONFIG_DIR),
            defaultextension=".json",
            filetypes=(("JSON", "*.json"), ("모든 파일", "*.*")),
        )
        if selected:
            variable.set(self._portable_path(Path(selected)))

    def _choose_server_path(self) -> None:
        selected = filedialog.askdirectory(parent=self.root, title="Feather 서버 폴더 선택")
        if selected:
            self.server_path_var.set(selected)

    @staticmethod
    def _portable_path(path: Path) -> str:
        try:
            return path.resolve().relative_to(runtime_paths.DATA_DIR.resolve()).as_posix()
        except ValueError:
            return str(path.resolve())

    def _refresh_diagnostics(self) -> None:
        token = runtime_paths.YOUTUBE_TOKEN_FILE.exists()
        secret = runtime_paths.YOUTUBE_CLIENT_SECRETS_FILE.exists()
        self.youtube_status_var.set(
            ("토큰 있음" if token else "토큰 없음")
            + " / "
            + ("클라이언트 설정 있음" if secret else "클라이언트 설정 없음")
        )
        sessions = list(runtime_paths.INSTAGRAM_SESSION_DIR.glob("session-*"))
        self.instagram_status_var.set(f"세션 {len(sessions)}개" if sessions else "세션 없음 (공개 embed는 사용 가능)")

    @staticmethod
    def _open_path(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _on_close(self) -> None:
        if self.controller.is_running:
            self.closing = True
            self.pending_restart = False
            self._request_stop()
        else:
            self.root.destroy()


def launch_desktop_app() -> None:
    root = tk.Tk()
    DesktopApp(root)
    root.mainloop()


__all__ = [
    "DesktopApp",
    "WorkerController",
    "build_worker_command",
    "decode_worker_line",
    "launch_desktop_app",
]
