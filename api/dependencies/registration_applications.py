"""Internal human review composition; the public intake application does not import this module."""
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
    return RegistrationReviewApplication(staging, formal)
