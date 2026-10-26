"""OpenAI-compatible client, credentials and durable token guard for Tomo."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import aiohttp
from .billing import record as record_billing

from .config import LlmConfig

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
ENV_KEY_NAME = "DASHSCOPE_API_KEY"
ENV_BASE_URL_NAME = "DASHSCOPE_BASE_URL"
ENV_MODEL_NAME = "DASHSCOPE_MODEL"
DOTENV_FILENAME = ".env"
USAGE_FILENAME = "llm-usage.json"
PROJECT_ENV_PATH = Path(__file__).resolve().parents[2] / DOTENV_FILENAME

ChatMessage = Mapping[str, str]


class LlmError(RuntimeError):
    """Raised for transport, HTTP, or malformed-response failures."""


class ApiKeyMissing(LlmError):
    """Raised when no API key is configured."""


def read_env_file(path: Path) -> dict[str, str]:
    """Read a small dotenv file without mutating the process environment."""
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if name and value:
            result[name] = value
    return result


def resolve_api_settings(config_dir: Path | None = None) -> tuple[str, str]:
    """Resolve credentials without ever copying them into application config.

    Precedence is process environment, private config directory, then the
    gitignored project .env used by developers.
    """
    file_values = _env_file_values(config_dir)
    api_key = os.environ.get(ENV_KEY_NAME, "").strip() or file_values.get(ENV_KEY_NAME, "").strip()
    if not api_key:
        raise ApiKeyMissing(
            f"{ENV_KEY_NAME} is empty; configure it in the environment, "
            "the private config directory, or the gitignored project .env"
        )
    base_url = (
        os.environ.get(ENV_BASE_URL_NAME, "").strip()
        or file_values.get(ENV_BASE_URL_NAME, "").strip()
        or DEFAULT_BASE_URL
    )
    return api_key, _validate_base_url(base_url)


def resolve_model_name(default_model: str, config_dir: Path | None = None) -> str:
    """Return the optional environment model override or the config default."""
    file_values = _env_file_values(config_dir)
    return (
        os.environ.get(ENV_MODEL_NAME, "").strip()
        or file_values.get(ENV_MODEL_NAME, "").strip()
        or default_model
    )


def _env_file_values(config_dir: Path | None) -> dict[str, str]:
    values = read_env_file(PROJECT_ENV_PATH)
    if config_dir is not None:
        private_path = config_dir / DOTENV_FILENAME
        if private_path.resolve(strict=False) != PROJECT_ENV_PATH.resolve(strict=False):
            values.update(read_env_file(private_path))
    return values


def _validate_base_url(value: str) -> str:
    error = "LLM base URL must be an http(s) address without credentials, query, or fragment"
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise LlmError(error) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise LlmError(error)
    return value.rstrip("/")


@dataclass(frozen=True)
class Completion:
    text: str
    total_tokens: int


@dataclass(frozen=True)
class BudgetReservation:
    tokens: int


class TokenBudget:
    """Daily guard with reservation and a tiny durable counter."""

    def __init__(self, daily_limit: int, state_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._daily_limit = daily_limit
        self._state_path = state_path
        self._day = self._today()
        self._used = 0
        self._reserved = 0
        with self._lock:
            self._load()

    @staticmethod
    def _today() -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    @property
    def used(self) -> int:
        with self._lock:
            self._rollover()
            return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            self._rollover()
            return max(0, self._daily_limit - self._used - self._reserved)

    def set_limit(self, daily_limit: int) -> None:
        with self._lock:
            self._rollover()
            self._daily_limit = daily_limit

    def try_reserve(self, tokens: int) -> BudgetReservation | None:
        with self._lock:
            self._rollover()
            amount = max(1, int(tokens))
            remaining = max(0, self._daily_limit - self._used - self._reserved)
            if amount > remaining:
                return None
            self._reserved += amount
            return BudgetReservation(amount)

    def settle(self, reservation: BudgetReservation, actual_tokens: int | None) -> None:
        with self._lock:
            self._rollover()
            self._reserved = max(0, self._reserved - reservation.tokens)
            charged = reservation.tokens if not actual_tokens or actual_tokens < 1 else int(actual_tokens)
            self._used += charged
            self._persist()

    def cancel(self, reservation: BudgetReservation) -> None:
        with self._lock:
            self._rollover()
            self._reserved = max(0, self._reserved - reservation.tokens)

    def snapshot(self) -> dict[str, int]:
        """Read-only usage view for status surfaces; safe to call repeatedly."""
        with self._lock:
            self._rollover()
            return {
                "used": self._used,
                "dailyLimit": self._daily_limit,
                "remaining": max(0, self._daily_limit - self._used - self._reserved),
            }

    def _rollover(self) -> None:
        today = self._today()
        if today == self._day:
            return
        self._day = today
        self._used = 0
        self._reserved = 0
        self._persist()
        log.info("llm token budget reset for %s", today)

    def _load(self) -> None:
        if self._state_path is None or not self._state_path.is_file():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            if data.get("day") == self._day:
                used = data.get("used", 0)
                if isinstance(used, int) and not isinstance(used, bool) and used >= 0:
                    self._used = used
        except (OSError, json.JSONDecodeError, AttributeError):
            log.warning("ignoring unreadable LLM usage state at %s", self._state_path)

    def _persist(self) -> None:
        if self._state_path is None:
            return
        pending = self._state_path.with_name(self._state_path.name + ".pending")
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            pending.write_text(
                json.dumps({"day": self._day, "used": self._used}) + "\n",
                encoding="utf-8",
            )
            os.replace(pending, self._state_path)
        except OSError as exc:
            log.warning("could not persist LLM usage state: %s", exc)
        finally:
            try:
                pending.unlink(missing_ok=True)
            except OSError as exc:
                log.warning("could not clean up pending LLM usage state: %s", exc)


def estimate_request_tokens(messages: Sequence[ChatMessage], max_output_tokens: int) -> int:
    """Conservative local estimate used only to reserve the daily guard."""
    content_chars = sum(len(str(message.get("content", ""))) for message in messages)
    return max(1, content_chars + max_output_tokens)


def read_usage_snapshot(daily_limit: int, config_dir: Path | None) -> dict[str, int]:
    """Usage view without a live responder: loads llm-usage.json directly.

    Used by the panel and control status when the message service is stopped;
    the durable file is the same one a live TokenBudget persists to.
    """
    if config_dir is None:
        return {"used": 0, "dailyLimit": daily_limit, "remaining": daily_limit}
    return TokenBudget(daily_limit, config_dir / USAGE_FILENAME).snapshot()


class LlmClient:
    """One async OpenAI-compatible chat-completions caller."""

    def __init__(self, api_key: str, base_url: str, config: LlmConfig) -> None:
        self._api_key = api_key
        self._url = _validate_base_url(base_url) + "/chat/completions"
        self._config = config

    async def complete(
        self,
        session: aiohttp.ClientSession,
        messages: Sequence[ChatMessage],
    ) -> Completion:
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": [dict(message) for message in messages],
            "max_tokens": self._config.max_tokens,
        }
        timeout = aiohttp.ClientTimeout(total=self._config.timeout_seconds)
        started = time.perf_counter()
        try:
            async with session.post(
                self._url,
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=timeout,
            ) as response:
                body = await response.text()
                if response.status != 200:
                    raise LlmError(f"LLM endpoint returned HTTP {response.status}")
        except aiohttp.ClientError as exc:
            raise LlmError(f"could not reach LLM endpoint: {type(exc).__name__}") from exc
        except TimeoutError as exc:
            raise LlmError("LLM request timed out") from exc
        log.info("llm completion took %.2fs", time.perf_counter() - started)
        try:
            billed = json.loads(body)
            record_billing(self._url, self._api_key, self._config.model, billed.get('usage'), billed.get('id'))
        except (ValueError, TypeError, AttributeError):
            record_billing(self._url, self._api_key, self._config.model, None)
        return _parse_completion(body)


def _parse_completion(body: str) -> Completion:
    try:
        data = json.loads(body)
        text = str(data["choices"][0]["message"]["content"]).strip()
        total_tokens = int(data.get("usage", {}).get("total_tokens") or 0)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise LlmError("malformed LLM response") from exc
    return Completion(text=text, total_tokens=max(0, total_tokens))
