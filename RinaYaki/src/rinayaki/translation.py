"""Translation and conservative subtitle-refinement providers."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from collections.abc import Callable
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from .retry import request_with_retry
from .billing import record as record_billing


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
SUBTITLE_DOMAIN = (
    "These are short timed subtitles from online video. Translate naturally and concisely "
    "for on-screen reading. Preserve meaning, tone, names, numbers, and established terms. "
    "Do not add explanations."
)


class DashScopeApiError(RuntimeError):
    """An API response failed without exposing authorization credentials."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class ApiResult:
    model: str
    content: str
    elapsed_seconds: float
    usage: Mapping[str, Any]
    response_id: str | None
    finish_reason: str | None


def load_dotenv(path: Path) -> None:
    """Load a small, conventional .env file without overriding the process."""

    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if name:
            os.environ.setdefault(name, value)


class DashScopeOpenAIClient:
    """Minimal OpenAI-compatible client for the DashScope shared endpoint."""

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, *, minimum_interval_seconds: float | None = None) -> None:
        if not api_key:
            raise ValueError("DASHSCOPE_API_KEY is empty")
        if not base_url.startswith("https://"):
            raise ValueError("DASHSCOPE_BASE_URL must use HTTPS")
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        # Keep sustained jobs below the common per-minute request boundary.
        # A long programme can contain hundreds of batches and otherwise reaches
        # the provider faster than its rolling limit can recover.
        configured_interval = (os.getenv("DASHSCOPE_MIN_REQUEST_INTERVAL_SECONDS", "1.1")
                               if minimum_interval_seconds is None else minimum_interval_seconds)
        try:
            self._minimum_interval_seconds = max(0.0, float(configured_interval))
        except ValueError:
            self._minimum_interval_seconds = 1.1
        self._last_request_started = 0.0

    def _wait_for_request_slot(self) -> None:
        remaining = self._minimum_interval_seconds - (time.monotonic() - self._last_request_started)
        if remaining > 0:
            time.sleep(remaining)
        self._last_request_started = time.monotonic()

    @classmethod
    def from_environment(cls, *, dotenv_path: Path | None = None) -> "DashScopeOpenAIClient":
        if dotenv_path is not None:
            load_dotenv(dotenv_path)
        return cls(
            api_key=os.getenv("DASHSCOPE_API_KEY", "").strip(),
            base_url=os.getenv("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL).strip()
            or DEFAULT_BASE_URL,
        )

    def chat_completions(
        self, payload: Mapping[str, Any], *, timeout_seconds: float = 180
    ) -> ApiResult:
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.perf_counter()
        try:
            self._wait_for_request_slot()
            with request_with_retry(
                lambda: urlopen(request, timeout=timeout_seconds),
                on_retry=lambda attempt, delay, _error: print(
                    f"DashScope rate limit: waiting {delay:g}s before retry {attempt}/5...",
                    flush=True,
                ),
            ) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise DashScopeApiError(
                f"DashScope returned HTTP {error.code}: {body[:1000]}",
                status=error.code,
            ) from error
        except URLError as error:
            raise DashScopeApiError(f"Could not reach DashScope: {error.reason}") from error

        elapsed = time.perf_counter() - started
        try:
            data = json.loads(response_body)
            message = data["choices"][0]["message"]
            content = message["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise DashScopeApiError(
                f"Unexpected DashScope response: {response_body[:1000]}"
            ) from error
        if not isinstance(content, str):
            raise DashScopeApiError("DashScope returned non-text message content")
        usage = data.get("usage") or {}
        record_billing(self.base_url, self._api_key, payload.get('model', ''), usage, data.get('id'))
        return ApiResult(
            model=str(data.get("model") or payload.get("model") or ""),
            content=content.strip(),
            elapsed_seconds=elapsed,
            usage=usage if isinstance(usage, Mapping) else {},
            response_id=data.get("id"),
            finish_reason=data["choices"][0].get("finish_reason"),
        )

    def chat_completions_stream(
        self,
        payload: Mapping[str, Any],
        *,
        on_update: Callable[[str], None],
        timeout_seconds: float = 180,
    ) -> ApiResult:
        """Stream a chat completion and publish reconstructed text snapshots.

        Qwen-MT Flash/Lite send incremental deltas, while Plus/Turbo send the
        complete text-so-far in each chunk. The caller always receives one
        reconstructed snapshot, including corrections from cumulative models.
        """
        body = dict(payload)
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        started = time.perf_counter()
        model = str(body.get("model") or "")
        incremental = not model.startswith(("qwen-mt-plus", "qwen-mt-turbo"))
        content = ""
        usage: Mapping[str, Any] = {}
        response_id = None
        finish_reason = None
        completed = False
        try:
            self._wait_for_request_slot()
            with request_with_retry(
                lambda: urlopen(request, timeout=timeout_seconds),
                on_retry=lambda attempt, delay, _error: print(
                    f"DashScope rate limit: waiting {delay:g}s before retry {attempt}/5...",
                    flush=True,
                ),
            ) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or line.startswith(":") or not line.startswith("data:"):
                        continue
                    data_text = line[5:].strip()
                    if data_text == "[DONE]":
                        completed = True
                        break
                    try:
                        data = json.loads(data_text)
                    except json.JSONDecodeError as error:
                        raise DashScopeApiError("DashScope returned an invalid stream chunk") from error
                    if not isinstance(data, dict) or data.get("error"):
                        raise DashScopeApiError("DashScope returned a stream error")
                    response_id = data.get("id") or response_id
                    model = str(data.get("model") or model)
                    raw_usage = data.get("usage")
                    if isinstance(raw_usage, Mapping):
                        usage = raw_usage
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    finish_reason = choice.get("finish_reason") or finish_reason
                    if finish_reason and finish_reason != "stop":
                        raise DashScopeApiError("DashScope translation did not finish normally")
                    piece = (choice.get("delta") or {}).get("content")
                    if not isinstance(piece, str) or not piece:
                        continue
                    updated = _merge_stream_content(content, piece, incremental=incremental)
                    if updated != content:
                        content = updated
                        on_update(content)
        except HTTPError as error:
            body_text = error.read().decode("utf-8", errors="replace")
            raise DashScopeApiError(
                f"DashScope returned HTTP {error.code}: {body_text[:1000]}",
                status=error.code,
            ) from error
        except URLError as error:
            raise DashScopeApiError(f"Could not reach DashScope: {error.reason}") from error
        if not completed and finish_reason != "stop":
            raise DashScopeApiError("DashScope translation stream was interrupted")
        if not content.strip():
            raise DashScopeApiError("DashScope returned an empty translation stream")
        record_billing(self.base_url, self._api_key, payload.get('model', ''), usage, response_id)
        return ApiResult(
            model=model,
            content=content.strip(),
            elapsed_seconds=time.perf_counter() - started,
            usage=usage,
            response_id=response_id,
            finish_reason=finish_reason,
        )


def _merge_stream_content(current: str, piece: str, *, incremental: bool) -> str:
    if incremental:
        return current + piece
    return piece


def qwen_mt_payload(
    text: str,
    *,
    model: str = "qwen-mt-flash",
    source_language: str = "Japanese",
    target_language: str = "Chinese",
    terms: list[dict[str, str]] | None = None,
    domain_hint: str = "",
) -> dict[str, Any]:
    """Build the exact single-user-message payload required by Qwen-MT."""

    if not text.strip():
        raise ValueError("text must not be empty")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": text}],
        "translation_options": {
            "source_lang": source_language,
            "target_lang": target_language,
        },
    }
    if terms:
        payload['translation_options']['terms'] = terms
    if not model.startswith('qwen-mt-lite'):
        payload['translation_options']['domains'] = SUBTITLE_DOMAIN + (' ' + domain_hint if domain_hint else '')
    return payload


REFINEMENT_SYSTEM_PROMPT = """你是日语视频中文字幕的保守校对员。
对照日文原文，只修正直译腔、指代、语序、标点、人名和术语一致性。
不得增加原文没有的信息，不得删减信息，不得解释，不得改变说话语气。
只输出最终的简体中文字幕，不要标题、引号、注释或 Markdown。"""


def refinement_payload(
    source_text: str,
    draft_translation: str,
    *,
    model: str,
    reasoning_effort: str,
    max_completion_tokens: int | None = None,
) -> dict[str, Any]:
    """Build a comparable refinement request for OpenAI-compatible models."""

    if not source_text.strip() or not draft_translation.strip():
        raise ValueError("source_text and draft_translation must not be empty")
    if max_completion_tokens is None:
        max_completion_tokens = 512 if reasoning_effort == "none" else 4096
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": REFINEMENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "日文原文：\n"
                    f"{source_text}\n\n"
                    "待校对译文：\n"
                    f"{draft_translation}"
                ),
            },
        ],
        "reasoning_effort": reasoning_effort,
        # Includes both reasoning and visible answer for reasoning models.
        "max_completion_tokens": max_completion_tokens,
    }
