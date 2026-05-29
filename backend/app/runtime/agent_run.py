from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

if TYPE_CHECKING:
    from app.runtime.agent_run_store import AgentRunStore

logger = logging.getLogger(__name__)

RUN_TERMINAL_STATUSES = {"committed", "completed", "failed", "superseded"}


@dataclass
class AgentObservation:
    """One sanitized observation recorded during an AgentRun."""

    kind: str
    detail: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class AgentRun:
    """Tracks one complete interaction cycle through the agent loop."""

    run_id: str = field(default_factory=lambda: "run-" + uuid4().hex[:12])
    event_id: str = ""
    episode_id: str = ""
    route: str = ""
    context_profile: str = ""
    provider: str = ""
    requested_tools: List[str] = field(default_factory=list)
    tool_observations: List[Dict[str, Any]] = field(default_factory=list)
    final_action: Optional[Dict[str, Any]] = None
    audio_job_id: Optional[str] = None
    sanitized_user_text: str = ""
    sanitized_response_text: str = ""
    timings_ms: Dict[str, int] = field(default_factory=dict)
    status: str = "started"
    error: Optional[str] = None
    observations: List[AgentObservation] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def record(self, kind: str, detail: Optional[Dict[str, Any]] = None) -> None:
        self.observations.append(AgentObservation(kind=kind, detail=detail or {}))
        self.updated_at = datetime.utcnow().isoformat()

    def set_status(self, status: str) -> None:
        self.status = status
        self.updated_at = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "event_id": self.event_id,
            "episode_id": self.episode_id,
            "route": self.route,
            "context_profile": self.context_profile,
            "provider": self.provider,
            "requested_tools": self.requested_tools,
            "tool_observations": self.tool_observations,
            "final_action": self.final_action,
            "audio_job_id": self.audio_job_id,
            "sanitized_user_text": _sanitize_text(self.sanitized_user_text),
            "sanitized_response_text": _sanitize_text(self.sanitized_response_text),
            "timings_ms": dict(self.timings_ms),
            "status": self.status,
            "error": self.error,
            "observation_count": len(self.observations),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _sanitize_text(text: str) -> str:
    """Strip anything that looks like a key or token from debug text."""
    if not text:
        return ""
    result = str(text)
    for marker in ("sk-", "tp-", "nvapi-", "Bearer ", "token="):
        idx = result.find(marker)
        if idx >= 0:
            result = result[:idx] + "[REDACTED]"
            break
    return result[:500]


class AgentRunRegistry:
    """Thread-safe in-memory registry of recent AgentRuns.

    When a store is provided, writes completed/failed runs to SQLite for
    postmortem debugging.
    """

    def __init__(
        self,
        max_runs: int = 50,
        store: Optional["AgentRunStore"] = None,
    ) -> None:
        self._runs: Dict[str, AgentRun] = {}
        self._order: List[str] = []
        self._lock = threading.RLock()
        self.max_runs = max_runs
        self._store = store

    def create(self, event_id: str = "", episode_id: str = "") -> AgentRun:
        run = AgentRun(event_id=event_id, episode_id=episode_id)
        with self._lock:
            self._runs[run.run_id] = run
            self._order.append(run.run_id)
            self._evict_if_needed()
        return run

    def get(self, run_id: str) -> Optional[AgentRun]:
        with self._lock:
            return self._runs.get(run_id)

    def find_by_audio_job_id(self, audio_job_id: str) -> Optional[AgentRun]:
        with self._lock:
            for run in self._runs.values():
                if run.audio_job_id == audio_job_id:
                    return run
            return None

    def persist_if_terminal(self, run: AgentRun) -> None:
        """Write run to SQLite if it reached a terminal status."""
        if run.status not in RUN_TERMINAL_STATUSES:
            return
        if self._store is None:
            return
        try:
            self._store.save(run.to_dict())
        except Exception:
            logger.warning("agent_run_store.save failed for %s", run.run_id, exc_info=True)

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            ids = list(reversed(self._order))
            result = []
            for rid in ids[:limit]:
                run = self._runs.get(rid)
                if run:
                    result.append(run.to_dict())
            return result

    def _evict_if_needed(self) -> None:
        while len(self._order) > self.max_runs:
            old_id = self._order.pop(0)
            self._runs.pop(old_id, None)
