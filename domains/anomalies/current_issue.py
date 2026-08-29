"""Typed contracts for the current-only anomaly projection.

This module deliberately contains no persistence or delivery history model.  An
issue is a projection of an owner fact that is true *now*; the owner remains the
source of truth for the facts and for any repair command.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191


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


@dataclass(frozen=True, slots=True)
class CurrentIssueProjection:
    """The only anomaly-owned durable state: a currently true issue."""

    candidate: CurrentIssueCandidate
    episode_started_at: datetime
    last_verified_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, CurrentIssueCandidate):
            raise TypeError("current issue candidate is invalid")
        if self.episode_started_at.tzinfo is None or self.last_verified_at.tzinfo is None:
            raise ValueError("current issue timestamps must be timezone-aware")
        if self.last_verified_at < self.episode_started_at:
            raise ValueError("last verified time cannot precede episode start")

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
    "CurrentIssueCandidate",
    "CurrentIssueProjection",
    "OwnerSnapshot",
    "RecheckIntent",
    "RecheckScope",
    "validate_candidate_set",
]
