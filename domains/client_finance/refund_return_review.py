"""Safe candidate for an operator-confirmed returned client refund."""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_canonical_text, require_positive_integer


@dataclass(frozen=True, slots=True)
class RefundReturnReviewSelection:
    row_identity: str
    original_refund_ledger_entry_identity: str
    case_no: str
    reason: str
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_identity(self.row_identity, "finance-import-row:")
        _require_identity(
            self.original_refund_ledger_entry_identity,
            "client-ledger-entry:",
        )
        require_canonical_text(self.case_no, "case number", 50)
        require_canonical_text(self.reason, "review reason", 500)
        _require_evidence(self.evidence)


@dataclass(frozen=True, slots=True)
class RefundReturnReviewFacts:
    batch_identity: str
    batch_version: int
    bank_amount: MoneyNTD
    bank_row_is_pending_credit: bool
    original_refund_amount: MoneyNTD
    original_refund_is_open: bool
    original_refund_case_no: str

    def __post_init__(self) -> None:
        _require_identity(self.batch_identity, "finance-import-batch:")
        require_positive_integer(self.batch_version + 1, "batch version plus one")
        require_canonical_text(self.original_refund_case_no, "refund case number", 50)
        if not isinstance(self.bank_row_is_pending_credit, bool):
            raise TypeError("bank row pending credit flag must be bool")
        if not isinstance(self.original_refund_is_open, bool):
            raise TypeError("original refund open flag must be bool")


@dataclass(frozen=True, slots=True)
class RefundReturnReviewCandidate:
    selection: RefundReturnReviewSelection
    batch_identity: str
    fingerprint: PreviewFingerprint


def build_refund_return_review_candidate(
    selection: RefundReturnReviewSelection,
    facts: RefundReturnReviewFacts,
) -> RefundReturnReviewCandidate:
    _validate_reviewable_return(selection, facts)
    return RefundReturnReviewCandidate(
        selection,
        facts.batch_identity,
        fingerprint_payload(
            {
                "row_identity": selection.row_identity,
                "original_refund_ledger_entry_identity": (
                    selection.original_refund_ledger_entry_identity
                ),
                "case_no": selection.case_no,
                "reason": selection.reason,
                "evidence": selection.evidence,
                "batch_identity": facts.batch_identity,
                "batch_version": facts.batch_version,
                "bank_amount_ntd": facts.bank_amount.amount,
                "original_refund_amount_ntd": facts.original_refund_amount.amount,
            }
        ),
    )


def _validate_reviewable_return(selection, facts) -> None:
    if not facts.bank_row_is_pending_credit:
        raise ValueError("refund_return_bank_row_not_pending_credit")
    if selection.case_no != facts.original_refund_case_no:
        raise ValueError("refund_return_case_mismatch")
    if not facts.original_refund_is_open:
        raise ValueError("refund_return_already_reversed")
    if facts.bank_amount != facts.original_refund_amount:
        raise ValueError("refund_return_amount_mismatch")


def _require_identity(value: str, prefix: str) -> None:
    require_canonical_text(value, "refund return identity", 191)
    suffix = value.removeprefix(prefix)
    if suffix == value or not suffix.isdigit() or int(suffix) <= 0:
        raise ValueError("refund_return_identity_invalid")


def _require_evidence(evidence: tuple[str, ...]) -> None:
    if not isinstance(evidence, tuple) or not evidence:
        raise ValueError("refund_return_review_evidence_required")
    if evidence != tuple(sorted(set(evidence))):
        raise ValueError("refund_return_review_evidence_invalid")
    for item in evidence:
        require_canonical_text(item, "review evidence", 500)
