"""Pure rules for reviewing invalid BeClass import rows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191
_REVIEW_IDENTITY_PREFIX = "beclass-review:"


class BeClassImportSourceKind(StrEnum):
    CLIENT = "client"
    STAFF = "staff"
    HCM = "hcm"


class BeClassImportReviewStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class BeClassImportReviewIssue(StrEnum):
    INVALID_ROOT_FACTS = "beclass_import_review_invalid_root_facts"
    ALREADY_RESOLVED = "beclass_import_review_already_resolved"
    UNRESOLVED_ISSUES = "beclass_import_review_unresolved_issues"
    STABLE_IDENTITY_MISSING = "beclass_import_review_stable_identity_missing"


class BeClassImportReviewDomainError(ValueError):
    def __init__(self, issue: BeClassImportReviewIssue, message: str) -> None:
        super().__init__(message)
        self.issue = issue


CanonicalBeClassPayload = Mapping[str, str | int | bool | None]


@dataclass(frozen=True, slots=True)
class InvalidBeClassImportRow:
    review_identity: str
    source_kind: BeClassImportSourceKind
    source_event_identity: str
    source_sheet: str
    source_row: int
    identifier: str
    source_payload: CanonicalBeClassPayload
    issue_codes: tuple[str, ...]
    source_fingerprint: PreviewFingerprint

    def __post_init__(self) -> None:
        _validate_review_identity(self.review_identity)
        _validate_identity(self.source_event_identity, "source event identity")
        _validate_identity(self.source_sheet, "source sheet")
        _validate_source_row(self.source_row)
        _validate_identifier(self.identifier)
        _validate_payload(self.source_payload, "source payload")
        _validate_issue_codes(self.issue_codes)
        if self.source_fingerprint != fingerprint_source_row(
            self.source_kind,
            self.source_event_identity,
            self.source_sheet,
            self.source_row,
            self.identifier,
            self.source_payload,
            self.issue_codes,
        ):
            _raise_invalid("source fingerprint does not match invalid row facts")


@dataclass(frozen=True, slots=True)
class BeClassImportReviewFacts:
    root: InvalidBeClassImportRow
    review_version: int
    status: BeClassImportReviewStatus
    effective_payload: CanonicalBeClassPayload

    def __post_init__(self) -> None:
        require_nonnegative_integer(self.review_version, "review version")
        _validate_payload(self.effective_payload, "effective payload")
        if self.status is BeClassImportReviewStatus.OPEN and self.review_version != 0:
            _raise_invalid("open review must remain at version zero")
        if self.status is BeClassImportReviewStatus.RESOLVED and self.review_version == 0:
            _raise_invalid("resolved review must have a positive version")


@dataclass(frozen=True, slots=True)
class BeClassImportReviewIntent:
    review_identity: str
    corrected_fields: CanonicalBeClassPayload
    resolved_issue_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_review_identity(self.review_identity)
        _validate_payload(self.corrected_fields, "corrected fields")
        if not self.corrected_fields:
            _raise_invalid("at least one corrected field is required")
        _validate_issue_codes(self.resolved_issue_codes)


@dataclass(frozen=True, slots=True)
class BeClassImportReviewCandidate:
    review_identity: str
    source_kind: BeClassImportSourceKind
    source_sheet: str
    source_row: int
    identifier: str
    resulting_version: int
    corrected_payload: CanonicalBeClassPayload
    resolved_issue_codes: tuple[str, ...]
    fingerprint: PreviewFingerprint


def build_review_identity(
    source_kind: BeClassImportSourceKind,
    source_event_identity: str,
) -> str:
    _validate_identity(source_event_identity, "source event identity")
    fingerprint = fingerprint_payload(
        {
            "source_kind": source_kind.value,
            "source_event_identity": source_event_identity,
        }
    )
    return f"{_REVIEW_IDENTITY_PREFIX}{fingerprint.value}"


def fingerprint_source_row(
    source_kind: BeClassImportSourceKind,
    source_event_identity: str,
    source_sheet: str,
    source_row: int,
    identifier: str,
    source_payload: CanonicalBeClassPayload,
    issue_codes: tuple[str, ...],
) -> PreviewFingerprint:
    _validate_identity(source_event_identity, "source event identity")
    _validate_payload(source_payload, "source payload")
    _validate_issue_codes(issue_codes)
    _validate_identity(source_sheet, "source sheet")
    _validate_source_row(source_row)
    _validate_identifier(identifier)
    return fingerprint_payload(
        {
            "source_kind": source_kind.value,
            "source_event_identity": source_event_identity,
            "source_sheet": source_sheet,
            "source_row": source_row,
            "identifier": identifier,
            "source_payload": source_payload,
            "issue_codes": issue_codes,
        }
    )


# Kept cohesive so one fingerprint covers the complete human correction decision.
def build_beclass_import_review_candidate(
    facts: BeClassImportReviewFacts,
    intent: BeClassImportReviewIntent,
) -> BeClassImportReviewCandidate:
    _validate_candidate_identity(facts, intent)
    _validate_open_review(facts)
    _validate_resolved_issues(facts, intent)
    corrected_payload = dict(facts.effective_payload)
    corrected_payload.update(intent.corrected_fields)
    _validate_stable_identity(facts.root.source_kind, corrected_payload)
    resulting_version = facts.review_version + 1
    fingerprint = _candidate_fingerprint(
        facts,
        intent,
        corrected_payload,
        resulting_version,
    )
    return BeClassImportReviewCandidate(
        intent.review_identity,
        facts.root.source_kind,
        facts.root.source_sheet,
        facts.root.source_row,
        facts.root.identifier,
        resulting_version,
        corrected_payload,
        intent.resolved_issue_codes,
        fingerprint,
    )


def review_outbox_snapshot(
    root: InvalidBeClassImportRow | BeClassImportReviewCandidate,
    *,
    version: int | None = None,
    active: bool | None = None,
) -> dict[str, object]:
    """Return the owner review envelope used by Case Import delivery.

    This is deliberately an owner snapshot, not an Anomalies definition or
    current-issue payload.  The review root and its resolution event remain
    the authoritative follow-up facts.
    """
    if isinstance(root, InvalidBeClassImportRow):
        review_identity = root.review_identity
        source_kind = root.source_kind
        source_sheet = root.source_sheet
        source_row = root.source_row
        identifier = root.identifier
        issue_codes = root.issue_codes
        snapshot_version = 0 if version is None else version
        snapshot_active = True if active is None else active
    else:
        review_identity = root.review_identity
        source_kind = root.source_kind
        source_sheet = root.source_sheet
        source_row = root.source_row
        identifier = root.identifier
        issue_codes = root.resolved_issue_codes
        snapshot_version = root.resulting_version if version is None else version
        snapshot_active = False if active is None else active
    return {
        "review_identity": review_identity,
        "source_kind": source_kind.value,
        "source_sheet": source_sheet,
        "source_row": source_row,
        "issue_codes": issue_codes,
        "version": snapshot_version,
        "identifier": identifier,
        "active": snapshot_active,
    }


def _candidate_fingerprint(facts, intent, payload, version):
    return fingerprint_payload(
        {
            "review_identity": intent.review_identity,
            "source_fingerprint": facts.root.source_fingerprint.value,
            "expected_review_version": facts.review_version,
            "resulting_review_version": version,
            "corrected_payload": payload,
            "resolved_issue_codes": intent.resolved_issue_codes,
        }
    )


def _validate_candidate_identity(facts, intent) -> None:
    if facts.root.review_identity != intent.review_identity:
        _raise_invalid("review intent belongs to another invalid row")


def _validate_open_review(facts) -> None:
    if facts.status is BeClassImportReviewStatus.RESOLVED:
        raise BeClassImportReviewDomainError(
            BeClassImportReviewIssue.ALREADY_RESOLVED,
            "The BeClass import row review is already resolved.",
        )


def _validate_resolved_issues(facts, intent) -> None:
    if intent.resolved_issue_codes == facts.root.issue_codes:
        return
    raise BeClassImportReviewDomainError(
        BeClassImportReviewIssue.UNRESOLVED_ISSUES,
        "Every recorded issue must be explicitly resolved.",
    )


def _validate_stable_identity(source_kind, payload) -> None:
    field_name = "query_no" if source_kind is BeClassImportSourceKind.CLIENT else "identity_card"
    value = payload.get(field_name)
    if isinstance(value, str) and value.strip():
        return
    raise BeClassImportReviewDomainError(
        BeClassImportReviewIssue.STABLE_IDENTITY_MISSING,
        f"Corrected {source_kind.value} row must include {field_name}.",
    )


def _validate_payload(payload, name) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError(f"{name} must be a mapping")
    for field, value in payload.items():
        _validate_identity(field, f"{name} field")
        if isinstance(value, (str, int, bool)) or value is None:
            continue
        _raise_invalid(f"{name} contains a non-canonical value")


def _validate_issue_codes(issue_codes) -> None:
    if not isinstance(issue_codes, tuple):
        raise TypeError("issue codes must be a tuple")
    for issue_code in issue_codes:
        _validate_identity(issue_code, "issue code")
    if not issue_codes or issue_codes != tuple(sorted(set(issue_codes))):
        _raise_invalid("issue codes must be non-empty, sorted, and unique")


def _validate_source_row(value) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _raise_invalid("source row must be a positive integer")


def _validate_identifier(value) -> None:
    _validate_identity(value, "identifier")

def _validate_review_identity(value) -> None:
    _validate_identity(value, "review identity")
    suffix = value.removeprefix(_REVIEW_IDENTITY_PREFIX)
    if not value.startswith(_REVIEW_IDENTITY_PREFIX) or len(suffix) != 64:
        _raise_invalid("review identity must be opaque")
    if any(character not in "0123456789abcdef" for character in suffix):
        _raise_invalid("review identity must be opaque")


def _validate_identity(value, name) -> None:
    require_canonical_text(value, name, _IDENTITY_MAXIMUM_LENGTH)


def _raise_invalid(message) -> None:
    raise BeClassImportReviewDomainError(
        BeClassImportReviewIssue.INVALID_ROOT_FACTS,
        message,
    )


__all__ = [
    "BeClassImportReviewCandidate",
    "BeClassImportReviewDomainError",
    "BeClassImportReviewFacts",
    "BeClassImportReviewIntent",
    "BeClassImportReviewIssue",
    "BeClassImportReviewStatus",
    "BeClassImportSourceKind",
    "CanonicalBeClassPayload",
    "InvalidBeClassImportRow",
    "build_beclass_import_review_candidate",
    "build_review_identity",
    "fingerprint_source_row",
    "review_outbox_snapshot",
]
