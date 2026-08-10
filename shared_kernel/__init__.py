"""Framework-independent contracts shared by all business domains."""

from shared_kernel.background_jobs import (
    BackgroundJobAccepted,
    BackgroundJobIdentity,
    BackgroundJobQueuePort,
    BackgroundJobRecord,
    BackgroundJobRepository,
    BackgroundJobStatus,
    transition_background_job,
)
from shared_kernel.clock import BusinessClock, FixedBusinessClock, SystemBusinessClock
from shared_kernel.errors import ErrorCategory, FieldError, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
    IdempotencyReceipt,
)
from shared_kernel.money import MoneyNTD
from shared_kernel.performance import (
    CacheKeyParts,
    CursorPaginationPolicy,
    SingleFlightCommandIdentity,
    UiOperationKind,
    build_cache_key,
    can_show_optimistic_success,
)
from shared_kernel.ports import (
    CacheEntry,
    OutboxIntent,
    OutboxWriter,
    PerformanceTelemetryPort,
    QueryCachePort,
    UnitOfWork,
)

__all__ = [
    "ActorContext",
    "BackgroundJobAccepted",
    "BackgroundJobIdentity",
    "BackgroundJobQueuePort",
    "BackgroundJobRecord",
    "BackgroundJobRepository",
    "BackgroundJobStatus",
    "BusinessClock",
    "CacheEntry",
    "CacheKeyParts",
    "CorrelationId",
    "CursorPaginationPolicy",
    "ErrorCategory",
    "ExpectedVersion",
    "FieldError",
    "FixedBusinessClock",
    "IdempotencyKey",
    "IdempotencyReceipt",
    "MoneyNTD",
    "OutboxIntent",
    "OutboxWriter",
    "PerformanceTelemetryPort",
    "PreviewFingerprint",
    "QueryCachePort",
    "SingleFlightCommandIdentity",
    "SystemBusinessClock",
    "TypedError",
    "UiOperationKind",
    "UnitOfWork",
    "build_cache_key",
    "can_show_optimistic_success",
    "fingerprint_payload",
    "transition_background_job",
]
