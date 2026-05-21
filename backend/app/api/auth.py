from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def get_internal_token(settings) -> str:
    """Return the internal debug token, generating and persisting one if needed."""
    env_token = os.environ.get("DEBUG_INTERNAL_TOKEN", "").strip()
    if env_token:
        return env_token

    token_path = settings.data_dir.parent / "secrets" / "internal_token"
    if token_path.exists():
        try:
            return token_path.read_text().strip()
        except OSError:
            pass

    # Generate a new token and persist it
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token = os.urandom(24).hex()
    try:
        token_path.write_text(token)
        token_path.chmod(0o600)
        fingerprint = hashlib.sha256(token.encode()).hexdigest()[:12]
        logger.info("Generated internal token at %s (fingerprint: %s)", token_path, fingerprint)
    except OSError as exc:
        logger.warning("Failed to persist internal token: %s", exc)
    return token


def is_loopback(request: Request) -> bool:
    """Check if the request comes from loopback."""
    client = request.client
    if client is None:
        return False
    return client.host in {"127.0.0.1", "::1", "localhost"}


def require_internal_token(request: Request) -> None:
    """FastAPI dependency that requires a valid internal token."""
    expected = getattr(request.app.state, "internal_token", None)
    if not expected:
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

    raise HTTPException(status_code=403, detail="Invalid or missing internal token")
