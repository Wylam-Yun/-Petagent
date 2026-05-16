from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional
from uuid import uuid4


@dataclass
class AudioJob:
    job_id: str
    status: str
    text: str
    voice_style: str
    created_at: str
    updated_at: str
    voice_url: Optional[str] = None
    error: Optional[str] = None

    def dict(self) -> Dict[str, Optional[str]]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "voice_url": self.voice_url,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AudioJobManager:
    """Runs TTS in background so interaction responses are not blocked by audio."""

    def __init__(self, tts_provider, ttl_seconds: int = 600) -> None:
        self.tts_provider = tts_provider
        self.ttl_seconds = ttl_seconds
        self._jobs: Dict[str, AudioJob] = {}
        self._lock = threading.RLock()

    def enqueue(self, text: str, voice_style: str = "soft") -> str:
        job_id = "aud-%s" % uuid4().hex
        now = datetime.utcnow().isoformat()
        job = AudioJob(
            job_id=job_id,
            status="pending",
            text=text,
            voice_style=voice_style,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job_id] = job
        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        thread.start()
        return job_id

    def get(self, job_id: str) -> Optional[AudioJob]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status == "pending" and self._is_expired(job):
                job.status = "expired"
                job.error = "audio job expired"
                job.updated_at = datetime.utcnow().isoformat()
            return AudioJob(**job.__dict__)

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return

        try:
            voice_url = self.tts_provider.synthesize(job.text, job.voice_style)
        except Exception:
            voice_url = None

        with self._lock:
            current = self._jobs.get(job_id)
            if current is None or current.status == "expired":
                return
            current.updated_at = datetime.utcnow().isoformat()
            if voice_url:
                current.status = "ready"
                current.voice_url = voice_url
                current.error = None
            else:
                current.status = "failed"
                current.voice_url = None
                current.error = "tts synthesis failed"

    def _is_expired(self, job: AudioJob) -> bool:
        try:
            created = datetime.fromisoformat(job.created_at)
        except ValueError:
            return False
        return datetime.utcnow() - created > timedelta(seconds=self.ttl_seconds)
