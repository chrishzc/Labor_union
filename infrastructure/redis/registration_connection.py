"""Registration Redis connection settings only; intentionally independent of app/DB settings."""
from __future__ import annotations

import os
from pathlib import Path

from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry


def registration_redis_client(*, role: str):
    if role not in {"intake", "admin"}:
        raise ValueError("registration_redis_role_invalid")
    password_file = os.environ.get(f"REGISTRATION_REDIS_{role.upper()}_PASSWORD_FILE")
    if not password_file:
        raise RuntimeError("registration_redis_credential_required")
    return Redis(host=os.environ.get("REGISTRATION_REDIS_HOST", "registration-redis"),
        port=int(os.environ.get("REGISTRATION_REDIS_PORT", "6379")),
        username=f"registration-{role}", password=Path(password_file).read_text(encoding="utf-8").strip(),
        decode_responses=True, socket_connect_timeout=2, socket_timeout=5,
        retry=Retry(NoBackoff(), 0))
