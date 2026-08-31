"""Typed contracts for the current-only anomaly projection.

This module deliberately contains no persistence or delivery history model.  An
issue is a projection of an owner fact that is true *now*; the owner remains the
source of truth for the facts and for any repair command.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import json
import math
from typing import Any, Mapping

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191
_ISSUE_KEY_PREFIX = "ci_"
_ISSUE_KEY_VERSION = 1

# The subject object is closed per definition.  A detector with no entry here
# must not fall back to a generic anomaly row.
CURRENT_ISSUE_SUBJECT_FIELDS: dict[str, tuple[str, ...]] = {
    "GOVSUB-007": ("payable_identity",),
    "LINE-006": ("case_no", "notification_reason"),
}


def canonical_subject_identity_for_code(
    definition_code: str, subject_identity: Mapping[str, Any]
) -> str:
    """Validate and serialize a definition's closed subject object."""

    try:
        expected = CURRENT_ISSUE_SUBJECT_FIELDS[definition_code]
    except KeyError as error:
        raise ValueError("anomaly subject schema is unavailable") from error
    if set(subject_identity) != set(expected):
        raise ValueError("anomaly subject identity fields are not closed")
    return canonical_subject_identity(subject_identity)


def build_owner_lock_key(
    owner_domain: str, owner_root_type: str, canonical_owner_root_id: str
) -> str:
    """Build the deterministic lock identity shared by all codes on one root."""

    values = (
        (owner_domain, "owner domain"),
        (owner_root_type, "owner root type"),
        (canonical_owner_root_id, "owner root id"),
    )
    for value, field_name in values:
        require_canonical_text(value, field_name, _IDENTITY_MAXIMUM_LENGTH)
    return ":".join(value for value, _ in values)


def canonical_subject_identity(subject_identity: Mapping[str, Any]) -> str:
    """Return the closed subject object in its stable UTF-8 JSON form.

    This is intentionally independent of the database collation.  The object
    is validated here, before an issue key is derived or persisted.
    """

    if not isinstance(subject_identity, Mapping):
        raise TypeError("subject identity must be a mapping")
    value = dict(subject_identity)
    _validate_json_object(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def build_issue_key(
    secret: str | bytes,
    definition_code: str,
    subject_identity: Mapping[str, Any],
) -> str:
    """Derive the opaque current issue identity using the injected secret."""

    require_canonical_text(definition_code, "definition code", _IDENTITY_MAXIMUM_LENGTH)
    if isinstance(secret, str):
        secret_bytes = secret.encode("utf-8")
    elif isinstance(secret, bytes):
        secret_bytes = secret
    else:
        raise TypeError("issue identity secret must be text or bytes")
    if not secret_bytes:
        raise ValueError("issue identity secret is required")
    canonical = canonical_subject_identity_for_code(definition_code, subject_identity)
    payload = json.dumps(
        {
            "v": _ISSUE_KEY_VERSION,
            "definition_code": definition_code,
            "subject_identity": json.loads(canonical),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    digest = hmac.new(secret_bytes, payload, hashlib.sha256).hexdigest()
    return _ISSUE_KEY_PREFIX + digest


def _validate_json_object(value: Mapping[str, Any]) -> None:
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError("subject identity keys must be non-empty text")
        _validate_json_value(item)


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("subject identity contains a non-finite number")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        _validate_json_object(value)
        return
    raise TypeError("subject identity contains a non-JSON value")


def _sorted_unique(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    normalized = tuple(
        require_canonical_text(value, f"{field_name} item", _IDENTITY_MAXIMUM_LENGTH)
        for value in values
    )
    if normalized != tuple(sorted(set(normalized))):
        raise ValueError(f"{field_name} must be sorted and unique")
    return normalized


@dataclass(frozen=True, slots=True)
class CurrentIssueCandidate:
    """One issue produced from one authoritative owner snapshot."""

    issue_key: str
    definition_code: str
    owner_domain: str
    owner_root_type: str
    subject_type: str
    subject_id: str
    owner_version: int
    severity: str
    blocking: bool
    details: Mapping[str, object]
    subject_identity: Mapping[str, Any]

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.issue_key, "issue key"),
            (self.definition_code, "definition code"),
            (self.owner_domain, "owner domain"),
            (self.owner_root_type, "owner root type"),
            (self.subject_type, "subject type"),
            (self.subject_id, "subject id"),
            (self.severity, "severity"),
        ):
            require_canonical_text(value, field_name, _IDENTITY_MAXIMUM_LENGTH)
        require_nonnegative_integer(self.owner_version, "owner version")
        if not isinstance(self.blocking, bool):
            raise TypeError("blocking must be boolean")
        if not isinstance(self.details, Mapping):
            raise TypeError("current issue details must be a mapping")
        canonical_subject_identity_for_code(self.definition_code, self.subject_identity)

    @property
    def canonical_subject_identity(self) -> str:
        """Return the persisted closed identity for this definition."""

        return canonical_subject_identity(self.subject_identity)


@dataclass(frozen=True, slots=True)
class CurrentIssueProjection:
    """The only anomaly-owned durable state: a currently true issue."""

    candidate: CurrentIssueCandidate
    episode_started_at: datetime
    last_verified_at: datetime
    owner_snapshot_token: str = ""
    details_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, CurrentIssueCandidate):
            raise TypeError("current issue candidate is invalid")
        if self.episode_started_at.tzinfo is None or self.last_verified_at.tzinfo is None:
            raise ValueError("current issue timestamps must be timezone-aware")
        if self.last_verified_at < self.episode_started_at:
            raise ValueError("last verified time cannot precede episode start")
        if self.owner_snapshot_token:
            require_canonical_text(
                self.owner_snapshot_token,
                "owner snapshot token",
                _IDENTITY_MAXIMUM_LENGTH,
            )
        if self.details_version != 1:
            raise ValueError("unsupported current issue details version")

    @property
    def issue_key(self) -> str:
        return self.candidate.issue_key


@dataclass(frozen=True, slots=True)
class RecheckScope:
    """A bounded, deterministic set of owner roots to re-evaluate."""

    owner_domain: str
    owner_root_type: str
    subject_type: str
    subject_ids: tuple[str, ...]
    owner_lock_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.owner_domain, "owner domain"),
            (self.owner_root_type, "owner root type"),
            (self.subject_type, "subject type"),
        ):
            require_canonical_text(value, field_name, _IDENTITY_MAXIMUM_LENGTH)
        _sorted_unique(self.subject_ids, "subject ids")
        _sorted_unique(self.owner_lock_keys, "owner lock keys")
        if not self.subject_ids:
            raise ValueError("recheck scope must contain at least one subject")
        if not self.owner_lock_keys:
            raise ValueError("recheck scope must contain at least one owner lock")


@dataclass(frozen=True, slots=True)
class OwnerSnapshot:
    """Complete owner readback used to derive a candidate set."""

    scope: RecheckScope
    snapshot_token: str
    owner_version: int
    facts: object
    authoritative_complete: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.scope, RecheckScope):
            raise TypeError("owner snapshot scope is invalid")
        require_canonical_text(self.snapshot_token, "owner snapshot token", _IDENTITY_MAXIMUM_LENGTH)
        require_nonnegative_integer(self.owner_version, "owner snapshot version")
        if not isinstance(self.authoritative_complete, bool):
            raise TypeError("owner snapshot completeness must be boolean")


@dataclass(frozen=True, slots=True)
class RecheckIntent:
    """A replayable request to refresh a bounded owner scope."""

    intent_identity: str
    scope: RecheckScope
    owner_version: int
    payload_fingerprint: PreviewFingerprint

    def __post_init__(self) -> None:
        require_canonical_text(self.intent_identity, "recheck intent identity", _IDENTITY_MAXIMUM_LENGTH)
        if not isinstance(self.scope, RecheckScope):
            raise TypeError("recheck intent scope is invalid")
        require_nonnegative_integer(self.owner_version, "recheck intent owner version")
        if not isinstance(self.payload_fingerprint, PreviewFingerprint):
            raise TypeError("recheck intent payload fingerprint is invalid")


def validate_candidate_set(
    scope: RecheckScope,
    candidates: tuple[CurrentIssueCandidate, ...],
) -> tuple[CurrentIssueCandidate, ...]:
    """Validate a detector result before any projection mutation is attempted."""

    if not isinstance(candidates, tuple):
        raise TypeError("recheck candidates must be a tuple")
    subject_ids = set(scope.subject_ids)
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, CurrentIssueCandidate):
            raise TypeError("recheck candidate is invalid")
        if candidate.owner_domain != scope.owner_domain:
            raise ValueError("recheck candidate owner domain mismatch")
        if candidate.owner_root_type != scope.owner_root_type:
            raise ValueError("recheck candidate owner root type mismatch")
        if candidate.subject_type != scope.subject_type or candidate.subject_id not in subject_ids:
            raise ValueError("recheck candidate is outside bounded scope")
        if candidate.issue_key in seen:
            raise ValueError("recheck candidate issue key is duplicated")
        seen.add(candidate.issue_key)
    return tuple(sorted(candidates, key=lambda item: item.issue_key))


__all__ = [
    "build_issue_key",
    "build_owner_lock_key",
    "canonical_subject_identity",
    "canonical_subject_identity_for_code",
    "CURRENT_ISSUE_SUBJECT_FIELDS",
    "CurrentIssueCandidate",
    "CurrentIssueProjection",
    "OwnerSnapshot",
    "RecheckIntent",
    "RecheckScope",
    "validate_candidate_set",
]
