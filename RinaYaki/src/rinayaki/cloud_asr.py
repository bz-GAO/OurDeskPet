"""Alibaba Model Studio Qwen-Audio ASR clients."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import mimetypes
import os
from pathlib import Path
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .translation import load_dotenv
from .retry import request_with_retry
from .billing import record as record_billing


SHORT_FILE_MODEL = "qwen-audio-3.0-asr-flash"
FILETRANS_MODEL = "qwen-audio-3.1-asr-flash-filetrans"
STREAMING_MODEL = "qwen-audio-3.0-asr-flash-streaming"
DEFAULT_HTTP_API_URL = "https://dashscope.aliyuncs.com/api/v1"
DEFAULT_WEBSOCKET_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"


class CloudAsrError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class CloudAsrResult:
    model: str
    text: str
    sentences: tuple[Mapping[str, Any], ...]
    usage: Mapping[str, Any]
    elapsed_seconds: float
    request_id: str | None
    metrics: Mapping[str, Any]


def _audio_format(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "mp3":
        return "mp3", "audio/mpeg"
    if suffix == "wav":
        return "wav", "audio/wav"
    mime = mimetypes.guess_type(path.name)[0] or f"audio/{suffix}"
    return suffix, mime


def audio_data_uri(path: Path) -> tuple[str, str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    format_name, mime = _audio_format(path)
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return format_name, f"data:{mime};base64,{encoded}"


def short_file_payload(
    data_uri: str,
    *,
    audio_format: str,
    sample_rate: int = 16_000,
    language_hints: tuple[str, ...] = ("ja",),
    vocabulary: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "format": audio_format,
        "sample_rate": str(sample_rate),
        "language_hints": list(language_hints),
    }
    if vocabulary:
        parameters["vocabulary"] = dict(vocabulary)
    return {
        "model": SHORT_FILE_MODEL,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_audio", "input_audio": {"data": data_uri}}
                    ],
                }
            ]
        },
        "parameters": parameters,
    }


def filetrans_payload(
    file_url: str,
    *,
    model: str = FILETRANS_MODEL,
    language_hints: tuple[str, ...] = ("ja",),
    diarization_enabled: bool = True,
    speaker_count: int | None = None,
    vocabulary: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    parsed = urlparse(file_url)
    if parsed.scheme not in {"http", "https", "oss"}:
        raise ValueError("Filetrans requires an HTTP(S) or DashScope oss:// file URL")
    parameters: dict[str, Any] = {
        "channel_id": [0],
        "diarization_enabled": diarization_enabled,
    }
    if language_hints:
        parameters["language_hints"] = list(language_hints)
    if speaker_count is not None:
        if not 2 <= speaker_count <= 100:
            raise ValueError("speaker_count must be between 2 and 100")
        parameters["speaker_count"] = speaker_count
    if vocabulary:
        parameters["vocabulary"] = dict(vocabulary)
    return {
        "model": model,
        "input": {"file_urls": [file_url]},
        "parameters": parameters,
    }


class QwenAudioAsrClient:
    def __init__(
        self,
        api_key: str,
        *,
        http_api_url: str = DEFAULT_HTTP_API_URL,
        websocket_url: str = DEFAULT_WEBSOCKET_URL,
    ) -> None:
        if not api_key:
            raise ValueError("DASHSCOPE_API_KEY is empty")
        self._api_key = api_key
        self.http_api_url = http_api_url.rstrip("/")
        self.websocket_url = websocket_url

    @classmethod
    def from_environment(cls, *, dotenv_path: Path | None = None) -> "QwenAudioAsrClient":
        if dotenv_path is not None:
            load_dotenv(dotenv_path)
        return cls(
            os.getenv("DASHSCOPE_API_KEY", "").strip(),
            http_api_url=os.getenv("DASHSCOPE_HTTP_API_URL", DEFAULT_HTTP_API_URL).strip()
            or DEFAULT_HTTP_API_URL,
            websocket_url=os.getenv("DASHSCOPE_WEBSOCKET_URL", DEFAULT_WEBSOCKET_URL).strip()
            or DEFAULT_WEBSOCKET_URL,
        )

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        payload: Mapping[str, Any] | None = None,
        extra_headers: Mapping[str, str] | None = None,
        timeout_seconds: float = 180,
        authorization: bool = True,
    ) -> Mapping[str, Any]:
        headers: dict[str, str] = {}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if authorization:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if extra_headers:
            headers.update(extra_headers)
        request = Request(
            url,
            data=(
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
                if payload is not None
                else None
            ),
            headers=headers,
            method=method,
        )
        try:
            with request_with_retry(lambda: urlopen(request, timeout=timeout_seconds), safe_read=method == 'GET') as response:
                body = response.read().decode("utf-8")
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            if not authorization:
                raise CloudAsrError(
                    f"ASR result download returned HTTP {error.code}", status=error.code
                ) from error
            raise CloudAsrError(
                f"ASR API returned HTTP {error.code}: {body[:1000]}", status=error.code
            ) from error
        except URLError as error:
            raise CloudAsrError(f"Could not reach ASR API: {error.reason}") from error
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as error:
            raise CloudAsrError(f"ASR API returned invalid JSON: {body[:1000]}") from error
        if not isinstance(parsed, Mapping):
            raise CloudAsrError("ASR API returned an unexpected JSON value")
        return parsed

    def recognize_short_file(
        self,
        audio_path: Path,
        *,
        language_hints: tuple[str, ...] = ("ja",),
        vocabulary: Mapping[str, int] | None = None,
    ) -> CloudAsrResult:
        audio_format, data_uri = audio_data_uri(audio_path)
        payload = short_file_payload(
            data_uri,
            audio_format=audio_format,
            language_hints=language_hints,
            vocabulary=vocabulary,
        )
        started = time.perf_counter()
        response = self._request_json(
            "POST",
            f"{self.http_api_url}/services/aigc/multimodal-generation/generation",
            payload=payload,
            extra_headers={"X-DashScope-SSE": "disable"},
        )
        output = response.get("output") or {}
        sentence = output.get("sentence") or {}
        record_billing(self.http_api_url, self._api_key, SHORT_FILE_MODEL, response.get('usage'), response.get('request_id'))
        return CloudAsrResult(
            model=SHORT_FILE_MODEL,
            text=str(output.get("text") or sentence.get("text") or "").strip(),
            sentences=(sentence,) if sentence else (),
            usage=response.get("usage") or {},
            elapsed_seconds=time.perf_counter() - started,
            request_id=response.get("request_id"),
            metrics={},
        )

    def recognize_filetrans(
        self,
        file_url: str,
        *,
        model: str = FILETRANS_MODEL,
        language_hints: tuple[str, ...] = ("ja",),
        diarization_enabled: bool = True,
        speaker_count: int | None = None,
        vocabulary: Mapping[str, int] | None = None,
        timeout_seconds: float = 300,
        poll_interval_seconds: float = 2,
        resume_task_id: str | None = None,
        on_submitted=None,
        on_status=None,
    ) -> CloudAsrResult:
        payload = None if resume_task_id else filetrans_payload(
            file_url,
            model=model,
            language_hints=language_hints,
            diarization_enabled=diarization_enabled,
            speaker_count=speaker_count,
            vocabulary=vocabulary,
        )
        started = time.perf_counter()
        submitted = {"output": {"task_id": resume_task_id}} if resume_task_id else self._request_json(
            "POST",
            f"{self.http_api_url}/services/audio/asr/transcription",
            payload=payload,
            extra_headers={
                "X-DashScope-Async": "enable",
                **(
                    {"X-DashScope-OssResourceResolve": "enable"}
                    if urlparse(file_url).scheme == "oss"
                    else {}
                ),
            },
        )
        task_id = (submitted.get("output") or {}).get("task_id")
        if not task_id:
            raise CloudAsrError("Filetrans submission returned no task_id")
        if on_submitted is not None:
            on_submitted(task_id)

        deadline = time.monotonic() + timeout_seconds
        task: Mapping[str, Any] = {}
        while time.monotonic() < deadline:
            task = self._request_json("GET", f"{self.http_api_url}/tasks/{task_id}")
            output = task.get("output") or {}
            status = output.get("task_status")
            if on_status is not None:
                on_status(status)
            if status in {"SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"}:
                break
            time.sleep(poll_interval_seconds)
        else:
            raise CloudAsrError("Filetrans task timed out")

        output = task.get("output") or {}
        if output.get("task_status") != "SUCCEEDED":
            code = output.get("code") or task.get("code")
            message = output.get("message") or task.get("message")
            results = output.get("results") or []
            if results:
                code = results[0].get("code") or code
                message = results[0].get("message") or message
            detail = " ".join(str(value) for value in (code, message) if value)
            suffix = f": {detail}" if detail else ""
            raise CloudAsrError(
                f"Filetrans task ended as {output.get('task_status')}{suffix}"
            )
        results = output.get("results") or []
        if not results or results[0].get("subtask_status") != "SUCCEEDED":
            detail = results[0] if results else {}
            raise CloudAsrError(
                f"Filetrans subtask failed: {detail.get('code')} {detail.get('message')}"
            )
        transcription_url = results[0].get("transcription_url")
        if not transcription_url:
            raise CloudAsrError("Filetrans returned no transcription result URL")
        transcript = self._request_json(
            "GET", transcription_url, authorization=False, timeout_seconds=60
        )
        transcripts = transcript.get("transcripts") or []
        sentences: list[Mapping[str, Any]] = []
        texts: list[str] = []
        for channel in transcripts:
            if channel.get("text"):
                texts.append(str(channel["text"]))
            sentences.extend(channel.get("sentences") or [])
        record_billing(self.http_api_url, self._api_key, model, task.get('usage'), task_id)
        return CloudAsrResult(
            model=model,
            text="\n".join(texts).strip(),
            sentences=tuple(sentences),
            usage=task.get("usage") or {},
            elapsed_seconds=time.perf_counter() - started,
            request_id=task.get("request_id") or submitted.get("request_id"),
            metrics={
                "task_status": output.get("task_status"),
                "source_host": urlparse(file_url).hostname,
                "diarization_enabled": diarization_enabled,
            },
        )

    def upload_temporary_file(
        self,
        file_path: Path,
        *,
        model: str = FILETRANS_MODEL,
        timeout_seconds: float = 180,
    ) -> str:
        """Upload a local inference file to DashScope's 48-hour temporary storage."""

        if not file_path.is_file():
            raise FileNotFoundError(file_path)
        credential = self._request_json(
            "GET",
            f"{self.http_api_url}/uploads?action=getPolicy&model={quote(model)}",
        )
        data = credential.get("data") or {}
        required = (
            "upload_host",
            "upload_dir",
            "oss_access_key_id",
            "policy",
            "signature",
            "x_oss_object_acl",
            "x_oss_forbid_overwrite",
        )
        missing = [name for name in required if not data.get(name)]
        if missing:
            raise CloudAsrError(
                f"Temporary upload credential is missing: {', '.join(missing)}"
            )

        try:
            import requests
        except ImportError as error:
            raise CloudAsrError("requests is required for temporary file upload") from error

        object_key = f"{str(data['upload_dir']).rstrip('/')}/{file_path.name}"
        form = {
            "OSSAccessKeyId": data["oss_access_key_id"],
            "policy": data["policy"],
            "Signature": data["signature"],
            "key": object_key,
            "x-oss-object-acl": data["x_oss_object_acl"],
            "x-oss-forbid-overwrite": data["x_oss_forbid_overwrite"],
            "success_action_status": "200",
        }
        _format_name, mime = _audio_format(file_path)
        try:
            with file_path.open("rb") as stream:
                response = requests.post(
                    str(data["upload_host"]),
                    data=form,
                    files={"file": (file_path.name, stream, mime)},
                    timeout=timeout_seconds,
                )
        except requests.RequestException as error:
            raise CloudAsrError(f"Temporary file upload failed: {error}") from error
        if response.status_code != 200:
            raise CloudAsrError(
                f"Temporary file upload returned HTTP {response.status_code}: "
                f"{response.text[:1000]}",
                status=response.status_code,
            )
        return f"oss://{object_key}"

    def recognize_streaming_file(
        self,
        audio_path: Path,
        *,
        language_hints: tuple[str, ...] = ("ja",),
        vocabulary: Mapping[str, int] | None = None,
        realtime_factor: float = 1.0,
    ) -> CloudAsrResult:
        if realtime_factor <= 0:
            raise ValueError("realtime_factor must be positive")
        try:
            import dashscope
            from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult
        except ImportError as error:
            raise CloudAsrError("DashScope SDK is required for streaming ASR") from error

        audio_format, _mime = _audio_format(audio_path)
        final_sentences: list[Mapping[str, Any]] = []
        usage: dict[str, Any] = {}
        callback_error: list[str] = []

        class Collector(RecognitionCallback):
            def on_complete(self) -> None:
                return None

            def on_error(self, result: RecognitionResult) -> None:
                callback_error.append(str(getattr(result, "message", result)))

            def on_event(self, result: RecognitionResult) -> None:
                sentence = result.get_sentence()
                if sentence and RecognitionResult.is_sentence_end(sentence):
                    final_sentences.append(dict(sentence))
                    result_usage = result.get_usage(sentence)
                    if result_usage:
                        usage.update(dict(result_usage))

        dashscope.api_key = self._api_key
        dashscope.base_websocket_api_url = self.websocket_url
        callback = Collector()
        recognition = Recognition(
            model=STREAMING_MODEL,
            format=audio_format,
            sample_rate=16_000,
            language_hints=list(language_hints),
            vocabulary=dict(vocabulary) if vocabulary else None,
            semantic_punctuation_enabled=False,
            callback=callback,
        )
        started = time.perf_counter()
        recognition.start()
        with audio_path.open("rb") as stream:
            while chunk := stream.read(3_200):
                recognition.send_audio_frame(chunk)
                time.sleep(0.1 / realtime_factor)
        recognition.stop()
        if callback_error:
            raise CloudAsrError(f"Streaming ASR failed: {callback_error[-1]}")
        text = "".join(str(sentence.get("text") or "") for sentence in final_sentences).strip()
        record_billing(self.http_api_url, self._api_key, STREAMING_MODEL, usage, recognition.get_last_request_id())
        return CloudAsrResult(
            model=STREAMING_MODEL,
            text=text,
            sentences=tuple(final_sentences),
            usage=usage,
            elapsed_seconds=time.perf_counter() - started,
            request_id=recognition.get_last_request_id(),
            metrics={
                "first_package_delay_ms": recognition.get_first_package_delay(),
                "last_package_delay_ms": recognition.get_last_package_delay(),
                "realtime_factor": realtime_factor,
            },
        )
