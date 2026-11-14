"""
File: registration_connection.py
Description: 正式註冊暫存僅使用專用 Redis；本機開發與測試可共用標準 Redis。
"""
from __future__ import annotations

import os
from pathlib import Path

from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry


class RegistrationRedisConfigurationError(RuntimeError):
    pass


def registration_redis_client(*, role: str):
    if role not in {"intake", "admin"}:
        raise ValueError("registration_redis_role_invalid")
    local_environment = (
        os.getenv("APP_ENV", "").strip().lower() in {"development", "dev", "local", "test", "testing"}
        and os.getenv("DEPLOYMENT_PROFILE", "").strip().lower() != "nas"
        and os.getenv("ACCESS_CONTROL_PROFILE", "").strip().lower() != "production"
    )
    password_file = os.environ.get(f"REGISTRATION_REDIS_{role.upper()}_PASSWORD_FILE")
    credential_error = f"registration_redis_{role}_credential_required"
    try:
        path = Path(password_file) if password_file else None
        password = path.read_text(encoding="utf-8").strip() if path and path.is_file() else ""
    except (OSError, ValueError):
        raise RegistrationRedisConfigurationError(credential_error) from None
    if password:
        host = os.getenv("REGISTRATION_REDIS_HOST", "registration-redis").strip()
        try:
            port = int(os.getenv("REGISTRATION_REDIS_PORT", "6379"))
        except ValueError:
            raise RegistrationRedisConfigurationError("registration_redis_endpoint_invalid") from None
        if not host or not 1 <= port <= 65535:
            raise RegistrationRedisConfigurationError("registration_redis_endpoint_invalid")
        return Redis(
            host=host,
            port=port,
            username=f"registration-{role}",
            password=password,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5,
            retry=Retry(NoBackoff(), 0),
        )

    if not local_environment:
        raise RegistrationRedisConfigurationError(credential_error)

    redis_url = os.environ.get("REGISTRATION_REDIS_URL") or os.environ.get("REDIS_URL")
    if redis_url:
        return Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5,
            retry=Retry(NoBackoff(), 0),
        )

    host = os.environ.get("REGISTRATION_REDIS_HOST", os.environ.get("REDIS_HOST", "127.0.0.1"))
    port = int(os.environ.get("REGISTRATION_REDIS_PORT", os.environ.get("REDIS_PORT", "6379")))
    password = os.environ.get(f"REGISTRATION_REDIS_{role.upper()}_PASSWORD") or os.environ.get("REDIS_PASSWORD")
    return Redis(
        host=host,
        port=port,
        password=password,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=5,
        retry=Retry(NoBackoff(), 0),
    )
