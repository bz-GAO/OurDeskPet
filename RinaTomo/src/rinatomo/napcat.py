"""Local NapCat Shell discovery, process management, and WebUI API access."""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .config import default_config_dir
from .managed_log import ManagedProcessLog


NAPCAT_REQUIRED_FILES = (
    "napcat.mjs",
    "NapCatWinBootMain.exe",
    "NapCatWinBootHook.dll",
    "qqnt.json",
)


def is_napcat_root(path: Path) -> bool:
    return all((path / name).is_file() for name in NAPCAT_REQUIRED_FILES)


def _windows_drive_roots() -> list[Path]:
    if os.name != "nt":
        return []
    try:
        import ctypes

        mask = ctypes.windll.kernel32.GetLogicalDrives()
        roots = []
        for offset in range(26):
            if not mask & (1 << offset):
                continue
            root = Path(f"{chr(ord('A') + offset)}:\\")
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(root))
            if drive_type in {2, 3}:  # removable or fixed local drive
                roots.append(root)
        return roots
    except (AttributeError, OSError):
        return []


def discover_napcat_root() -> Path:
    """Prefer an explicit override, then common portable install locations."""
    override = os.environ.get("RINATOMO_NAPCAT_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve(strict=False)
    return default_config_dir() / "NapCat"
    workspace = Path(__file__).resolve().parents[3]
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    candidates = [
        workspace / "NapCat" / "Shell" / "napcat",
        workspace / "NapCat" / "napcat",
        workspace / "NapCat",
        base / "NapCat" / "napcat",
    ]
    for drive in _windows_drive_roots():
        candidates.extend(
            (
                drive / "NapCat" / "Shell" / "napcat",
                drive / "NapCat" / "napcat",
                drive / "NapCat",
            )
        )
    return next((path for path in candidates if is_napcat_root(path)), candidates[-1])


class NapCatError(RuntimeError):
    pass


@dataclass
class NapCatSettings:
    root: Path = field(default_factory=discover_napcat_root)
    qq_path: Path = field(default_factory=lambda: discover_qq_path())
    quick_account: str = ""
    auto_start: bool = False

    @property
    def path(self) -> Path:
        return default_config_dir() / "napcat.json"


def load_napcat_settings() -> NapCatSettings:
    path = default_config_dir() / "napcat.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return NapCatSettings()
    if not isinstance(raw, dict):
        return NapCatSettings()

    def local_path(key: str, fallback: Path) -> Path:
        value = raw.get(key)
        return Path(value).expanduser().resolve(strict=False) if isinstance(value, str) and value.strip() else fallback

    detected_root = discover_napcat_root()
    detected_qq = discover_qq_path()
    root = local_path("root", detected_root)
    qq_path = local_path("qq_path", detected_qq)
    if not is_napcat_root(root) and is_napcat_root(detected_root):
        root = detected_root
    if not qq_path.is_file() and detected_qq.is_file():
        qq_path = detected_qq
    return NapCatSettings(
        root=root,
        qq_path=qq_path,
        quick_account=str(raw.get("quick_account", "")).strip(),
        auto_start=raw.get("auto_start", False) is True,
    )


def save_napcat_settings(settings: NapCatSettings) -> Path:
    target = settings.path
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "root": str(settings.root.resolve(strict=False)),
        "qq_path": str(settings.qq_path.resolve(strict=False)),
        "quick_account": settings.quick_account.strip(),
        "auto_start": settings.auto_start,
    }
    pending = target.with_name(target.name + ".pending")
    try:
        pending.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(pending, target)
    finally:
        pending.unlink(missing_ok=True)
    return target


def _qq_registry_path(value_name: str, value: object) -> Path | None:
    """Interpret each registry field without treating arguments as paths."""
    if not isinstance(value, str):
        return None
    text = os.path.expandvars(value).strip()
    if not text:
        return None
    if value_name == "InstallLocation":
        text = text.strip('"')
    elif text.startswith('"'):
        closing_quote = text.find('"', 1)
        if closing_quote < 0:
            return None
        text = text[1:closing_quote]
    elif value_name == "DisplayIcon":
        text = re.sub(r",\s*-?\d+\s*$", "", text).strip()
    elif value_name == "UninstallString":
        executable = re.match(r"(.+?\.exe)(?:\s|$)", text, flags=re.IGNORECASE)
        if executable is None:
            return None
        text = executable.group(1)
    path = Path(text)
    # Registry paths must never depend on the launcher's current directory.
    if not path.is_absolute():
        return None
    if value_name == "InstallLocation":
        return path / "QQ.exe"
    if path.suffix.lower() != ".exe":
        return None
    return path if path.name.lower() == "qq.exe" else path.parent / "QQ.exe"


def discover_qq_path() -> Path:
    override = os.environ.get("RINATOMO_QQ_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve(strict=False)
    program_files = Path(os.environ.get("ProgramFiles") or Path.home().anchor)
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)") or program_files)
    local_app_data = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    candidates = [
        program_files / "Tencent" / "QQNT" / "QQ.exe",
        program_files / "Tencent" / "QQ" / "QQ.exe",
        program_files_x86 / "Tencent" / "QQNT" / "QQ.exe",
        local_app_data / "Programs" / "Tencent" / "QQ" / "QQ.exe",
    ]
    try:
        import winreg

        roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
        keys = (
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\QQ",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ",
        )
        for root in roots:
            for key_name in keys:
                try:
                    with winreg.OpenKey(root, key_name) as key:
                        for value_name in ("InstallLocation", "DisplayIcon", "UninstallString"):
                            try:
                                value, _ = winreg.QueryValueEx(key, value_name)
                            except OSError:
                                continue
                            path = _qq_registry_path(value_name, value)
                            if path is not None:
                                candidates.insert(0, path)
                except OSError:
                    continue
    except (OSError, ImportError):
        pass
    for drive in _windows_drive_roots():
        candidates.extend(
            (
                drive / "Tencent" / "QQNT" / "QQ.exe",
                drive / "Program Files" / "Tencent" / "QQNT" / "QQ.exe",
            )
        )
    return next((candidate for candidate in candidates if candidate.is_file()), candidates[0])


def port_is_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


class NapCatWebUI:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._credential = ""

    @property
    def webui_config(self) -> dict[str, Any]:
        try:
            value = json.loads((self.root / "config" / "webui.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise NapCatError(f"无法读取 NapCat WebUI 配置：{exc}") from exc
        if not isinstance(value, dict):
            raise NapCatError("NapCat WebUI 配置格式无效")
        return value

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{int(self.webui_config.get('port', 6099))}"

    @property
    def qrcode_path(self) -> Path:
        return self.root / "cache" / "qrcode.png"

    def authenticate(self) -> None:
        token = str(self.webui_config.get("token", ""))
        if not token:
            raise NapCatError("NapCat WebUI token 为空")
        digest = hashlib.sha256((token + ".napcat").encode("utf-8")).hexdigest()
        result = self._request("/api/auth/login", {"hash": digest}, authenticated=False)
        credential = result.get("Credential") if isinstance(result, dict) else None
        if not credential:
            raise NapCatError("NapCat WebUI 未返回登录凭证")
        self._credential = str(credential)

    def check_login(self) -> dict[str, Any]:
        return self._post("/api/QQLogin/CheckLoginStatus")

    def login_info(self) -> dict[str, Any]:
        return self._post("/api/QQLogin/GetQQLoginInfo")

    def refresh_qrcode(self) -> dict[str, Any]:
        return self._post("/api/QQLogin/RefreshQRcode")

    def get_qrcode(self) -> dict[str, Any]:
        return self._post("/api/QQLogin/GetQQLoginQrcode")

    def get_ob11_config(self) -> dict[str, Any]:
        return self._post("/api/OB11Config/GetConfig")

    def set_ob11_config(self, config: dict[str, Any]) -> None:
        self._post(
            "/api/OB11Config/SetConfig",
            {"config": json.dumps(config, ensure_ascii=False)},
        )

    def ensure_onebot_server(self, host: str, port: int, token: str) -> bool:
        config = self.get_ob11_config()
        network = config.setdefault("network", {})
        servers = network.setdefault("websocketServers", [])
        if not isinstance(servers, list):
            servers = []
            network["websocketServers"] = servers
        desired = {
            "name": "RinaTomo",
            "enable": True,
            "host": host,
            "port": port,
            "messagePostFormat": "array",
            "reportSelfMessage": False,
            "token": token,
            "enableForcePushEvent": True,
            "debug": False,
        }
        existing = next(
            (server for server in servers if isinstance(server, dict) and server.get("name") == "RinaTomo"),
            None,
        )
        if existing == desired:
            return False
        if existing is None:
            servers.append(desired)
        else:
            existing.clear()
            existing.update(desired)
        self.set_ob11_config(config)
        return True

    def webui_url(self) -> str:
        token = str(self.webui_config.get("token", ""))
        return f"{self.base_url}/webui?token={quote(token)}"

    def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._credential:
            self.authenticate()
        try:
            return self._request(path, body or {}, authenticated=True)
        except NapCatError as exc:
            if "Unauthorized" not in str(exc):
                raise
            self.authenticate()
            return self._request(path, body or {}, authenticated=True)

    def _request(
        self,
        path: str,
        body: dict[str, Any],
        *,
        authenticated: bool,
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self._credential}"
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=3.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, ValueError) as exc:
            raise NapCatError(f"NapCat WebUI 请求失败：{exc}") from exc
        if not isinstance(payload, dict) or payload.get("code") != 0:
            message = payload.get("message", "未知错误") if isinstance(payload, dict) else "响应格式无效"
            raise NapCatError(str(message))
        data = payload.get("data")
        return data if isinstance(data, dict) else {}


class NapCatProcess:
    def __init__(self, settings: NapCatSettings) -> None:
        self.settings = settings
        self.process: subprocess.Popen | None = None
        self._log_capture: ManagedProcessLog | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def validate(self) -> None:
        missing = [name for name in NAPCAT_REQUIRED_FILES if not (self.settings.root / name).is_file()]
        if missing:
            raise NapCatError("请在设置中选择本机 NapCat Shell 目录；当前目录缺少：" + ", ".join(missing))
        if not self.settings.qq_path.is_file():
            raise NapCatError(f"找不到 QQ：{self.settings.qq_path}")

    def start(self) -> bool:
        self.validate()
        webui = NapCatWebUI(self.settings.root)
        # A fresh Shell install may generate webui.json only after its first boot.
        has_webui_config = (self.settings.root / "config" / "webui.json").is_file()
        if has_webui_config and port_is_open(int(webui.webui_config.get("port", 6099))):
            return False
        main_path = self.settings.root / "napcat.mjs"
        loader_path = self.settings.root / "loadNapCat.js"
        loader_text = f'(async () => {{await import("{main_path.as_uri()}")}})()\n'
        if not loader_path.is_file() or loader_path.read_text(encoding="utf-8") != loader_text:
            loader_path.write_text(loader_text, encoding="utf-8", newline="\n")
        environment = os.environ.copy()
        environment.update(
            {
                "NAPCAT_PATCH_PACKAGE": str(self.settings.root / "qqnt.json"),
                "NAPCAT_LOAD_PATH": str(loader_path),
                "NAPCAT_INJECT_PATH": str(self.settings.root / "NapCatWinBootHook.dll"),
                "NAPCAT_LAUNCHER_PATH": str(self.settings.root / "NapCatWinBootMain.exe"),
                "NAPCAT_MAIN_PATH": str(main_path).replace("\\", "/"),
            }
        )
        command = [
            str(self.settings.root / "NapCatWinBootMain.exe"),
            str(self.settings.qq_path),
            str(self.settings.root / "NapCatWinBootHook.dll"),
        ]
        if self.settings.quick_account:
            command.extend(["-q", self.settings.quick_account])
        log_path = default_config_dir() / "logs" / "napcat-managed.log"
        capture = ManagedProcessLog(log_path)
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
        try:
            self.process = subprocess.Popen(
                command,
                cwd=self.settings.root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                creationflags=flags,
            )
        except Exception:
            capture.close()
            raise
        self._log_capture = capture
        capture.start(self.process.stdout)
        return True

    def wait_for_webui(
        self, timeout: float = 35.0, *, stop_event: threading.Event | None = None
    ) -> NapCatWebUI:
        client = NapCatWebUI(self.settings.root)
        deadline = time.monotonic() + timeout
        last_error = ""
        while time.monotonic() < deadline:
            if stop_event is not None and stop_event.is_set():
                raise NapCatError("启动已取消")
            if self.process is not None and self.process.poll() is not None:
                raise NapCatError(f"NapCat 启动进程提前退出（代码 {self.process.returncode}）")
            try:
                port = int(client.webui_config.get("port", 6099))
                if port_is_open(port):
                    client.authenticate()
                    return client
            except (NapCatError, ValueError, TypeError) as exc:
                last_error = str(exc)
            if stop_event is None:
                time.sleep(0.5)
            elif stop_event.wait(0.5):
                raise NapCatError("启动已取消")
        raise NapCatError("等待 NapCat WebUI 超时" + (f"：{last_error}" if last_error else ""))

    def stop(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                result = subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    creationflags=flags,
                    check=False,
                    timeout=10.0,
                )
                if result.returncode != 0 and process.poll() is None:
                    raise NapCatError("未能关闭托管的 NapCat/QQ，请重试关闭服务")
                process.wait(timeout=5.0)
            except (OSError, subprocess.TimeoutExpired) as exc:
                if process.poll() is None:
                    raise NapCatError("未能关闭托管的 NapCat/QQ，请重试关闭服务") from exc
        self.process = None
        if self._log_capture is not None:
            self._log_capture.close()
            self._log_capture = None
