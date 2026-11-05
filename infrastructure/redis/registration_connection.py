"""
File: registration_connection.py
Description: 註冊暫存 Redis 連線工廠，支援專用 secret 檔案或共用標準 REDIS_URL。
"""
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
    if password_file and Path(password_file).is_file():
        return Redis(
            host=os.environ.get("REGISTRATION_REDIS_HOST", "registration-redis"),
            port=int(os.environ.get("REGISTRATION_REDIS_PORT", "6379")),
            username=f"registration-{role}",
            password=Path(password_file).read_text(encoding="utf-8").strip(),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5,
            retry=Retry(NoBackoff(), 0),
        )

    # 方案二：共用標準 Redis（優先使用 REDIS_URL，或 fallback 本機標準連線）
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
