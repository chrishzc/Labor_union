"""
File: registration_applications.py
Description: 管理後台需求審核依賴組裝，自動確認共用 Redis 暫存命名空間初始化狀態。
"""
from functools import lru_cache

from api.dependencies.line_identity import get_line_identity_application
from infrastructure.redis.registration_connection import registration_redis_client
from infrastructure.redis.registration_staging_repository import RedisRegistrationStagingRepository
from subsystems.case_import.registration_staging import RegistrationReviewApplication


@lru_cache(maxsize=1)
def get_registration_staging_repository():
    return RedisRegistrationStagingRepository(registration_redis_client(role="admin"))


@lru_cache(maxsize=1)
def get_registration_review_application():
    staging = get_registration_staging_repository()
    formal = get_line_identity_application()
    try:
        staging.ensure_initialized()
    except Exception:
        try:
            staging.initialize(formal.registration_id_high_water(), shared_instance=True)
        except Exception:
            pass
    return RegistrationReviewApplication(staging, formal)
