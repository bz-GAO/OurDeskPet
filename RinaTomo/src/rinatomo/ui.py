"""Minimal native control panel for NapCat login and RinaTomo runtime settings."""

from __future__ import annotations

import base64
import math
import queue
import re
import threading
import time
import tkinter as tk
import webbrowser
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse

from .config import (
    AppConfig,
    ConfigError,
    ConnectionConfig,
    FeaturesConfig,
    LlmConfig,
    PermissionsConfig,
    save,
)
from .napcat import (
    NapCatError,
    NapCatProcess,
    NapCatSettings,
    NapCatWebUI,
    discover_napcat_root,
    discover_qq_path,
    is_napcat_root,
    load_napcat_settings,
    save_napcat_settings,
)
from .runtime import BotService
from .llm import read_usage_snapshot, resolve_model_name
from .control import (
    ControlRequest as _ControlRequest,
    PanelControlServer as _PanelControlServer,
    request_existing_panel as _request_existing_panel,
    prepare_update,
)


def _parse_ids(value: str, label: str) -> list[int]:
    values = [part for part in re.split(r"[\s,，;；]+", value.strip()) if part]
    if any(not item.isdecimal() or int(item) <= 0 for item in values):
        raise ConfigError(f"{label}只能填写正整数 QQ/群号，用逗号或换行分隔")
    return list(dict.fromkeys(int(item) for item in values))


def _format_ids(values: list[int]) -> str:
    return ", ".join(str(value) for value in values)


def _parse_nonnegative_float(value: str, label: str) -> float:
    try:
        result = float(value.strip())
    except ValueError as exc:
        raise ConfigError(f"{label}必须是数字") from exc
    if not math.isfinite(result) or result < 0:
        raise ConfigError(f"{label}必须是大于或等于 0 的有限数字")
    return result


def _parse_positive_float(value: str, label: str) -> float:
    result = _parse_nonnegative_float(value, label)
    if result <= 0:
        raise ConfigError(f"{label}必须大于 0")
    return result


def _parse_positive_int(value: str, label: str) -> int:
    text = value.strip()
    if not text.isdecimal() or int(text) < 1:
        raise ConfigError(f"{label}必须是大于 0 的整数")
    return int(text)


def _login_phase_label(value: str) -> str:
    return {
        "waiting_qrcode": "等待扫码",
        "generating_qrcode": "正在生成二维码",
        "qrcode_scanned": "等待手机确认",
        "qr_login_accepted": "正在登录",
        "offline": "未登录",
    }.get(value, value or "未登录")


class App:
    def __init__(
        self,
        window: tk.Tk,
        config: AppConfig,
        *,
        enable_control_server: bool = True,
        owner: str = "standalone",
    ) -> None:
        if owner not in {"standalone", "desk"}:
            raise ValueError("owner must be standalone or desk")
        self.window = window
        self.config = config
        self.owner = owner
        self.napcat_settings = load_napcat_settings()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.control_server = _PanelControlServer(self.events) if enable_control_server else None
        if self.control_server is not None:
            self.control_server.start()
        self.pipeline_stop = threading.Event()
        self.pipeline_thread: threading.Thread | None = None
        self.napcat_process: NapCatProcess | None = None
        self.webui: NapCatWebUI | None = None
        self.qr_image: tk.PhotoImage | None = None
        self.login_required = False
        self.login_overlay_dismissed = False
        self.login_qr_data_url = ""
        self.login_qr_path: Path | None = None
        self.paused = False
        self.service_connected = False
        self.user_stopped = False
        self.shutting_down = False
        self.shutdown_error = ""
        self.exiting = False
        self.panel_hidden = False
        self.qq_logged_in = False
        self.connection_revision = 0
        self.bot = BotService(self._bot_status, self._activity)

        window.title("RinaTomo")
        window.geometry("760x650")
        window.minsize(700, 560)
        window.protocol("WM_DELETE_WINDOW", self.close_window)
        style = ttk.Style(window)
        style.configure(".", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Status.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(15, 8))

        self.napcat_status = tk.StringVar(value="未连接")
        self.qq_status = tk.StringVar(value="等待启动")
        self.bot_status = tk.StringVar(value="离线")
        self.footer_status = tk.StringVar(value="正在读取本机配置…")

        outer = ttk.Frame(window, padding=18)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="RinaTomo", style="Title.TLabel").pack(side="left")

        status_frame = ttk.LabelFrame(outer, text="运行状态", padding=12)
        status_frame.pack(fill="x")
        for column, (title, variable) in enumerate(
            (("NapCat", self.napcat_status), ("QQ", self.qq_status), ("状态", self.bot_status))
        ):
            cell = ttk.Frame(status_frame)
            cell.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 8, 0))
            ttk.Label(cell, text=title, foreground="#777777").pack(anchor="w")
            ttk.Label(cell, textvariable=variable, style="Status.TLabel", wraplength=210).pack(anchor="w")
            status_frame.columnconfigure(column, weight=1)

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=12)
        self.action_button = ttk.Button(
            controls, text="启动", style="Primary.TButton", command=self.toggle_running
        )
        self.action_button.pack(side="left")
        self.shutdown_button = tk.Button(
            controls,
            text="关闭服务",
            command=self.shutdown_all,
            relief="flat",
            borderwidth=0,
            padx=16,
            pady=7,
            background="#f7dddd",
            foreground="#8b3030",
            activebackground="#efcaca",
            activeforeground="#742525",
            font=("Microsoft YaHei UI", 10),
            cursor="hand2",
        )

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        activity_page = ttk.Frame(notebook, padding=12)
        settings_page = ttk.Frame(notebook, padding=12)
        notebook.add(activity_page, text="活动")
        notebook.add(settings_page, text="设置")

        activity_host = tk.Frame(activity_page, borderwidth=0, highlightthickness=0)
        activity_host.pack(fill="both", expand=True)
        activity_underlay = ttk.Frame(activity_host)
        activity_underlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.activity_list = tk.Listbox(activity_underlay, activestyle="none", borderwidth=0)
        activity_scroll = ttk.Scrollbar(activity_underlay, command=self.activity_list.yview)
        self.activity_list.configure(yscrollcommand=activity_scroll.set)
        activity_scroll.pack(side="right", fill="y")
        self.activity_list.pack(fill="both", expand=True)
        self.activity_list.configure(yscrollcommand=lambda first, last: self._update_scrollbar(activity_scroll, self.activity_list, first, last))

        self.login_overlay = tk.Frame(
            activity_host,
            background="#fbfafb",
            highlightbackground="#d9cbd4",
            highlightthickness=1,
        )
        overlay_header = tk.Frame(self.login_overlay, background="#fbfafb")
        overlay_header.pack(fill="x", padx=18, pady=(14, 0))
        tk.Label(
            overlay_header,
            text="QQ 登录",
            background="#fbfafb",
            font=("Microsoft YaHei UI", 15, "bold"),
        ).pack(side="left")
        tk.Button(
            overlay_header,
            text="×",
            command=self.dismiss_login_overlay,
            relief="flat",
            borderwidth=0,
            background="#fbfafb",
            activebackground="#eee7ec",
            font=("Segoe UI", 14),
            cursor="hand2",
        ).pack(side="right")
        self.login_message = tk.StringVar(value="正在等待 NapCat 生成二维码…")
        tk.Label(
            self.login_overlay,
            textvariable=self.login_message,
            background="#fbfafb",
            foreground="#776a73",
            wraplength=520,
        ).pack(pady=(7, 5))
        self.qr_label = tk.Label(self.login_overlay, background="#fbfafb", anchor="center")
        self.qr_label.pack(fill="both", expand=True, padx=18, pady=5)
        login_actions = ttk.Frame(self.login_overlay)
        login_actions.pack(fill="x", padx=18, pady=(4, 14))
        ttk.Button(login_actions, text="刷新二维码", command=self.refresh_qrcode).pack(side="left")
        ttk.Button(login_actions, text="打开完整登录页", command=self.open_webui).pack(side="right")
        self.login_overlay.place_forget()

        self._build_settings(settings_page)
        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Button(footer, text="打开 NapCat", command=self.open_webui).pack(side="right")

        window.after(100, self._poll_events)
        if self.napcat_settings.auto_start:
            window.after(350, self.start_pipeline)
        else:
            self.footer_status.set("已就绪；点击“启动”后才会连接 NapCat 和 QQ")

    @staticmethod
    def _update_scrollbar(scroll, content, first, last):
        scroll.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            scroll.pack_forget()
        elif not scroll.winfo_manager():
            scroll.pack(side="right", fill="y", before=content)

    def _build_settings(self, parent: ttk.Frame) -> None:
        canvas = tk.Canvas(parent, highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        item = canvas.create_window(0, 0, window=body, anchor="nw")
        body.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        canvas.configure(yscrollcommand=lambda first, last: self._update_scrollbar(scroll, canvas, first, last))
        self.settings_canvas = canvas
        self.settings_body = body
        self.window.bind("<MouseWheel>", self._scroll_settings, add="+")
        self.window.bind("<Button-4>", self._scroll_settings, add="+")
        self.window.bind("<Button-5>", self._scroll_settings, add="+")

        self.notify_enabled = tk.BooleanVar(value=self.config.notifications.enabled)
        self.notify_night = tk.BooleanVar(value=self.config.notifications.night_sleep_enabled)
        self.notify_night_start = tk.StringVar(value=self.config.notifications.night_start)
        self.notify_night_end = tk.StringVar(value=self.config.notifications.night_end)
        self.notify_translation = tk.BooleanVar(value=self.config.notifications.events.translation)
        self.notify_chat_reply = tk.BooleanVar(value=self.config.notifications.events.chat_reply)
        self.notify_login = tk.BooleanVar(value=self.config.notifications.events.login_failure)
        self.feature_ping = tk.BooleanVar(value=self.config.features.ping)
        self.feature_echo = tk.BooleanVar(value=self.config.bot.echo)
        self.llm_enabled = tk.BooleanVar(value=self.config.llm.enabled)
        self.llm_interval = tk.StringVar(value=f"{self.config.llm.min_reply_interval:g}")
        self.llm_timeout = tk.StringVar(value=f"{self.config.llm.timeout_seconds:g}")
        self.llm_max_tokens = tk.StringVar(value=str(self.config.llm.max_tokens))
        self.llm_daily_budget = tk.StringVar(value=str(self.config.llm.daily_token_budget))
        self.llm_max_input = tk.StringVar(value=str(self.config.llm.max_input_chars))
        self.llm_concurrency = tk.StringVar(value=str(self.config.llm.max_concurrent_requests))
        config_dir = self.config.path.parent if self.config.path is not None else None
        self.llm_effective_model = tk.StringVar(
            value=resolve_model_name(self.config.llm.model, config_dir)
        )
        self.llm_usage = tk.StringVar()
        self._next_usage_refresh = 0.0
        self.admin_users = tk.StringVar(value=_format_ids(self.config.permissions.admin_users))
        self.private_users = tk.StringVar(value=_format_ids(self.config.permissions.private_whitelist))
        self.enabled_groups = tk.StringVar(value=_format_ids(self.config.permissions.enabled_groups))
        self.ws_url = tk.StringVar(value=self.config.connection.url)
        self.ws_token = tk.StringVar(value=self.config.connection.access_token)
        self.napcat_root = tk.StringVar(value=str(self.napcat_settings.root))
        self.qq_path = tk.StringVar(value=str(self.napcat_settings.qq_path))
        self.quick_account = tk.StringVar(value=self.napcat_settings.quick_account)
        self.auto_start = tk.BooleanVar(value=self.napcat_settings.auto_start)

        features = ttk.LabelFrame(body, text="对话功能", padding=12)
        features.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(features, text="ping → pong 连通验证", variable=self.feature_ping).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Checkbutton(features, text="复读所有消息（仅联调）", variable=self.feature_echo).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        self.notify_feedback = ttk.Label(features, text="✓ 已应用", foreground="#4f7e6d")
        notifications_frame = ttk.LabelFrame(body, text="通知与深夜休眠", padding=12)
        notifications_frame.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(
            notifications_frame,
            text="推送通知给管理员（仅 admin_users 白名单）",
            variable=self.notify_enabled,
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(
            notifications_frame,
            text="深夜休眠（期间完全不服务，通知丢弃不排队）",
            variable=self.notify_night,
        ).grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Label(notifications_frame, text="休眠时段").grid(row=2, column=0, sticky="w")
        night_row = ttk.Frame(notifications_frame)
        night_row.grid(row=2, column=1, sticky="w")
        ttk.Entry(night_row, textvariable=self.notify_night_start, width=7).pack(side="left")
        ttk.Label(night_row, text=" 至 ").pack(side="left")
        ttk.Entry(night_row, textvariable=self.notify_night_end, width=7).pack(side="left")
        ttk.Checkbutton(notifications_frame, text="事件：翻译任务完成/失败", variable=self.notify_translation).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(notifications_frame, text="事件：聊天回复完成（默认关）", variable=self.notify_chat_reply).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(notifications_frame, text="事件：登录失效", variable=self.notify_login).grid(row=5, column=0, columnspan=2, sticky="w")
        self.notify_feedback.grid(row=6, column=0, sticky="w")
        ttk.Button(notifications_frame, text="应用通知", command=self.apply_notification_settings).grid(row=6, column=1, sticky="e")
        notifications_frame.columnconfigure(0, weight=1)
        self.feature_feedback = ttk.Label(features, text="✓ 已应用", foreground="#4f7e6d")
        self.feature_feedback.grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Button(features, text="应用功能", command=self.apply_feature_settings).grid(
            row=2, column=1, sticky="e", pady=(10, 0)
        )
        features.columnconfigure(0, weight=1)

        llm = ttk.LabelFrame(body, text="大模型服务", padding=12)
        llm.pack(fill="x", pady=(0, 10))
        ttk.Label(llm, text="服务状态").grid(row=0, column=0, sticky="w", pady=5, padx=(0, 10))
        llm_switch = ttk.Frame(llm)
        llm_switch.grid(row=0, column=1, columnspan=2, sticky="w", pady=5)
        ttk.Radiobutton(llm_switch, text="开启", variable=self.llm_enabled, value=True).pack(side="left")
        ttk.Radiobutton(llm_switch, text="关闭", variable=self.llm_enabled, value=False).pack(
            side="left", padx=(12, 0)
        )
        ttk.Label(llm, text="当前模型").grid(row=1, column=0, sticky="w", pady=5, padx=(0, 10))
        ttk.Label(llm, textvariable=self.llm_effective_model).grid(
            row=1, column=1, columnspan=2, sticky="w", pady=5
        )
        ttk.Label(llm, text="最小回复间隔").grid(
            row=2, column=0, sticky="w", pady=5, padx=(0, 10)
        )
        interval = ttk.Combobox(
            llm,
            textvariable=self.llm_interval,
            values=("0", "1", "5", "10"),
            width=10,
        )
        interval.grid(row=2, column=1, sticky="w", pady=5)
        ttk.Label(llm, text="秒；可直接输入自定义值").grid(row=2, column=2, sticky="w", pady=5)
        self._entry_row(llm, 3, "请求超时（秒）", self.llm_timeout)
        self._entry_row(llm, 4, "最大回复 token", self.llm_max_tokens)
        self._entry_row(llm, 5, "每日 token 预算", self.llm_daily_budget)
        self._entry_row(llm, 6, "输入字符上限", self.llm_max_input)
        self._entry_row(llm, 7, "最大并发请求", self.llm_concurrency)
        ttk.Label(llm, text="今日 token 用量").grid(row=8, column=0, sticky="w", pady=5, padx=(0, 10))
        ttk.Label(llm, textvariable=self.llm_usage).grid(row=8, column=1, columnspan=2, sticky="w")
        self._refresh_llm_usage()
        self.llm_feedback = ttk.Label(llm, text="✓ 已应用", foreground="#4f7e6d")
        self.llm_feedback.grid(row=9, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(llm, text="应用大模型设置", command=self.apply_llm_settings).grid(
            row=9, column=2, sticky="e", pady=(10, 0)
        )
        llm.columnconfigure(1, weight=1)

        permissions = ttk.LabelFrame(body, text="权限范围", padding=12)
        permissions.pack(fill="x", pady=(0, 10))
        permission_entries = (
            self._entry_row(permissions, 0, "管理员 QQ", self.admin_users),
            self._entry_row(permissions, 1, "允许私聊", self.private_users),
            self._entry_row(permissions, 2, "启用群聊", self.enabled_groups),
        )
        ttk.Label(permissions, text="可用逗号、空格或换行分隔；空列表表示不放行。", foreground="#777777").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(4, 0)
        )
        self.permission_feedback = ttk.Label(permissions, text="✓ 已应用", foreground="#4f7e6d")
        self.permission_feedback.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(permissions, text="应用权限", command=self.apply_permission_settings).grid(
            row=4, column=2, sticky="e", pady=(10, 0)
        )
        for entry in permission_entries:
            entry.bind("<Return>", lambda _event: self.apply_permission_settings())

        connection = ttk.LabelFrame(body, text="启动与连接", padding=12)
        connection.pack(fill="x", pady=(0, 10))
        self._entry_row(connection, 0, "快速登录 QQ（可选）", self.quick_account)
        ttk.Checkbutton(
            connection,
            text="打开控制面板后自动启动 Bot",
            variable=self.auto_start,
        ).grid(row=1, column=1, columnspan=2, sticky="w", pady=(6, 2))
        connection_tools = ttk.Frame(connection)
        connection_tools.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        self.connection_summary = tk.StringVar()
        self.connection_summary_label = ttk.Label(
            connection_tools, textvariable=self.connection_summary
        )
        self.connection_summary_label.pack(side="left")
        self.connection_advanced_button = ttk.Button(
            connection_tools, text="高级设置", command=self._toggle_connection_advanced
        )
        self.connection_advanced_button.pack(side="right")
        ttk.Button(
            connection_tools, text="重新检测", command=self.redetect_connection_settings
        ).pack(side="right", padx=(0, 8))

        self.connection_advanced = ttk.Frame(connection)
        self.connection_advanced.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self._path_row(
            self.connection_advanced, 0, "NapCat 目录", self.napcat_root, directory=True
        )
        self._path_row(self.connection_advanced, 1, "QQ.exe", self.qq_path, directory=False)
        self._entry_row(self.connection_advanced, 2, "OneBot WS", self.ws_url)
        self._entry_row(
            self.connection_advanced, 3, "OneBot token", self.ws_token, secret=True
        )
        self.connection_advanced.grid_remove()
        self.connection_feedback = ttk.Label(connection, text="✓ 已应用", foreground="#4f7e6d")
        self.connection_feedback.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(connection, text="应用连接设置", command=self.apply_connection_settings).grid(
            row=4, column=2, sticky="e", pady=(10, 0)
        )
        self._refresh_connection_summary()

        self._watch_changes(
            (self.feature_ping, self.feature_echo),
            self.feature_feedback,
        )
        self._watch_changes(
            (
                self.llm_enabled,
                self.llm_interval,
                self.llm_timeout,
                self.llm_max_tokens,
                self.llm_daily_budget,
                self.llm_max_input,
                self.llm_concurrency,
            ),
            self.llm_feedback,
        )
        self._watch_changes(
            (self.admin_users, self.private_users, self.enabled_groups),
            self.permission_feedback,
        )
        self._watch_changes(
            (
                self.napcat_root,
                self.qq_path,
                self.quick_account,
                self.ws_url,
                self.ws_token,
                self.auto_start,
            ),
            self.connection_feedback,
        )

    def _refresh_connection_summary(self) -> None:
        napcat_found = is_napcat_root(Path(self.napcat_root.get()))
        qq_found = Path(self.qq_path.get()).is_file()
        self.connection_summary.set(
            f"NapCat {'已找到' if napcat_found else '未找到'}  ·  QQ {'已找到' if qq_found else '未找到'}"
        )
        self.connection_summary_label.configure(
            foreground="#4f7e6d" if napcat_found and qq_found else "#9a681f"
        )

    def _toggle_connection_advanced(self) -> None:
        if self.connection_advanced.winfo_manager():
            self.connection_advanced.grid_remove()
            self.connection_advanced_button.configure(text="高级设置")
        else:
            self.connection_advanced.grid()
            self.connection_advanced_button.configure(text="收起高级设置")

    def redetect_connection_settings(self) -> bool:
        root = discover_napcat_root()
        qq_path = discover_qq_path()
        if is_napcat_root(root):
            self.napcat_root.set(str(root))
        if qq_path.is_file():
            self.qq_path.set(str(qq_path))
        self._refresh_connection_summary()
        if not is_napcat_root(Path(self.napcat_root.get())) or not Path(
            self.qq_path.get()
        ).is_file():
            self.footer_status.set("未能自动找到完整安装；可在高级设置中选择位置")
            return False
        return self.apply_connection_settings()

    def _scroll_settings(self, event: tk.Event) -> str | None:
        """Scroll only while the pointer is over the settings form."""
        widget = getattr(event, "widget", None)
        if widget is None or isinstance(widget, ttk.Combobox):
            return None
        if widget != self.settings_canvas and not str(widget).startswith(
            str(self.settings_body) + "."
        ) and widget != self.settings_body:
            return None
        number = getattr(event, "num", None)
        if number == 4:
            units = -1
        elif number == 5:
            units = 1
        else:
            delta = int(getattr(event, "delta", 0))
            if delta == 0:
                return None
            units = (-1 if delta > 0 else 1) * max(1, abs(delta) // 120)
        if self.settings_canvas.yview() != (0.0, 1.0):
            self.settings_canvas.yview_scroll(units, "units")
        return "break"

    @staticmethod
    def _entry_row(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        secret: bool = False,
    ) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 10))
        entry = ttk.Entry(parent, textvariable=variable, show="•" if secret else "")
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=5)
        parent.columnconfigure(1, weight=1)
        return entry

    def _path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        *,
        directory: bool,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 10))
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=5)

        def choose() -> None:
            if directory:
                value = filedialog.askdirectory(initialdir=variable.get() or None)
            else:
                value = filedialog.askopenfilename(
                    initialdir=str(Path(variable.get()).parent) if variable.get() else None,
                    filetypes=(("QQ executable", "QQ.exe"), ("Executable", "*.exe")),
                )
            if value:
                variable.set(value)

        ttk.Button(parent, text="选择…", command=choose).grid(row=row, column=2, padx=(8, 0))
        parent.columnconfigure(1, weight=1)

    @staticmethod
    def _watch_changes(variables: tuple[tk.Variable, ...], label: ttk.Label) -> None:
        def mark_pending(*_args: object) -> None:
            label.configure(text="● 有未应用的更改", foreground="#9a681f")

        for variable in variables:
            variable.trace_add("write", mark_pending)

    @staticmethod
    def _mark_applied(label: ttk.Label) -> None:
        label.configure(text="✓ 已应用", foreground="#4f7e6d")

    def start_pipeline(self) -> None:
        if self.shutting_down or self.exiting:
            return
        if self.shutdown_error:
            self.footer_status.set("请先重试关闭服务")
            return
        if self.pipeline_thread is not None and self.pipeline_thread.is_alive():
            self.footer_status.set("启动链路正在运行")
            return
        self.user_stopped = False
        self.shutting_down = False
        self.paused = False
        self.service_connected = False
        self.napcat_status.set("正在连接")
        self.qq_status.set("等待 NapCat")
        self.qq_logged_in = False
        self.bot_status.set("离线")
        self.hide_login_overlay()
        self.login_message.set("正在等待 NapCat 生成二维码…")
        self.login_qr_data_url = ""
        self.login_qr_path = None
        self.pipeline_stop.clear()
        self.shutdown_button.configure(state="normal")
        self.pipeline_thread = threading.Thread(target=self._pipeline_worker, daemon=True)
        self.pipeline_thread.start()
        self._refresh_primary_action()

    def _pipeline_worker(self) -> None:
        try:
            self.events.put(("napcat", "正在启动"))
            process = NapCatProcess(self.napcat_settings)
            self.napcat_process = process
            started = process.start()
            if self.pipeline_stop.is_set():
                return
            self.events.put(("activity", "已拉起 NapCat Shell" if started else "检测到 NapCat 已在运行"))
            client = process.wait_for_webui(stop_event=self.pipeline_stop)
            if self.pipeline_stop.is_set():
                return
            self.webui = client
            self.events.put(("napcat", "已连接"))
            last_qr_mtime = 0.0
            configured_for_account = ""
            configured_revision = -1
            while not self.pipeline_stop.is_set():
                state = client.check_login()
                if self.pipeline_stop.is_set():
                    break
                if state.get("isLogin"):
                    info = client.login_info()
                    account = str(info.get("uin") or info.get("user_id") or "")
                    nickname = str(info.get("nick") or info.get("nickname") or "")
                    self.events.put(("qq", ("已登录", account, nickname)))
                    if (
                        account != configured_for_account
                        or configured_revision != self.connection_revision
                    ):
                        parsed = urlparse(self.config.connection.url)
                        host = parsed.hostname or "127.0.0.1"
                        port = parsed.port or 3001
                        changed = client.ensure_onebot_server(
                            host,
                            port,
                            self.config.connection.access_token,
                        )
                        configured_for_account = account
                        configured_revision = self.connection_revision
                        if changed:
                            self.events.put(("activity", "已同步 RinaTomo 的 OneBot 服务配置"))
                    if self.pipeline_stop.is_set():
                        break
                    if not self.bot.running:
                        self.bot.start(self.config)
                        if self.paused:
                            self.bot.set_paused(True)
                    self.events.put(("login_complete", None))
                else:
                    phase = str(state.get("loginPhase") or "等待二维码")
                    error = str(state.get("loginError") or "")
                    self.events.put(("qq", (phase, "", error)))
                    qr_path = client.qrcode_path
                    if qr_path.is_file():
                        mtime = qr_path.stat().st_mtime
                        if mtime != last_qr_mtime:
                            last_qr_mtime = mtime
                            self.events.put(("qrcode", (qr_path, phase, error)))
                    if self.bot.running:
                        self.bot.stop()
                self.pipeline_stop.wait(1.0)
        except Exception as exc:
            if not self.pipeline_stop.is_set():
                self.events.put(("error", str(exc)))
        finally:
            # The manager owns startup and cleanup, so shutdown cannot race a
            # late NapCat launch or a login response that starts the bot again.
            try:
                self.bot.stop()
            finally:
                try:
                    if not self.shutting_down and self.napcat_process is not None:
                        self.napcat_process.stop()
                except Exception as exc:
                    self.events.put(("shutdown_failed", str(exc)))
                finally:
                    self.events.put(("pipeline_done", None))

    def apply_notification_settings(self) -> bool:
        try:
            self._apply_control_update({"notifications": {
                "enabled": self.notify_enabled.get(),
                "nightSleepEnabled": self.notify_night.get(),
                "nightStart": self.notify_night_start.get().strip(),
                "nightEnd": self.notify_night_end.get().strip(),
                "events": {
                    "translation": self.notify_translation.get(),
                    "chatReply": self.notify_chat_reply.get(),
                    "loginFailure": self.notify_login.get(),
                },
            }})
        except (ValueError, OSError, ConfigError) as exc:
            messagebox.showerror("通知设置未应用", str(exc), parent=self.window)
            return False
        return True

    def apply_feature_settings(self) -> bool:
        try:
            new_config = replace(
                self.config,
                bot=replace(self.config.bot, echo=self.feature_echo.get()),
                features=FeaturesConfig(
                    ping=self.feature_ping.get(),
                ),
            )
            save(new_config)
        except (ValueError, OSError, ConfigError) as exc:
            messagebox.showerror("功能设置未应用", str(exc), parent=self.window)
            return False

        self.config = new_config
        self.bot.apply_behavior(new_config)
        self._mark_applied(self.feature_feedback)
        self.footer_status.set("对话功能已保存并应用")
        self._add_activity("对话功能已热更新")
        return True

    def apply_llm_settings(self) -> bool:
        try:
            llm = LlmConfig(
                enabled=self.llm_enabled.get(),
                model=self.config.llm.model,
                timeout_seconds=_parse_positive_float(self.llm_timeout.get(), "请求超时"),
                max_tokens=_parse_positive_int(self.llm_max_tokens.get(), "最大回复 token"),
                daily_token_budget=_parse_positive_int(
                    self.llm_daily_budget.get(), "每日 token 预算"
                ),
                min_reply_interval=_parse_nonnegative_float(
                    self.llm_interval.get(), "最小回复间隔"
                ),
                max_input_chars=_parse_positive_int(self.llm_max_input.get(), "输入字符上限"),
                max_concurrent_requests=_parse_positive_int(
                    self.llm_concurrency.get(), "最大并发请求"
                ),
            )
            new_config = replace(self.config, llm=llm)
            save(new_config)
        except (OSError, ConfigError) as exc:
            messagebox.showerror("大模型设置未应用", str(exc), parent=self.window)
            return False

        self.config = new_config
        self.bot.apply_behavior(new_config)
        config_dir = new_config.path.parent if new_config.path is not None else None
        self.llm_effective_model.set(resolve_model_name(new_config.llm.model, config_dir))
        self._refresh_llm_usage()
        self._mark_applied(self.llm_feedback)
        self.footer_status.set("大模型设置已保存并应用")
        self._add_activity("大模型服务已热更新")
        return True

    def apply_permission_settings(self) -> bool:
        try:
            new_config = replace(
                self.config,
                permissions=PermissionsConfig(
                    admin_users=_parse_ids(self.admin_users.get(), "管理员 QQ"),
                    private_whitelist=_parse_ids(self.private_users.get(), "允许私聊"),
                    enabled_groups=_parse_ids(self.enabled_groups.get(), "启用群聊"),
                ),
            )
            save(new_config)
        except (OSError, ConfigError) as exc:
            messagebox.showerror("权限设置未应用", str(exc), parent=self.window)
            return False

        self.config = new_config
        self.bot.apply_behavior(new_config)
        self._mark_applied(self.permission_feedback)
        self.footer_status.set("权限范围已保存并应用")
        self._add_activity("权限范围已热更新")
        return True

    def apply_connection_settings(self) -> bool:
        try:
            new_config = replace(
                self.config,
                connection=ConnectionConfig(
                    url=self.ws_url.get().strip(),
                    access_token=self.ws_token.get(),
                    reconnect_delay=self.config.connection.reconnect_delay,
                ),
            )
            new_napcat = NapCatSettings(
                root=Path(self.napcat_root.get()).expanduser().resolve(strict=False),
                qq_path=Path(self.qq_path.get()).expanduser().resolve(strict=False),
                quick_account=self.quick_account.get().strip(),
                auto_start=self.auto_start.get(),
            )
            connection_changed = new_config.connection != self.config.connection
            manager_changed = (
                new_napcat.root,
                new_napcat.qq_path,
                new_napcat.quick_account,
            ) != (
                self.napcat_settings.root,
                self.napcat_settings.qq_path,
                self.napcat_settings.quick_account,
            )
            auto_start_changed = new_napcat.auto_start != self.napcat_settings.auto_start
            save(new_config)
            save_napcat_settings(new_napcat)
        except (ValueError, OSError, ConfigError, NapCatError) as exc:
            messagebox.showerror("连接设置未应用", str(exc), parent=self.window)
            return False

        self.config = new_config
        self.napcat_settings = new_napcat
        self._refresh_connection_summary()
        if manager_changed and self.pipeline_thread is not None and self.pipeline_thread.is_alive():
            self._restart_pipeline()
        elif connection_changed:
            self.connection_revision += 1
            if self.bot.running:
                self.bot.stop()
        self._mark_applied(self.connection_feedback)
        self.footer_status.set(
            "连接设置已保存；自动启动将在下次打开时生效"
            if auto_start_changed
            else "连接设置已保存并应用"
        )
        self._add_activity("连接设置已更新")
        return True

    def toggle_running(self) -> None:
        if self.service_connected and not self.paused:
            self.paused = True
            self.bot.set_paused(True)
            self._add_activity("已暂停自动回复")
            self.footer_status.set("回复已暂停；NapCat 和 QQ 仍保持连接")
            self._refresh_primary_action()
            return
        if self.paused and self.bot.running:
            self.paused = False
            self.bot.set_paused(False)
            self._add_activity("已恢复自动回复")
            self.footer_status.set("RinaTomo 已恢复在线")
            self._refresh_primary_action()
            return
        if self.pipeline_thread is None or not self.pipeline_thread.is_alive():
            self.start_pipeline()

    def _refresh_primary_action(self) -> None:
        pipeline_running = self.pipeline_thread is not None and self.pipeline_thread.is_alive()
        if self._has_running_resources() or self.shutting_down or self.shutdown_error:
            if not self.shutdown_button.winfo_manager():
                self.shutdown_button.pack(side="right")
        else:
            self.shutdown_button.pack_forget()
        if self.shutting_down or self.shutdown_error:
            self.bot_status.set("离线")
            self.action_button.configure(
                text="正在关闭…" if self.shutting_down else "启动", state="disabled"
            )
        elif self.service_connected and not self.paused and not self.user_stopped:
            self.bot_status.set("在线")
            self.action_button.configure(text="暂停", state="normal")
        elif (
            self.paused
            or self.user_stopped
            or self.pipeline_thread is None
            or not self.pipeline_thread.is_alive()
        ):
            self.bot_status.set("离线")
            self.action_button.configure(text="启动", state="normal")
        else:
            self.bot_status.set("离线")
            self.action_button.configure(text="启动中…", state="disabled")

    def shutdown_all(self) -> None:
        if self.shutting_down:
            return
        self.shutting_down = True
        self.shutdown_error = ""
        self.user_stopped = True
        self.paused = False
        self.service_connected = False
        self.pipeline_stop.set()
        self.bot_status.set("离线")
        self.action_button.configure(text="正在关闭…", state="disabled")
        self.shutdown_button.configure(state="disabled")
        self.footer_status.set("正在关闭 RinaTomo 服务、NapCat 和本次启动的 QQ…")

        threading.Thread(target=self._shutdown_worker, daemon=True).start()

    def _shutdown_worker(self) -> None:
        try:
            pipeline = self.pipeline_thread
            if pipeline is not None:
                pipeline.join()
            self.bot.stop()
            if self.bot.running:
                raise NapCatError("消息服务尚未关闭，请重试关闭服务")
            if self.napcat_process is not None:
                self.napcat_process.stop()
        except Exception as exc:
            self.events.put(("shutdown_failed", str(exc)))
        else:
            self.events.put(("shutdown_complete", None))

    def _has_running_resources(self) -> bool:
        return bool(
            (self.pipeline_thread is not None and self.pipeline_thread.is_alive())
            or self.bot.running
            or (self.napcat_process is not None and self.napcat_process.running)
        )

    def show_login_overlay(self, *, force: bool = False) -> None:
        self.login_required = True
        if force:
            self.login_overlay_dismissed = False
        if self.login_overlay_dismissed:
            return
        self.login_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.login_overlay.lift()

    def dismiss_login_overlay(self) -> None:
        self.login_overlay_dismissed = True
        self.login_overlay.place_forget()

    def hide_login_overlay(self) -> None:
        self.login_required = False
        self.login_overlay_dismissed = False
        self.login_overlay.place_forget()

    def _load_qrcode(self, path: Path | None = None, message: str = "") -> None:
        path = path or (self.webui.qrcode_path if self.webui is not None else None)
        if message:
            self.login_message.set(message)
        if path is None or not path.is_file():
            return
        self.login_qr_path = path
        try:
            self.login_qr_data_url = (
                "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
            )
            image = tk.PhotoImage(file=str(path))
            factor = max(1, image.width() // 300)
            if factor > 1:
                image = image.subsample(factor, factor)
            self.qr_image = image
            self.qr_label.configure(image=image, text="")
        except (OSError, tk.TclError) as exc:
            self.login_qr_data_url = ""
            self.login_message.set(f"二维码读取失败：{exc}")

    def refresh_qrcode(self) -> None:
        self.login_overlay_dismissed = False
        self.show_login_overlay(force=True)
        client = self.webui
        if client is None:
            self.footer_status.set("NapCat WebUI 尚未连接")
            return

        def worker() -> None:
            try:
                client.refresh_qrcode()
                time.sleep(0.5)
                self.events.put(("qrcode", (client.qrcode_path, "二维码已刷新", "")))
            except NapCatError as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def open_webui(self) -> None:
        try:
            client = self.webui or NapCatWebUI(self.napcat_settings.root)
            webbrowser.open(client.webui_url())
        except NapCatError as exc:
            messagebox.showerror("无法打开 NapCat WebUI", str(exc), parent=self.window)

    def _restart_pipeline(self) -> None:
        self.pipeline_stop.set()
        self.service_connected = False
        self.paused = False
        self._start_when_pipeline_stopped()

    def _start_when_pipeline_stopped(self) -> None:
        """Wait without blocking Tk until the previous manager loop has exited."""
        if self.pipeline_thread is not None and self.pipeline_thread.is_alive():
            self.window.after(150, self._start_when_pipeline_stopped)
            return
        self.start_pipeline()

    def _bot_status(self, state: str, detail: str) -> None:
        self.events.put(("bot", (state, detail)))

    def _llm_usage_snapshot(self) -> dict[str, int]:
        live = self.bot.llm_usage()
        if live is not None:
            return live
        config_dir = self.config.path.parent if self.config.path is not None else None
        return read_usage_snapshot(self.config.llm.daily_token_budget, config_dir)

    def _refresh_llm_usage(self) -> None:
        usage = self._llm_usage_snapshot()
        self.llm_usage.set(
            f"{usage['used']} / {usage['dailyLimit']}（剩余 {usage['remaining']}）"
        )

    def _activity(self, text: str) -> None:
        self.events.put(("activity", text))

    def _control_snapshot(self) -> dict[str, object]:
        return {
            "protocolVersion": 1,
            "provider": "rinatomo",
            "available": True,
            "owner": self.owner,
            "napcat": self.napcat_status.get(),
            "qq": self.qq_status.get(),
            "state": "online" if self.service_connected and not self.paused else "offline",
            "running": self._has_running_resources(),
            "shuttingDown": self.shutting_down,
            "shutdownError": self.shutdown_error,
            "paused": self.paused,
            "login": {
                "required": self.login_required and not self.qq_logged_in,
                "message": self.login_message.get(),
                "qrcodeDataUrl": self.login_qr_data_url,
            },
            "features": {
                "ping": self.config.features.ping,
                "echo": self.config.bot.echo,
            },
            "notifications": {
                "enabled": self.config.notifications.enabled,
                "nightSleepEnabled": self.config.notifications.night_sleep_enabled,
                "nightStart": self.config.notifications.night_start,
                "nightEnd": self.config.notifications.night_end,
                "events": {
                    "translation": self.config.notifications.events.translation,
                    "chatReply": self.config.notifications.events.chat_reply,
                    "loginFailure": self.config.notifications.events.login_failure,
                },
            },
            "llm": {
                "enabled": self.config.llm.enabled,
                "effectiveModel": self.llm_effective_model.get(),
                "minReplyInterval": self.config.llm.min_reply_interval,
                "timeoutSeconds": self.config.llm.timeout_seconds,
                "maxTokens": self.config.llm.max_tokens,
                "dailyTokenBudget": self.config.llm.daily_token_budget,
                "maxInputChars": self.config.llm.max_input_chars,
                "maxConcurrentRequests": self.config.llm.max_concurrent_requests,
                "usage": self._llm_usage_snapshot(),
            },
            "permissions": {
                "adminUsers": self.config.permissions.admin_users,
                "privateWhitelist": self.config.permissions.private_whitelist,
                "enabledGroups": self.config.permissions.enabled_groups,
            },
            "autoStart": self.napcat_settings.auto_start,
        }

    def _handle_control_request(self, request: _ControlRequest) -> None:
        try:
            if request.command == "status":
                pass
            elif request.command == "show":
                self.panel_hidden = False
                self.window.deiconify()
                self.window.lift()
                self.window.focus_force()
            elif request.command == "start":
                if not (self.service_connected and not self.paused):
                    self.toggle_running()
            elif request.command == "pause":
                if self.service_connected and not self.paused:
                    self.toggle_running()
            elif request.command == "refreshLogin":
                self.refresh_qrcode()
            elif request.command == "shutdown":
                self.shutdown_all()
                request.response.put({"ok": True, "data": self._control_snapshot()})
                return
            elif request.command == "notify":
                payload = request.payload
                event = str(payload.get("event", ""))
                raw_lines = payload.get("lines", [])
                title = str(payload.get("title", ""))[:80] if isinstance(payload.get("title"), str) else ""
                if not isinstance(raw_lines, list) or not (1 <= len(raw_lines) <= 10) or any(
                    not isinstance(line, str) or not line.strip() or len(line) > 300 for line in raw_lines
                ):
                    raise ConfigError("notify.lines 需为 1-10 条非空字符串（每条 ≤300 字符）")
                accepted, reason = self.bot.notify_admins(self.config, event, [str(line) for line in raw_lines])
                self._add_activity(f"通知推送（{event}）：{reason}")
                request.response.put({"ok": True, "data": {"accepted": accepted, "reason": reason}})
                return
            elif request.command == "update":
                self._apply_control_update(request.payload)
            else:
                raise ConfigError("不支持的 Tomo 控制命令")
            request.response.put({"ok": True, "data": self._control_snapshot()})
        except (ConfigError, ValueError, OSError) as exc:
            request.response.put({"ok": False, "error": str(exc)})

    def _apply_control_update(self, payload: dict[str, object]) -> None:
        new_config, new_napcat = prepare_update(self.config, self.napcat_settings, payload)
        group = next(iter(payload))
        if group == "autoStart":
            # Do not apply unrelated, unsaved connection fields from the Tk panel.
            save_napcat_settings(new_napcat)
            self.napcat_settings = new_napcat
            feedback = self.connection_feedback.cget("text")
            color = self.connection_feedback.cget("foreground")
            self.auto_start.set(new_napcat.auto_start)
            self.connection_feedback.configure(text=feedback, foreground=color)
        else:
            save(new_config)
            self.config = new_config
            self.bot.apply_behavior(new_config)
            if group == "features":
                self.feature_ping.set(new_config.features.ping)
                self.feature_echo.set(new_config.bot.echo)
                self._mark_applied(self.feature_feedback)
            elif group == "notifications":
                self.notify_enabled.set(new_config.notifications.enabled)
                self.notify_night.set(new_config.notifications.night_sleep_enabled)
                self.notify_night_start.set(new_config.notifications.night_start)
                self.notify_night_end.set(new_config.notifications.night_end)
                self.notify_translation.set(new_config.notifications.events.translation)
                self.notify_chat_reply.set(new_config.notifications.events.chat_reply)
                self.notify_login.set(new_config.notifications.events.login_failure)
                self._mark_applied(self.notify_feedback)
            elif group == "llm":
                self.llm_enabled.set(new_config.llm.enabled)
                self.llm_interval.set(f"{new_config.llm.min_reply_interval:g}")
                self.llm_timeout.set(f"{new_config.llm.timeout_seconds:g}")
                self.llm_max_tokens.set(str(new_config.llm.max_tokens))
                self.llm_daily_budget.set(str(new_config.llm.daily_token_budget))
                self.llm_max_input.set(str(new_config.llm.max_input_chars))
                self.llm_concurrency.set(str(new_config.llm.max_concurrent_requests))
                config_dir = new_config.path.parent if new_config.path is not None else None
                self.llm_effective_model.set(
                    resolve_model_name(new_config.llm.model, config_dir)
                )
                self._refresh_llm_usage()
                self._mark_applied(self.llm_feedback)
            else:
                self.admin_users.set(_format_ids(new_config.permissions.admin_users))
                self.private_users.set(_format_ids(new_config.permissions.private_whitelist))
                self.enabled_groups.set(_format_ids(new_config.permissions.enabled_groups))
                self._mark_applied(self.permission_feedback)
        self._add_activity("桌宠端设置已同步：" + group)

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "napcat":
                    if self.user_stopped:
                        continue
                    self.napcat_status.set(str(payload))
                    self.footer_status.set(str(payload))
                elif kind == "qq":
                    if self.user_stopped:
                        continue
                    state, account, detail = payload
                    self.qq_logged_in = state == "已登录"
                    self.qq_status.set(
                        str(account) if state == "已登录" and account else _login_phase_label(str(state))
                    )
                    if state != "已登录":
                        self.login_required = True
                        self.login_message.set(str(detail or _login_phase_label(str(state))))
                        if not self.panel_hidden:
                            self.show_login_overlay()
                elif kind == "bot":
                    if self.user_stopped:
                        continue
                    state, detail = payload
                    self.service_connected = state == "connected"
                    self._refresh_primary_action()
                    if detail and state in {"waiting", "error"}:
                        self.footer_status.set(str(detail))
                elif kind == "qrcode":
                    path, phase, error = payload
                    self.login_required = True
                    self._load_qrcode(path, str(error or phase))
                    if not self.panel_hidden:
                        self.show_login_overlay()
                elif kind == "login_complete":
                    self.hide_login_overlay()
                elif kind == "activity":
                    self._add_activity(str(payload))
                elif kind == "show_window":
                    self.panel_hidden = False
                    self.window.deiconify()
                    self.window.lift()
                    self.window.focus_force()
                    if not self.qq_logged_in and self.pipeline_thread is not None:
                        self.show_login_overlay(force=True)
                elif kind == "control_request":
                    self._handle_control_request(payload)
                elif kind == "error":
                    if self.user_stopped:
                        continue
                    self.service_connected = False
                    self._refresh_primary_action()
                    self.footer_status.set(str(payload))
                    self._add_activity("错误 · " + str(payload))
                elif kind == "pipeline_done":
                    self.pipeline_thread = None
                    self._refresh_primary_action()
                elif kind == "shutdown_failed":
                    self.shutting_down = False
                    self.shutdown_error = str(payload)
                    self.service_connected = False
                    self.shutdown_button.configure(state="normal")
                    self.footer_status.set(self.shutdown_error)
                    self._add_activity("关闭失败 · " + self.shutdown_error)
                    self._refresh_primary_action()
                    # Desk may have already exited. Keep this controller
                    # reachable so a failed child shutdown can still be retried.
                    if self.panel_hidden:
                        self.panel_hidden = False
                        self.window.deiconify()
                        self.window.lift()
                elif kind == "shutdown_complete":
                    self.webui = None
                    self.napcat_process = None
                    self.napcat_status.set("未连接")
                    self.qq_status.set("等待启动")
                    self.qq_logged_in = False
                    self.bot_status.set("离线")
                    self.action_button.configure(text="启动", state="normal")
                    self.shutdown_button.configure(state="normal")
                    self.footer_status.set("服务已关闭")
                    self.shutting_down = False
                    self.hide_login_overlay()
                    self._exit_app()
                    return
        except queue.Empty:
            pass
        if time.monotonic() >= self._next_usage_refresh:
            self._next_usage_refresh = time.monotonic() + 5.0
            self._refresh_llm_usage()
        if not self.exiting:
            self.window.after(150, self._poll_events)

    def _add_activity(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.activity_list.insert(0, f"{stamp}  {text}")
        if self.activity_list.size() > 200:
            self.activity_list.delete(200, tk.END)

    def close_window(self) -> None:
        if self.shutting_down:
            return
        if self.owner == "standalone":
            pipeline_running = self.pipeline_thread is not None and self.pipeline_thread.is_alive()
            if pipeline_running or self.bot.running or self.napcat_process is not None:
                self.shutdown_all()
            else:
                self._exit_app()
            return
        self.panel_hidden = True
        self.window.withdraw()

    def _exit_app(self) -> None:
        self.exiting = True
        if self.control_server is not None:
            self.control_server.stop()
        self.window.destroy()


def run_ui(config: AppConfig, *, owner: str = "standalone") -> int:
    if _request_existing_panel():
        return 0
    window = tk.Tk()
    try:
        app = App(window, config, owner=owner)
        if owner == "desk":
            app.panel_hidden = True
            window.withdraw()
    except OSError as exc:
        window.destroy()
        if _request_existing_panel():
            return 0
        raise NapCatError(f"无法启动 RinaTomo 控制面板：{exc}") from exc
    window.mainloop()
    return 0
