"""
File: ingestion.py
Description: 定義 Finance 初始分類、匯入 receipt 與安全 attempt 根事實。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from domains.finance_import.planning import (
    FinanceClassificationType,
    FinanceImportDisposition,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_positive_integer

_CLASSIFICATION_MAP = {
    "client_receipt": FinanceClassificationType.CLIENT_RECEIPT,
    "client_refund": FinanceClassificationType.CLIENT_REFUND,
    "client_subsidy_return": FinanceClassificationType.CLIENT_SUBSIDY_RETURN,
    "government_subsidy": FinanceClassificationType.GOVERNMENT_SUBSIDY,
    "staff_salary": FinanceClassificationType.STAFF_PAYOUT,
    "staff_legacy_subsidy": FinanceClassificationType.STAFF_PAYOUT,
    "non_business_review": FinanceClassificationType.NON_BUSINESS_REVIEW,
}


@dataclass(frozen=True, slots=True)
class InitialClassificationFacts:
    finance_import_row_id: int
    legacy_classification_type: str
    matched_identity_ids: tuple[int, ...]
    classification_reason: str

    def __post_init__(self) -> None:
        require_positive_integer(
            self.finance_import_row_id,
            "finance import row id",
        )
        if self.legacy_classification_type not in _CLASSIFICATION_MAP:
            raise ValueError("unsupported_initial_classification")
        if not self.classification_reason.strip():
            raise ValueError("classification reason is required")


@dataclass(frozen=True, slots=True)
class InitialClassificationDecision:
    classification_type: FinanceClassificationType
    disposition: FinanceImportDisposition
    decision_facts_fingerprint: PreviewFingerprint
    target_identities: tuple[str, ...]
    evidence: tuple[str, ...]
    available_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FinanceWorkbookIngestionReceipt:
    batch_identity: str
    source_content_digest: str
    source_row_count: int
    canonical_created_count: int
    duplicate_occurrence_count: int
    source_warning_count: int = 0
    source_warning_created_count: int = 0
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class FinanceImportAttempt:
    """Safe durable result for an ingestion command that did not commit."""

    attempt_identity: str
    source_content_digest: str
    phase: str
    error_code: str | None
    transaction_outcome: Literal["committed", "rolled_back"]
    started_at: datetime
    completed_at: datetime
    batch_identity: str | None = None


# Kept cohesive so one fingerprint covers the complete initial decision.
def build_initial_classification(
    facts: InitialClassificationFacts,
) -> InitialClassificationDecision:
    classification_type = _CLASSIFICATION_MAP[
        facts.legacy_classification_type
    ]
    disposition = _initial_disposition(classification_type)
    evidence = (facts.classification_reason.strip(),)
    targets = _identity_evidence(facts)
    actions = _available_actions(disposition)
    fingerprint = fingerprint_payload(
        _decision_payload(facts, classification_type, disposition)
    )
    return InitialClassificationDecision(
        classification_type,
        disposition,
        fingerprint,
        targets,
        evidence,
        actions,
    )


def _initial_disposition(classification_type):
    if classification_type is FinanceClassificationType.NON_BUSINESS_REVIEW:
        return FinanceImportDisposition.MANUAL_REVIEW
    return FinanceImportDisposition.BUSINESS_PENDING


def _identity_evidence(facts):
    prefix = (
        "staff"
        if facts.legacy_classification_type
        in {"staff_salary", "staff_legacy_subsidy"}
        else "client"
    )
    return tuple(
        f"{prefix}:{identity}"
        for identity in sorted(set(facts.matched_identity_ids))
    )


def _available_actions(disposition):
    if disposition is FinanceImportDisposition.MANUAL_REVIEW:
        return ("preview_manual_correction",)
    return ("resolve_owning_domain_target",)


def _decision_payload(facts, classification_type, disposition):
    return {
        "finance_import_row_id": facts.finance_import_row_id,
        "legacy_classification_type": facts.legacy_classification_type,
        "classification_type": classification_type.value,
        "disposition": disposition.value,
        "matched_identity_ids": tuple(sorted(set(facts.matched_identity_ids))),
        "classification_reason": facts.classification_reason.strip(),
    }


__all__ = [
    "FinanceImportAttempt",
    "FinanceWorkbookIngestionReceipt",
    "InitialClassificationDecision",
    "InitialClassificationFacts",
    "build_initial_classification",
]
