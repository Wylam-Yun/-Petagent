from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from uuid import uuid4

if TYPE_CHECKING:
    from app.runtime.audio_job_store import AudioJobStore
    from app.runtime.concurrency import ProviderGate

logger = logging.getLogger(__name__)

AUDIO_JOB_TERMINAL = {"ready", "failed", "expired", "superseded",
                       "failed_runtime_restart", "failed_shutdown"}

# Map ProviderError subclass error_class to audio error_class
_PROVIDER_ERROR_TO_AUDIO_CLASS: Dict[str, str] = {
    "provider_network_error": "network",
    "provider_timeout": "timeout",
    "provider_auth_failed": "auth_config",
    "provider_quota": "auth_config",
}


@dataclass
class AudioJob:
    job_id: str
    status: str
    text: str
    voice_style: str
    created_at: str
    updated_at: str
    run_id: str = ""
    event_id: str = ""
    session_id: str = ""
    voice_url: Optional[str] = None
    error: Optional[str] = None
    provider: str = ""
    timings_ms: Dict[str, int] = field(default_factory=dict)
    failure_reason: str = ""
    error_class: str = ""

    def dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "run_id": self.run_id,
            "event_id": self.event_id,
            "status": self.status,
            "voice_url": self.voice_url,
            "error": self.error,
            "error_class": self.error_class or None,
            "provider": self.provider,
            "timings_ms": dict(self.timings_ms),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "failure_reason": self.failure_reason,
        }


class AudioJobManager:
    """Runs TTS in background so interaction responses are not blocked by audio.

    Design:
    - ThreadPoolExecutor with bounded workers (default 2)
    - Max job count with LRU eviction of terminal jobs
    - Per-session pending job limit with supersede semantics
    - Sanitized error capture
    - Optional on_complete callback for observation writeback
    """

    def __init__(
        self,
        tts_provider: Any,
        ttl_seconds: int = 900,
        max_jobs: int = 100,
        max_pending_per_session: int = 3,
        max_workers: int = 2,
        provider_name: str = "tts",
        on_complete: Optional[Callable[[str, str, Optional[str]], None]] = None,
        store: Optional["AudioJobStore"] = None,
        provider_gate: Optional["ProviderGate"] = None,
    ) -> None:
        self.tts_provider = tts_provider
        self.ttl_seconds = ttl_seconds
        self.max_jobs = max_jobs
        self.max_pending_per_session = max_pending_per_session
        self.provider_name = provider_name
        self.on_complete = on_complete
        self._store = store
        self.provider_gate = provider_gate
        self._jobs: Dict[str, AudioJob] = {}
        self._order: List[str] = []
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._pending_count = 0
        self._retry_cache: Dict[str, tuple] = {}  # old_job_id -> (new_job_id, timestamp)

    def enqueue(
        self,
        text: str,
        voice_style: str = "soft",
        run_id: str = "",
        event_id: str = "",
        session_id: str = "",
    ) -> str:
        job_id = "aud-" + uuid4().hex[:12]
        now = datetime.utcnow().isoformat()
        job = AudioJob(
            job_id=job_id,
            status="pending",
            text=text,
            voice_style=voice_style,
            run_id=run_id,
            event_id=event_id,
            session_id=session_id,
            created_at=now,
            updated_at=now,
            provider=self.provider_name,
        )

        with self._lock:
            # Supersede older pending jobs in the same session
            if session_id:
                for existing in self._jobs.values():
                    if (
                        existing.session_id == session_id
                        and existing.status == "pending"
                    ):
                        existing.status = "superseded"
                        existing.error = "superseded by newer job"
                        existing.error_class = "infrastructure"
                        existing.updated_at = datetime.utcnow().isoformat()
                        self._adjust_pending_locked(-1)

            # Enforce per-session pending limit
            if session_id:
                pending_count = sum(
                    1
                    for j in self._jobs.values()
                    if j.session_id == session_id and j.status == "pending"
                )
                if pending_count >= self.max_pending_per_session:
                    # Mark oldest pending in this session as superseded
                    oldest = None
                    for j in self._jobs.values():
                        if j.session_id == session_id and j.status == "pending":
                            if oldest is None or j.created_at < oldest.created_at:
                                oldest = j
                    if oldest:
                        oldest.status = "superseded"
                        oldest.error = "pending limit exceeded"
                        oldest.error_class = "infrastructure"
                        oldest.updated_at = datetime.utcnow().isoformat()
                        self._adjust_pending_locked(-1)

            self._jobs[job_id] = job
            self._order.append(job_id)
            self._pending_count += 1
            self._evict_if_needed()

            # Write-through to SQLite
            if self._store:
                try:
                    self._store.save(job.__dict__)
                except Exception:
                    logger.warning("audio_job_store.save failed for %s", job_id, exc_info=True)
                # Also persist superseded jobs
                for existing_id, existing_job in self._jobs.items():
                    if existing_id != job_id and existing_job.status == "superseded":
                        try:
                            self._store.save(existing_job.__dict__)
                        except Exception:
                            pass

        self._executor.submit(self._run_job, job_id)
        return job_id

    def get(self, job_id: str) -> Optional[AudioJob]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                if job.status == "pending" and self._is_expired(job):
                    job.status = "expired"
                    job.error = "audio job expired"
                    job.error_class = "timeout"
                    job.updated_at = datetime.utcnow().isoformat()
                    self._adjust_pending_locked(-1)
                return AudioJob(**job.__dict__)

        # Fall back to SQLite for jobs not in memory cache (e.g. after restart)
        if self._store:
            row = self._store.get(job_id)
            if row is not None:
                return AudioJob(
                    job_id=row["job_id"],
                    status=row["status"],
                    text=row.get("text", ""),
                    voice_style=row.get("voice_style", ""),
                    created_at=row.get("created_at", ""),
                    updated_at=row.get("updated_at", ""),
                    run_id=row.get("run_id", ""),
                    event_id=row.get("event_id", ""),
                    session_id=row.get("session_id", ""),
                    voice_url=row.get("voice_url"),
                    error=row.get("error"),
                    provider=row.get("provider", ""),
                    timings_ms=row.get("timings_ms", {}),
                    error_class=row.get("error_class", ""),
                )
        return None

    def retry(self, job_id: str) -> Optional[str]:
        """Create a new job from a terminal failed/expired job.

        Returns new job_id, or None if the job is not retryable.
        Idempotent: returns cached new job_id if same old job retried within 5s.
        """
        now_mono = datetime.utcnow().timestamp()

        # Idempotency check
        cached = self._retry_cache.get(job_id)
        if cached:
            cached_id, cached_ts = cached
            if now_mono - cached_ts < 5.0:
                return cached_id

        old = self.get(job_id)
        if old is None:
            return None
        if old.status not in ("failed", "expired",
                               "failed_runtime_restart", "failed_shutdown"):
            return None

        new_id = self.enqueue(
            text=old.text,
            voice_style=old.voice_style,
            session_id=old.session_id,
        )
        self._retry_cache[job_id] = (new_id, now_mono)
        return new_id

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.status != "pending":
            return

        try:
            queued = datetime.fromisoformat(job.created_at)
            queue_ms = int((datetime.utcnow() - queued).total_seconds() * 1000)
        except (ValueError, TypeError):
            queue_ms = 0

        tts_start = datetime.utcnow()
        gate_acquired = False
        try:
            if self.provider_gate is not None:
                self.provider_gate.acquire("tts")
                gate_acquired = True
            voice_url = self.tts_provider.synthesize(job.text, job.voice_style)
            tts_ms = int((datetime.utcnow() - tts_start).total_seconds() * 1000)
        except Exception as exc:
            voice_url = None
            tts_ms = int((datetime.utcnow() - tts_start).total_seconds() * 1000)
            sanitized = _sanitize_error(exc)
            audio_err_class = _map_error_class(exc)

            with self._lock:
                current = self._jobs.get(job_id)
                if current is None or current.status != "pending":
                    return
                current.status = "failed"
                current.voice_url = None
                current.error = sanitized
                current.error_class = audio_err_class
                current.timings_ms["tts"] = tts_ms
                current.timings_ms["audio_queue"] = queue_ms
                current.updated_at = datetime.utcnow().isoformat()
                self._adjust_pending_locked(-1)

                if self._store:
                    try:
                        self._store.save(current.__dict__)
                    except Exception:
                        logger.warning("audio_job_store.save failed for %s", job_id, exc_info=True)

            if self.on_complete:
                try:
                    self.on_complete(job_id, "failed", sanitized)
                except Exception:
                    logger.warning("on_complete callback failed", exc_info=True)
            return
        finally:
            if gate_acquired and self.provider_gate is not None:
                try:
                    self.provider_gate.release("tts")
                except Exception:
                    pass

        with self._lock:
            current = self._jobs.get(job_id)
            if current is None or current.status != "pending":
                return
            current.updated_at = datetime.utcnow().isoformat()
            current.timings_ms["tts"] = tts_ms
            current.timings_ms["audio_queue"] = queue_ms
            if voice_url:
                current.status = "ready"
                current.voice_url = voice_url
                current.error = None
            else:
                current.status = "failed"
                current.voice_url = None
                current.error = "tts returned empty"
                current.error_class = "auth_config"
            self._adjust_pending_locked(-1)

            if self._store:
                try:
                    self._store.save(current.__dict__)
                except Exception:
                    logger.warning("audio_job_store.save failed for %s", job_id, exc_info=True)

        if self.on_complete:
            try:
                status = "ready" if voice_url else "failed"
                self.on_complete(job_id, status, None if voice_url else "tts returned empty")
            except Exception:
                logger.warning("on_complete callback failed", exc_info=True)

    def _is_expired(self, job: AudioJob) -> bool:
        try:
            created = datetime.fromisoformat(job.created_at)
        except ValueError:
            return False
        return datetime.utcnow() - created > timedelta(seconds=self.ttl_seconds)

    def _evict_if_needed(self) -> None:
        """Remove oldest jobs when over max_jobs.

        Evicts terminal jobs first. If the oldest is non-terminal (stuck pending),
        force-expire it to prevent unbounded growth.
        """
        while len(self._order) > self.max_jobs:
            old_id = self._order[0]
            old_job = self._jobs.get(old_id)
            if old_job is None:
                self._order.pop(0)
                continue
            if old_job.status in AUDIO_JOB_TERMINAL:
                self._order.pop(0)
                self._jobs.pop(old_id, None)
            else:
                # Force-expire stuck non-terminal job
                if old_job.status == "pending":
                    self._adjust_pending_locked(-1)
                old_job.status = "expired"
                old_job.error = "expired: queue full"
                old_job.error_class = "timeout"
                old_job.updated_at = datetime.utcnow().isoformat()
                self._order.pop(0)
                self._jobs.pop(old_id, None)

    def shutdown(self, drain_timeout_s: Optional[float] = None) -> None:
        if drain_timeout_s and drain_timeout_s > 0:
            self._executor.shutdown(wait=True, timeout=drain_timeout_s)
        else:
            self._executor.shutdown(wait=False)

    def pending_count(self) -> int:
        """Count of pending jobs (lock-free read for watchdog health)."""
        return max(0, int(self._pending_count))

    def _adjust_pending_locked(self, delta: int) -> None:
        self._pending_count = max(0, self._pending_count + delta)

    def mark_restart_failed(self) -> int:
        """Mark all pending/running jobs as failed_runtime_restart."""
        if self._store:
            self._store.mark_restart_failed()
        count = 0
        with self._lock:
            for job in self._jobs.values():
                if job.status in ("pending", "running"):
                    if job.status == "pending":
                        self._adjust_pending_locked(-1)
                    job.status = "failed_runtime_restart"
                    job.failure_reason = "runtime_restarted"
                    job.error = "runtime restarted while job was in-flight"
                    job.error_class = "infrastructure"
                    job.updated_at = datetime.utcnow().isoformat()
                    count += 1
        return count

    def mark_shutdown_failed(self) -> int:
        """Mark all pending/running jobs as failed_shutdown."""
        if self._store:
            self._store.mark_shutdown_failed()
        count = 0
        with self._lock:
            for job in self._jobs.values():
                if job.status in ("pending", "running"):
                    if job.status == "pending":
                        self._adjust_pending_locked(-1)
                    job.status = "failed_shutdown"
                    job.failure_reason = "process_shutdown"
                    job.error = "process shutdown while job was in-flight"
                    job.error_class = "infrastructure"
                    job.updated_at = datetime.utcnow().isoformat()
                    count += 1
        return count


def _map_error_class(exc: Exception) -> str:
    """Map an exception to an audio error_class string."""
    error_class = getattr(exc, "error_class", None)
    if error_class and error_class in _PROVIDER_ERROR_TO_AUDIO_CLASS:
        return _PROVIDER_ERROR_TO_AUDIO_CLASS[error_class]
    return "unknown"


def _sanitize_error(exc: Exception) -> str:
    """Return a sanitized error string — no API keys, tokens, or raw provider output."""
    exc_type = type(exc).__name__
    msg = str(exc)[:120]
    # Strip anything that looks like a key or token
    for marker in ("sk-", "tp-", "nvapi-", "Bearer ", "token="):
        idx = msg.find(marker)
        if idx >= 0:
            msg = msg[:idx] + "[REDACTED]"
            break
    return f"{exc_type}: {msg}" if msg else exc_type
