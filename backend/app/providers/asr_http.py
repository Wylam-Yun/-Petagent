from __future__ import annotations

from pathlib import Path
from time import sleep
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from app.config import ProviderConfig
from app.runtime.voice_types import ASRTranscript

DIRECT_REQUEST_PROXIES = {"http": None, "https": None, "all": None}


def _timeout_tuple(scalar: int, connect: Optional[int] = None, read: Optional[int] = None) -> tuple:
    """Convert a scalar timeout to (connect_timeout, read_timeout) tuple."""
    scalar = _positive_int(scalar, 1)
    if connect is not None or read is not None:
        connect_timeout = _positive_int(connect, min(2, scalar))
        read_timeout = _positive_int(read, max(scalar - min(2, scalar), 1))
        return (connect_timeout, read_timeout)
    connect_timeout = min(2, scalar)
    return (connect_timeout, max(scalar - connect_timeout, 1))


def _positive_int(raw: Any, default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(1, value)


def parse_transcript_json(
    body: Dict[str, Any],
    text_paths: Optional[Iterable[str]] = None,
    confidence_paths: Optional[Iterable[str]] = None,
) -> Tuple[str, float]:
    configured_text = _first_text(body, text_paths or [])
    if configured_text:
        return configured_text, _confidence(
            _first_value(body, confidence_paths or []) or body.get("confidence", 1.0)
        )

    for key in ("text", "transcript", "transcription"):
        text = str(body.get(key) or "").strip()
        if text:
            return text, _confidence(body.get("confidence", 1.0))

    for segment in body.get("segments", []) or []:
        text = str(segment.get("text") or "").strip()
        if text:
            return text, _confidence(segment.get("confidence", body.get("confidence", 1.0)))

    for result in body.get("results", []) or []:
        for alternative in result.get("alternatives", []) or []:
            text = str(
                alternative.get("transcript")
                or alternative.get("text")
                or alternative.get("transcription")
                or ""
            ).strip()
            if text:
                return text, _confidence(alternative.get("confidence", body.get("confidence", 1.0)))

    return "", 0.0


def _first_text(body: Dict[str, Any], paths: Iterable[str]) -> str:
    for path in paths:
        for value in _values_at_path(body, path):
            text = str(value or "").strip()
            if text:
                return text
    return ""


def _first_value(body: Dict[str, Any], paths: Iterable[str]) -> Any:
    for path in paths:
        for value in _values_at_path(body, path):
            if value is not None and value != "":
                return value
    return None


def _values_at_path(body: Dict[str, Any], path: str) -> List[Any]:
    values: List[Any] = [body]
    for raw_part in str(path or "").split("."):
        if not raw_part:
            continue
        expand_list = raw_part.endswith("[]")
        key = raw_part[:-2] if expand_list else raw_part
        next_values: List[Any] = []
        for value in values:
            if key:
                if not isinstance(value, dict) or key not in value:
                    continue
                value = value[key]
            if expand_list:
                if isinstance(value, list):
                    next_values.extend(value)
                else:
                    next_values.append(value)
            else:
                next_values.append(value)
        values = next_values
    return values


def _confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(1.0, value))


class HttpASRProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.name = config.name or "http_asr"

    def transcribe(self, audio_path: Path, content_type: str) -> ASRTranscript:
        if not audio_path.exists():
            return self._error("asr_audio_missing", "ASR input audio file is missing")
        if not self.config.base_url:
            return self._error("asr_not_configured", "ASR base URL is not configured")

        models = self._model_candidates()
        last_transcript = self._error("asr_provider_error", "ASR provider failed")
        attempts = self._max_attempts(models)
        for attempt in range(attempts):
            model = models[min(attempt, len(models) - 1)]
            last_transcript = self._transcribe_once(audio_path, content_type, model)
            if not self._should_retry(last_transcript.error_code, attempt, attempts):
                return last_transcript
            sleep(self._retry_backoff_seconds(attempt))
        return last_transcript

    def _transcribe_once(self, audio_path: Path, content_type: str, model: str) -> ASRTranscript:
        try:
            request_kwargs = self._request_kwargs(audio_path, content_type, model)
            file_handles = request_kwargs.pop("_file_handles", [])
            response = requests.post(
                self._url(),
                **request_kwargs,
            )
            response.raise_for_status()
            text, confidence = parse_transcript_json(
                response.json(),
                text_paths=self.config.extra.get("transcript_paths") or [],
                confidence_paths=self.config.extra.get("confidence_paths") or [],
            )
            if not text.strip():
                return self._error("asr_empty", "ASR provider returned empty transcript")
            return ASRTranscript(text=text, confidence=confidence, provider=self.name)
        except requests.Timeout:
            return self._error("asr_timeout", "ASR HTTP request timed out")
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status:
                return self._error(
                    "asr_http_%s" % status,
                    "ASR HTTP request failed with status %s" % status,
                )
            return self._error("asr_http_error", "ASR HTTP request failed")
        except requests.RequestException:
            return self._error("asr_request_error", "ASR HTTP request failed")
        except ValueError:
            return self._error("asr_bad_response", "ASR HTTP response was not valid JSON")
        except Exception:
            return self._error("asr_provider_error", "ASR provider failed")
        finally:
            for handle in locals().get("file_handles", []):
                handle.close()

    def _model_candidates(self) -> List[str]:
        models = [self.config.model]
        fallback_models = self.config.extra.get("fallback_models") or []
        if isinstance(fallback_models, str):
            fallback_models = [fallback_models]
        if isinstance(fallback_models, list):
            models.extend(str(model) for model in fallback_models)
        deduped: List[str] = []
        for model in models:
            model = str(model or "").strip()
            if model and model not in deduped:
                deduped.append(model)
        return deduped or [self.config.model]

    def _max_attempts(self, models: List[str]) -> int:
        try:
            retries = int(self.config.extra.get("transient_retries", 0))
        except (TypeError, ValueError):
            retries = 0
        return max(1, min(3, max(retries + 1, len(models))))

    def _retry_backoff_seconds(self, attempt: int) -> float:
        try:
            base = float(self.config.extra.get("retry_backoff_seconds", 0.25))
        except (TypeError, ValueError):
            base = 0.25
        return max(0.0, min(2.0, base * (attempt + 1)))

    def _should_retry(self, error_code: str, attempt: int, attempts: int) -> bool:
        if not error_code or attempt >= attempts - 1:
            return False
        if error_code in {"asr_request_error", "asr_provider_error", "asr_empty", "asr_timeout"}:
            return True
        if error_code.startswith("asr_http_"):
            try:
                status = int(error_code.rsplit("_", 1)[1])
            except (IndexError, ValueError):
                return False
            return 500 <= status <= 599
        return False

    def _error(self, code: str, message: str) -> ASRTranscript:
        return ASRTranscript(
            text="",
            confidence=0.0,
            provider=self.name,
            error_code=code,
            error_message=message,
        )

    def _request_kwargs(self, audio_path: Path, content_type: str, model: str) -> Dict[str, Any]:
        request_format = str(
            self.config.extra.get("request_format") or "multipart"
        ).lower()
        common = {
            "headers": self._headers(
                content_type if request_format == "binary" else None
            ),
            "params": self._params(),
            "proxies": DIRECT_REQUEST_PROXIES,
            "timeout": _timeout_tuple(
                self.config.timeout_seconds,
                connect=self.config.extra.get("connect_timeout_seconds"),
                read=self.config.extra.get("read_timeout_seconds"),
            ),
        }
        if request_format == "binary":
            common["data"] = audio_path.read_bytes()
            return common

        file_field = str(self.config.extra.get("file_field") or "file")
        handle = audio_path.open("rb")
        common["data"] = self._data(model)
        common["files"] = {
            file_field: (
                audio_path.name,
                handle,
                content_type or "application/octet-stream",
            )
        }
        common["_file_handles"] = [handle]
        return common

    def _url(self) -> str:
        endpoint = str(self.config.extra.get("endpoint") or "/v1/audio/transcriptions")
        return self.config.base_url.rstrip("/") + "/" + endpoint.lstrip("/")

    def _headers(self, content_type: Optional[str] = None) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        configured_headers = self.config.extra.get("headers") or {}
        if isinstance(configured_headers, dict):
            headers.update(
                {str(key): str(value) for key, value in configured_headers.items()}
            )
        if content_type:
            headers["Content-Type"] = content_type

        if not self.config.api_key:
            return headers
        scheme = str(self.config.extra.get("auth_scheme") or "bearer").lower()
        if scheme == "none":
            return headers
        if scheme == "custom":
            header = str(self.config.extra.get("api_key_header") or "Authorization")
            prefix = str(self.config.extra.get("api_key_prefix") or "")
            headers[header] = ("%s %s" % (prefix, self.config.api_key)).strip()
            return headers
        if scheme == "api-key":
            header = str(self.config.extra.get("api_key_header") or "api-key")
            headers[header] = self.config.api_key
            return headers
        headers["Authorization"] = "Bearer %s" % self.config.api_key
        return headers

    def _data(self, model: str) -> Dict[str, str]:
        data: Dict[str, str] = {}
        model_field = self.config.extra.get("model_field", "model")
        language_field = self.config.extra.get("language_field", "language")
        if model_field:
            data[str(model_field)] = model
        if language_field:
            data[str(language_field)] = str(
                self.config.extra.get("language_code") or "zh-CN"
            )
        form_fields = self.config.extra.get("form_fields") or {}
        if isinstance(form_fields, dict):
            data.update({str(key): str(value) for key, value in form_fields.items()})
        for key in ("response_format", "temperature", "prompt"):
            value = self.config.extra.get(key)
            if value is not None and value != "":
                data[key] = str(value)
        return data

    def _params(self) -> Dict[str, str]:
        query_params = self.config.extra.get("query_params") or {}
        if not isinstance(query_params, dict):
            return {}
        return {str(key): str(value) for key, value in query_params.items()}
