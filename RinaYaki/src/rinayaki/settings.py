"""Per-user RinaYaki settings shared by the native and embedded UIs."""
from __future__ import annotations

from dataclasses import dataclass, replace
from contextlib import contextmanager
import json
import os
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_HTTP_API_URL = "https://dashscope.aliyuncs.com/api/v1"
DEFAULT_WEBSOCKET_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
DEFAULT_ASR_MODEL = "qwen-audio-3.1-asr-flash-filetrans"
DEFAULT_LIVE_ENGINE = "asr-mt"
LIVE_ENGINES = {"asr-mt", "livetranslate"}
DEFAULT_TRANSLATION_MODEL = "qwen-mt-flash"
DEFAULT_REFINEMENT_MODEL = "qwen3.8-flash"


@dataclass(frozen=True, slots=True)
class UserSettings:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    http_api_url: str = DEFAULT_HTTP_API_URL
    websocket_url: str = DEFAULT_WEBSOCKET_URL
    minimum_interval_seconds: float = 1.1
    asr_model: str = DEFAULT_ASR_MODEL
    translation_model: str = DEFAULT_TRANSLATION_MODEL
    refinement_model: str = DEFAULT_REFINEMENT_MODEL
    default_project_dir: str = ""
    live_engine: str = DEFAULT_LIVE_ENGINE

    def public(self) -> dict:
        return {
            "hasApiKey": bool(self.api_key),
            "baseUrl": self.base_url,
            "httpApiUrl": self.http_api_url,
            "websocketUrl": self.websocket_url,
            "minimumIntervalSeconds": self.minimum_interval_seconds,
            "asrModel": self.asr_model,
            "translationModel": self.translation_model,
            "refinementModel": self.refinement_model,
            "defaultProjectDir": self.default_project_dir,
            "liveEngine": self.live_engine,
        }

    def runtime_snapshot(self) -> dict:
        return {
            "schema_version": 1,
            "model_defaults_version": 2,
            "base_url": self.base_url,
            "http_api_url": self.http_api_url,
            "websocket_url": self.websocket_url,
            "minimum_interval_seconds": self.minimum_interval_seconds,
            "asr_model": self.asr_model,
            "translation_model": self.translation_model,
            "refinement_model": self.refinement_model,
            "live_engine": self.live_engine,
        }


def default_output_dir(project_root: Path | None = None) -> Path:
    return config_home() / "output"


def config_home() -> Path:
    override = os.getenv("RINAYAKI_CONFIG_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA", "").strip()
        return (Path(base) if base else Path.home() / "AppData/Local") / "OurDeskPet" / "RinaYaki"
    base = os.getenv("XDG_CONFIG_HOME", "").strip()
    return (Path(base) if base else Path.home() / ".config") / "rinayaki"


def _read_env(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return {}
    result = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        result[name.strip()] = value
    return result


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _validate_url(value: str, schemes: set[str], label: str) -> str:
    value = str(value).strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in schemes or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError(f"{label}格式无效。")
    return value


def _validate_model(value: str, label: str) -> str:
    value = str(value).strip()
    if not value or len(value) > 160 or any(ord(character) < 32 for character in value):
        raise ValueError(f"{label}名称无效。")
    return value


def validate_settings(settings: UserSettings) -> UserSettings:
    if settings.live_engine not in LIVE_ENGINES:
        raise ValueError("实时翻译方式无效。")
    try:
        interval = float(settings.minimum_interval_seconds)
    except (TypeError, ValueError) as error:
        raise ValueError("最小请求间隔必须是数字。") from error
    if not 0 <= interval <= 60:
        raise ValueError("最小请求间隔应在 0 到 60 秒之间。")
    project_dir = str(settings.default_project_dir).strip()
    if project_dir:
        path = Path(project_dir).expanduser()
        if not path.is_absolute():
            raise ValueError("默认项目目录必须使用完整路径。")
        project_dir = str(path.resolve(strict=False))
    return replace(
        settings,
        base_url=_validate_url(settings.base_url, {"https"}, "兼容 API 地址"),
        http_api_url=_validate_url(settings.http_api_url, {"https"}, "语音 API 地址"),
        websocket_url=_validate_url(settings.websocket_url, {"wss"}, "实时语音地址"),
        minimum_interval_seconds=interval,
        asr_model=_validate_model(settings.asr_model, "语音识别模型"),
        translation_model=_validate_model(settings.translation_model, "字幕翻译模型"),
        refinement_model=_validate_model(settings.refinement_model, "字幕精修模型"),
        default_project_dir=project_dir,
    )


def load_settings(project_root: Path | None = None) -> UserSettings:
    home = config_home()
    stored = _read_json(home / "settings.json")
    user_env = _read_env(home / "credentials.env")
    legacy = _read_env(project_root / ".env") if project_root is not None else {}
    process = os.environ

    def setting(name: str, env_name: str, default):
        return stored.get(name, process.get(env_name) or legacy.get(env_name) or default)

    key = user_env.get("DASHSCOPE_API_KEY") or process.get("DASHSCOPE_API_KEY") or legacy.get("DASHSCOPE_API_KEY") or ""
    return validate_settings(UserSettings(
        api_key=key.strip(),
        base_url=setting("base_url", "DASHSCOPE_BASE_URL", DEFAULT_BASE_URL),
        http_api_url=setting("http_api_url", "DASHSCOPE_HTTP_API_URL", DEFAULT_HTTP_API_URL),
        websocket_url=setting("websocket_url", "DASHSCOPE_WEBSOCKET_URL", DEFAULT_WEBSOCKET_URL),
        minimum_interval_seconds=setting("minimum_interval_seconds", "DASHSCOPE_MIN_REQUEST_INTERVAL_SECONDS", 1.1),
        # Upgrade the former default for NEW jobs only. Project snapshots retain
        # their original model/task IDs for reproducible resume and retry.
        asr_model=(DEFAULT_ASR_MODEL if stored.get("model_defaults_version", 1) == 1
                   and stored.get("asr_model") == "qwen-audio-3.0-asr-flash-filetrans"
                   else stored.get("asr_model", DEFAULT_ASR_MODEL)),
        translation_model=stored.get("translation_model", DEFAULT_TRANSLATION_MODEL),
        refinement_model=stored.get("refinement_model", DEFAULT_REFINEMENT_MODEL),
        default_project_dir=stored.get("default_project_dir") or str(default_output_dir(project_root)),
        live_engine=stored.get("live_engine", DEFAULT_LIVE_ENGINE),
    ))


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + ".pending")
    try:
        pending.write_text(text, encoding="utf-8", newline="\n")
        try:
            pending.chmod(0o600)
        except OSError:
            pass
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def save_settings(request: dict, project_root: Path | None = None) -> UserSettings:
    current = load_settings(project_root)
    values = {
        "base_url": request.get("baseUrl", current.base_url),
        "http_api_url": request.get("httpApiUrl", current.http_api_url),
        "websocket_url": request.get("websocketUrl", current.websocket_url),
        "minimum_interval_seconds": request.get("minimumIntervalSeconds", current.minimum_interval_seconds),
        "asr_model": request.get("asrModel", current.asr_model),
        "translation_model": request.get("translationModel", current.translation_model),
        "refinement_model": request.get("refinementModel", current.refinement_model),
        "default_project_dir": str(request.get("defaultProjectDir", current.default_project_dir) or "").strip() or str(default_output_dir(project_root)),
        "live_engine": request.get("liveEngine", current.live_engine),
    }
    key = request.get("apiKey")
    if key is None or not str(key).strip():
        key = current.api_key
    updated = validate_settings(UserSettings(api_key=str(key).strip(), **values))
    home = config_home()
    _atomic_write(home / "settings.json", json.dumps({
        **updated.runtime_snapshot(),
        "default_project_dir": "" if Path(updated.default_project_dir) == default_output_dir(project_root) else updated.default_project_dir,
    }, ensure_ascii=False, indent=2) + "\n")
    if updated.api_key:
        _atomic_write(home / "credentials.env", "# Local RinaYaki credential; never commit or share.\nDASHSCOPE_API_KEY=" + updated.api_key + "\n")
    return updated


def apply_runtime_snapshot(settings: UserSettings, snapshot: dict) -> UserSettings:
    if snapshot.get("schema_version") != 1:
        raise ValueError("项目使用了不支持的运行配置版本。")
    return validate_settings(replace(
        settings,
        base_url=snapshot["base_url"],
        http_api_url=snapshot["http_api_url"],
        websocket_url=snapshot.get("websocket_url", DEFAULT_WEBSOCKET_URL),
        minimum_interval_seconds=snapshot["minimum_interval_seconds"],
        asr_model=snapshot["asr_model"],
        translation_model=snapshot["translation_model"],
        refinement_model=snapshot["refinement_model"],
    ))


@contextmanager
def runtime_environment(settings: UserSettings):
    """Expose one validated configuration while legacy client factories run."""
    values = {
        "DASHSCOPE_API_KEY": settings.api_key,
        "DASHSCOPE_BASE_URL": settings.base_url,
        "DASHSCOPE_HTTP_API_URL": settings.http_api_url,
        "DASHSCOPE_WEBSOCKET_URL": settings.websocket_url,
        "DASHSCOPE_MIN_REQUEST_INTERVAL_SECONDS": str(settings.minimum_interval_seconds),
    }
    previous = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
