"""Framework-neutral performance and UX safety policies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

DEFAULT_PAGE_SIZE = 50
MAXIMUM_PAGE_SIZE = 200


class UiOperationKind(StrEnum):
    LOCAL_DISPLAY = "local_display"
    QUERY = "query"
    PREVIEW = "preview"
    APPLY = "apply"
    WORKFLOW = "workflow"
    FORMAL_APPLY = "formal_apply"
    ALERT_WORKFLOW = "alert_workflow"
    ARCHIVE_EXPORT = "archive_export"


class BackgroundJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundJobAction(StrEnum):
    START = "start"
    SUCCEED = "succeed"
    FAIL = "fail"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class CursorPageRequest:
    page_size: int = DEFAULT_PAGE_SIZE
    after_cursor: str | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.page_size, "page size")
        if self.page_size > MAXIMUM_PAGE_SIZE:
            raise ValueError("page_size_invalid")
        if self.after_cursor is not None:
            require_canonical_text(self.after_cursor, "after cursor", 500)


@dataclass(frozen=True, slots=True)
class CursorPaginationPolicy:
    default_page_size: int
    maximum_page_size: int

    def __post_init__(self) -> None:
        require_positive_integer(self.default_page_size, "default page size")
        require_positive_integer(self.maximum_page_size, "maximum page size")
        if self.default_page_size > self.maximum_page_size:
            raise ValueError("default page size exceeds maximum")

    def resolve_page_size(self, requested_page_size: int | None) -> int:
        page_size = (
            self.default_page_size
            if requested_page_size is None
            else requested_page_size
        )
        require_positive_integer(page_size, "requested page size")
        if page_size > self.maximum_page_size:
            raise ValueError("requested page size exceeds maximum")
        return page_size


@dataclass(frozen=True, slots=True)
class CacheKeyParts:
    namespace: str
    resource_identity: str
    permission_scope: tuple[str, ...]
    facts_version: int
    contract_version: str
    time_zone: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.namespace, "cache namespace"),
            (self.resource_identity, "resource identity"),
            (self.contract_version, "contract version"),
            (self.time_zone, "time zone"),
        ):
            require_canonical_text(value, field_name, 191)
        require_nonnegative_integer(self.facts_version, "facts version")
        if self.permission_scope != tuple(sorted(set(self.permission_scope))):
            raise ValueError("permission scope must be sorted and unique")
        for permission in self.permission_scope:
            require_canonical_text(permission, "permission scope", 191)


@dataclass(frozen=True, slots=True)
class SingleFlightCommandIdentity:
    idempotency_key: IdempotencyKey
    payload_fingerprint: PreviewFingerprint

    def __post_init__(self) -> None:
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("idempotency key must be IdempotencyKey")
        if not isinstance(self.payload_fingerprint, PreviewFingerprint):
            raise TypeError("payload fingerprint must be PreviewFingerprint")


@dataclass(frozen=True, slots=True)
class CacheIdentity:
    resource_identity: str
    actor_scope: str
    facts_version: int
    contract_version: str
    timezone_name: str
    locale_name: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.resource_identity, "resource identity"),
            (self.actor_scope, "actor scope"),
            (self.contract_version, "contract version"),
            (self.timezone_name, "timezone name"),
            (self.locale_name, "locale name"),
        ):
            require_canonical_text(value, field_name, 191)
        require_nonnegative_integer(self.facts_version, "facts version")

    def fingerprint(self) -> PreviewFingerprint:
        return fingerprint_payload(
            {
                "resource_identity": self.resource_identity,
                "actor_scope": self.actor_scope,
                "facts_version": self.facts_version,
                "contract_version": self.contract_version,
                "timezone_name": self.timezone_name,
                "locale_name": self.locale_name,
            }
        )


@dataclass(frozen=True, slots=True)
class SingleFlightState:
    active_command_identities: frozenset[str] = frozenset()

    def begin(self, command_identity: str) -> SingleFlightState:
        require_canonical_text(command_identity, "command identity", 191)
        if command_identity in self.active_command_identities:
            raise ValueError("command_already_in_flight")
        return SingleFlightState(
            self.active_command_identities | {command_identity}
        )

    def finish(self, command_identity: str) -> SingleFlightState:
        require_canonical_text(command_identity, "command identity", 191)
        return SingleFlightState(
            self.active_command_identities - {command_identity}
        )


@dataclass(frozen=True, slots=True)
class RequestSupersession:
    latest_generation: int

    def __post_init__(self) -> None:
        require_nonnegative_integer(
            self.latest_generation,
            "request generation",
        )

    def next(self) -> RequestSupersession:
        return RequestSupersession(self.latest_generation + 1)

    def accepts(self, response_generation: int) -> bool:
        require_nonnegative_integer(
            response_generation,
            "response generation",
        )
        return response_generation == self.latest_generation


def allows_optimistic_success(operation: UiOperationKind) -> bool:
    if not isinstance(operation, UiOperationKind):
        raise TypeError("operation must be UiOperationKind")
    return operation is UiOperationKind.LOCAL_DISPLAY


def can_show_optimistic_success(operation: UiOperationKind) -> bool:
    return allows_optimistic_success(operation)


def build_cache_key(parts: CacheKeyParts) -> str:
    if not isinstance(parts, CacheKeyParts):
        raise TypeError("cache key parts must be CacheKeyParts")
    return fingerprint_payload(
        {
            "namespace": parts.namespace,
            "resource_identity": parts.resource_identity,
            "permission_scope": parts.permission_scope,
            "facts_version": parts.facts_version,
            "contract_version": parts.contract_version,
            "time_zone": parts.time_zone,
        }
    ).value


def transition_background_job(
    current: BackgroundJobStatus,
    action: BackgroundJobAction,
) -> BackgroundJobStatus:
    try:
        return _JOB_TRANSITIONS[(current, action)]
    except KeyError as exc:
        raise ValueError("job_state_conflict") from exc


def require_payload_budget(
    payload: Mapping[str, object],
    serialized_size_bytes: int,
    maximum_size_bytes: int,
) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    require_nonnegative_integer(serialized_size_bytes, "payload bytes")
    require_positive_integer(maximum_size_bytes, "maximum payload bytes")
    if serialized_size_bytes > maximum_size_bytes:
        raise ValueError("payload_too_large")


_JOB_TRANSITIONS = {
    (BackgroundJobStatus.QUEUED, BackgroundJobAction.START):
        BackgroundJobStatus.RUNNING,
    (BackgroundJobStatus.QUEUED, BackgroundJobAction.CANCEL):
        BackgroundJobStatus.CANCELLED,
    (BackgroundJobStatus.RUNNING, BackgroundJobAction.SUCCEED):
        BackgroundJobStatus.SUCCEEDED,
    (BackgroundJobStatus.RUNNING, BackgroundJobAction.FAIL):
        BackgroundJobStatus.FAILED,
}


__all__ = [
    "BackgroundJobAction",
    "BackgroundJobStatus",
    "CacheKeyParts",
    "CacheIdentity",
    "CursorPaginationPolicy",
    "CursorPageRequest",
    "RequestSupersession",
    "SingleFlightCommandIdentity",
    "SingleFlightState",
    "UiOperationKind",
    "allows_optimistic_success",
    "build_cache_key",
    "can_show_optimistic_success",
    "require_payload_budget",
    "transition_background_job",
]
