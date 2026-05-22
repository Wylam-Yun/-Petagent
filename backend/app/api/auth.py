from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def internal_token_path(settings) -> Path:
    return settings.data_dir.parent / "secrets" / "internal_token"


def _new_token() -> str:
    return os.urandom(24).hex()


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def persist_internal_token(settings, token: str) -> Path:
    token_path = internal_token_path(settings)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token)
    token_path.chmod(0o600)
    return token_path


def get_internal_token(settings) -> str:
    """Return the internal debug token, generating and persisting one if needed."""
    env_token = os.environ.get("DEBUG_INTERNAL_TOKEN", "").strip()
    if env_token:
        return env_token

    token_path = internal_token_path(settings)
    if token_path.exists():
        try:
            return token_path.read_text().strip()
        except OSError:
            pass

    # Generate a new token and persist it
    token = _new_token()
    try:
        persist_internal_token(settings, token)
        fingerprint = token_fingerprint(token)
        logger.info("Generated internal token at %s (fingerprint: %s)", token_path, fingerprint)
    except OSError as exc:
        logger.warning("Failed to persist internal token: %s", exc)
    return token


def rotate_internal_token(settings) -> tuple[str, Path]:
    """Generate and persist a replacement token."""
    token = _new_token()
    token_path = persist_internal_token(settings, token)
    return token, token_path


def is_loopback(request: Request) -> bool:
    """Check if the request comes from loopback."""
    client = request.client
    if client is None:
        return False
    return client.host in {"127.0.0.1", "::1", "localhost"}


def _record_auth_rejection(request: Request, reason: str) -> None:
    incident_store = getattr(request.app.state, "incident_store", None)
    if incident_store is None:
        return
    client = request.client.host if request.client else "unknown"
    incident_store.record(
        "auth_rejected",
        {
            "path": request.url.path,
            "method": request.method,
            "client": client,
            "reason": reason,
        },
    )


def require_internal_token(request: Request) -> None:
    """FastAPI dependency that requires a valid internal token."""
    expected = getattr(request.app.state, "internal_token", None)
    if not expected:
        _record_auth_rejection(request, "not_configured")
        raise HTTPException(status_code=503, detail="Internal token not configured")

    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token == expected:
            return

    # Also accept X-Internal-Token header
    token_header = request.headers.get("x-internal-token", "")
    if token_header == expected:
        return

    _record_auth_rejection(request, "missing_or_invalid")
    raise HTTPException(status_code=403, detail="Invalid or missing internal token")
