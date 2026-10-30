"""
File: __init__.py
Description: 匯出選用外部唯讀投影快取基礎設施 adapter。
"""

from infrastructure.cache.redis_projection_cache import (
    RedisCacheBackend,
    default_redis_cache_backend,
    reset_default_redis_cache_backend,
)

__all__ = [
    "RedisCacheBackend",
    "default_redis_cache_backend",
    "reset_default_redis_cache_backend",
]
