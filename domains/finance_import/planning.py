"""Deterministic Finance Import Preview planning from canonical bank facts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
    require_sha256_hex,
)

_IDENTITY_MAXIMUM_LENGTH = 191
_EVIDENCE_MAXIMUM_LENGTH = 500


class FinanceClassificationType(StrEnum):
    CLIENT_RECEIPT = "client_receipt"
    CLIENT_REFUND = "client_refund"
    CLIENT_REFUND_RETURN = "client_refund_return"
    CLIENT_SUBSIDY_RETURN = "client_subsidy_return"
    GOVERNMENT_SUBSIDY = "government_subsidy"
    STAFF_PAYOUT = "staff_payout"
    NON_BUSINESS_REVIEW = "non_business_review"


class FinanceImportDisposition(StrEnum):
    CREATE = "create"
    EXISTING = "existing"
    MANUAL_REVIEW = "manual_review"
    BUSINESS_PENDING = "business_pending"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class CanonicalFinanceImportRow:
    row_identity: str
    canonical_fact_version: int
    amount: MoneyNTD
    classification_type: FinanceClassificationType
    disposition: FinanceImportDisposition
    decision_facts_fingerprint: PreviewFingerprint
    target_identities: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    available_actions: tuple[str, ...] = ()
    integrity_violations: tuple[str, ...] = ()
    fingerprint_collision: bool = False
    formal_reference_conflict: bool = False

    def __post_init__(self) -> None:
        _validate_row_identity(self)
        _validate_row_state(self)
        _validate_sorted_text(self.target_identities, "target identities")
        _validate_sorted_text(self.evidence, "classification evidence")
        _validate_sorted_text(self.available_actions, "available actions")
        _validate_sorted_text(self.integrity_violations, "integrity violations")


@dataclass(frozen=True, slots=True)
class FinanceImportBatchFacts:
    batch_identity: str
    batch_version: int
    source_row_count: int
    canonical_created_count: int
    duplicate_occurrence_count: int
    source_content_digest: str
    classifier_version: str
    fingerprint_version: str
    rows: tuple[CanonicalFinanceImportRow, ...]
    batch_completed: bool = True
    integrity_violations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_batch_identity(self)
        _validate_batch_counts(self)
        require_sha256_hex(self.source_content_digest, "source content digest")
        _validate_batch_rows(self.rows)
        _validate_sorted_text(self.integrity_violations, "integrity violations")
        if not isinstance(self.batch_completed, bool):
            raise TypeError("batch completed must be bool")


@dataclass(frozen=True, slots=True)
class FinanceImportPreviewCounts:
    source_rows: int
    canonical_created: int
    duplicate_occurrences: int
    ready_dispatch: int
    existing: int
    manual_review: int
    business_pending: int
    blocked: int


@dataclass(frozen=True, slots=True)
class FinanceDispatchSummary:
    classification_type: FinanceClassificationType
    candidate_count: int
    total_amount: MoneyNTD


@dataclass(frozen=True, slots=True)
class FinanceImportPlan:
    batch_identity: str
    batch_version: int
    source_content_digest: str
    classifier_version: str
    fingerprint_version: str
    rows: tuple[CanonicalFinanceImportRow, ...]
    counts: FinanceImportPreviewCounts
    dispatch_summaries: tuple[FinanceDispatchSummary, ...]
    blocking_codes: tuple[str, ...]
    fingerprint: PreviewFingerprint

    @property
    def apply_allowed(self) -> bool:
        return not self.blocking_codes

    @property
    def dispatchable_rows(self) -> tuple[CanonicalFinanceImportRow, ...]:
        return tuple(
            row
            for row in self.rows
            if row.disposition is FinanceImportDisposition.CREATE
        )


def build_finance_import_plan(
    facts: FinanceImportBatchFacts,
) -> FinanceImportPlan:
    blocking_codes = _batch_blocking_codes(facts)
    planned_rows = tuple(_planned_row(row) for row in facts.rows)
    counts = _preview_counts(facts, planned_rows)
    summaries = _dispatch_summaries(planned_rows)
    fingerprint = fingerprint_payload(
        _plan_payload(facts, planned_rows, counts, summaries, blocking_codes)
    )
    return _finance_import_plan(
        facts,
        planned_rows,
        counts,
        summaries,
        blocking_codes,
        fingerprint,
    )


def mark_suspected_duplicate_client_receipts(
    rows: tuple[CanonicalFinanceImportRow, ...],
) -> tuple[CanonicalFinanceImportRow, ...]:
    seen_targets: set[tuple[str, ...]] = set()
    return tuple(
        _mark_duplicate_client_receipt(row, seen_targets)
        for row in rows
    )


def _mark_duplicate_client_receipt(row, seen_targets):
    if not _is_new_client_receipt(row):
        return row
    if row.target_identities not in seen_targets:
        seen_targets.add(row.target_identities)
        return row
    return replace(
        row,
        disposition=FinanceImportDisposition.BUSINESS_PENDING,
        evidence=tuple(
            sorted(set((*row.evidence, "suspected_duplicate_business_match")))
        ),
        available_actions=("review_suspected_duplicate_business_match",),
    )


def _is_new_client_receipt(row):
    return (
        row.classification_type is FinanceClassificationType.CLIENT_RECEIPT
        and row.disposition is FinanceImportDisposition.CREATE
        and bool(row.target_identities)
    )


def _finance_import_plan(
    facts,
    planned_rows,
    counts,
    summaries,
    blocking_codes,
    fingerprint,
):
    return FinanceImportPlan(
        facts.batch_identity,
        facts.batch_version,
        facts.source_content_digest,
        facts.classifier_version,
        facts.fingerprint_version,
        planned_rows,
        counts,
        summaries,
        blocking_codes,
        fingerprint,
    )


def _planned_row(row: CanonicalFinanceImportRow) -> CanonicalFinanceImportRow:
    blockers = _row_blocking_codes(row)
    if not blockers:
        return row
    return replace(
        row,
        disposition=FinanceImportDisposition.BLOCKED,
        integrity_violations=blockers,
    )


def _row_blocking_codes(row: CanonicalFinanceImportRow) -> tuple[str, ...]:
    blockers = set(row.integrity_violations)
    if row.fingerprint_collision:
        blockers.add("fingerprint_collision")
    if row.formal_reference_conflict:
        blockers.add("formal_reference_conflict")
    return tuple(sorted(blockers))


def _batch_blocking_codes(
    facts: FinanceImportBatchFacts,
) -> tuple[str, ...]:
    blockers = set(facts.integrity_violations)
    if not facts.batch_completed:
        blockers.add("batch_not_completed")
    if (
        facts.canonical_created_count + facts.duplicate_occurrence_count
        != facts.source_row_count
    ):
        blockers.add("occurrence_count_mismatch")
    for row in facts.rows:
        blockers.update(_row_blocking_codes(row))
    return tuple(sorted(blockers))


def _preview_counts(
    facts: FinanceImportBatchFacts,
    rows: tuple[CanonicalFinanceImportRow, ...],
) -> FinanceImportPreviewCounts:
    dispositions = tuple(row.disposition for row in rows)
    return FinanceImportPreviewCounts(
        facts.source_row_count,
        facts.canonical_created_count,
        facts.duplicate_occurrence_count,
        dispositions.count(FinanceImportDisposition.CREATE),
        dispositions.count(FinanceImportDisposition.EXISTING),
        dispositions.count(FinanceImportDisposition.MANUAL_REVIEW),
        dispositions.count(FinanceImportDisposition.BUSINESS_PENDING),
        dispositions.count(FinanceImportDisposition.BLOCKED),
    )


def _dispatch_summaries(
    rows: tuple[CanonicalFinanceImportRow, ...],
) -> tuple[FinanceDispatchSummary, ...]:
    totals: dict[FinanceClassificationType, list[int]] = {}
    for row in rows:
        if row.disposition is not FinanceImportDisposition.CREATE:
            continue
        aggregate = totals.setdefault(row.classification_type, [0, 0])
        aggregate[0] += 1
        aggregate[1] += row.amount.amount
    return tuple(
        FinanceDispatchSummary(classification_type, values[0], MoneyNTD(values[1]))
        for classification_type, values in sorted(
            totals.items(),
            key=lambda item: item[0].value,
        )
    )


def _plan_payload(facts, rows, counts, summaries, blockers):
    return {
        "batch_identity": facts.batch_identity,
        "batch_version": facts.batch_version,
        "source_content_digest": facts.source_content_digest,
        "classifier_version": facts.classifier_version,
        "fingerprint_version": facts.fingerprint_version,
        "counts": _counts_payload(counts),
        "rows": tuple(_row_payload(row) for row in rows),
        "dispatch_summaries": tuple(
            _summary_payload(summary) for summary in summaries
        ),
        "blocking_codes": blockers,
    }


def _counts_payload(counts):
    return {
        "source_rows": counts.source_rows,
        "canonical_created": counts.canonical_created,
        "duplicate_occurrences": counts.duplicate_occurrences,
        "ready_dispatch": counts.ready_dispatch,
        "existing": counts.existing,
        "manual_review": counts.manual_review,
        "business_pending": counts.business_pending,
        "blocked": counts.blocked,
    }


def _row_payload(row):
    return {
        "row_identity": row.row_identity,
        "canonical_fact_version": row.canonical_fact_version,
        "amount_ntd": row.amount.amount,
        "classification_type": row.classification_type.value,
        "disposition": row.disposition.value,
        "decision_facts_fingerprint": row.decision_facts_fingerprint.value,
        "target_identities": row.target_identities,
        "evidence": row.evidence,
        "available_actions": row.available_actions,
        "blocking_codes": _row_blocking_codes(row),
    }


def _summary_payload(summary):
    return {
        "classification_type": summary.classification_type.value,
        "candidate_count": summary.candidate_count,
        "total_amount_ntd": summary.total_amount.amount,
    }


def _validate_row_identity(row: CanonicalFinanceImportRow) -> None:
    require_canonical_text(
        row.row_identity,
        "canonical row identity",
        _IDENTITY_MAXIMUM_LENGTH,
    )
    require_nonnegative_integer(
        row.canonical_fact_version,
        "canonical fact version",
    )
    if not isinstance(row.amount, MoneyNTD):
        raise TypeError("canonical bank amount must be MoneyNTD")
    require_positive_integer(row.amount.amount, "canonical bank amount")


def _validate_row_state(row: CanonicalFinanceImportRow) -> None:
    if not isinstance(row.classification_type, FinanceClassificationType):
        raise TypeError("classification type is invalid")
    if not isinstance(row.disposition, FinanceImportDisposition):
        raise TypeError("finance import disposition is invalid")
    _validate_manual_review_state(row)
    if (
        row.disposition is FinanceImportDisposition.BLOCKED
        and not _row_blocking_codes(row)
    ):
        raise ValueError("blocked row requires a blocking root fact")


def _validate_manual_review_state(row) -> None:
    if (
        row.classification_type is FinanceClassificationType.NON_BUSINESS_REVIEW
        and row.disposition
        not in {
            FinanceImportDisposition.MANUAL_REVIEW,
            FinanceImportDisposition.BLOCKED,
        }
    ):
        raise ValueError("non-business classification must remain in review")
    if (
        row.disposition is FinanceImportDisposition.MANUAL_REVIEW
        and row.classification_type
        is not FinanceClassificationType.NON_BUSINESS_REVIEW
    ):
        raise ValueError("manual review must use non-business classification")


def _validate_batch_identity(facts: FinanceImportBatchFacts) -> None:
    require_canonical_text(
        facts.batch_identity,
        "finance import batch identity",
        _IDENTITY_MAXIMUM_LENGTH,
    )
    require_nonnegative_integer(facts.batch_version, "batch version")
    require_canonical_text(
        facts.classifier_version,
        "classifier version",
        _IDENTITY_MAXIMUM_LENGTH,
    )
    require_canonical_text(
        facts.fingerprint_version,
        "fingerprint version",
        _IDENTITY_MAXIMUM_LENGTH,
    )


def _validate_batch_counts(facts: FinanceImportBatchFacts) -> None:
    require_nonnegative_integer(facts.source_row_count, "source row count")
    require_nonnegative_integer(
        facts.canonical_created_count,
        "canonical created count",
    )
    require_nonnegative_integer(
        facts.duplicate_occurrence_count,
        "duplicate occurrence count",
    )


def _validate_batch_rows(
    rows: tuple[CanonicalFinanceImportRow, ...],
) -> None:
    if not isinstance(rows, tuple):
        raise TypeError("canonical rows must be a tuple")
    identities = tuple(row.row_identity for row in rows)
    if identities != tuple(sorted(set(identities))):
        raise ValueError("canonical rows must be sorted and unique")


def _validate_sorted_text(values: tuple[str, ...], field_name: str) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    maximum_length = (
        _EVIDENCE_MAXIMUM_LENGTH
        if field_name == "classification evidence"
        else _IDENTITY_MAXIMUM_LENGTH
    )
    for value in values:
        require_canonical_text(value, field_name, maximum_length)
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{field_name} must be sorted and unique")


__all__ = [
    "CanonicalFinanceImportRow",
    "FinanceClassificationType",
    "FinanceDispatchSummary",
    "FinanceImportBatchFacts",
    "FinanceImportDisposition",
    "FinanceImportPlan",
    "FinanceImportPreviewCounts",
    "build_finance_import_plan",
    "mark_suspected_duplicate_client_receipts",
]
