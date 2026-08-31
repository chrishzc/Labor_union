"""Government Subsidy-owned anomaly remediation facts and predicates.

This module deliberately contains no persistence or generic anomaly workflow.  It
describes the three owner facts that a current-issue projection may consume and
the only correction/reconciliation shapes permitted by the Government Subsidy
contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)


class GovernmentSubsidyIntegrityRepairPath(StrEnum):
    DERIVED_REBUILD = "derived_rebuild"
    TYPED_APPEND_ONLY = "typed_append_only"
    STRUCTURAL_AMBIGUITY = "structural_ambiguity"


class GovernmentSubsidyClaimDriftRepairPath(StrEnum):
    DRAFT_REVISION = "draft_revision"
    SUBMITTED_CORRECTION = "submitted_correction"
    STRUCTURAL_AMBIGUITY = "structural_ambiguity"


class GovernmentSubsidyRecoveryStatus(StrEnum):
    OPEN = "open"
    PARTIALLY_RECONCILED = "partially_reconciled"
    RECONCILED = "reconciled"


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyIntegrityOwnerFact:
    """Fresh integrity readback for GOVSUB-003.

    A projection drift is repairable only when immutable roots are valid and the
    selected path is explicit.  Structural ambiguity remains active even when a
    caller can calculate a tempting compensating amount.
    """

    batch_id: int
    owner_version: int
    owner_snapshot_token: str
    authoritative_complete: bool
    immutable_roots_valid: bool
    projection_consistent: bool
    repair_path: GovernmentSubsidyIntegrityRepairPath

    def __post_init__(self) -> None:
        require_positive_integer(self.batch_id, "claim batch id")
        require_nonnegative_integer(self.owner_version, "owner version")
        require_canonical_text(self.owner_snapshot_token, "owner snapshot token", 191)
        _flags(
            self.authoritative_complete,
            self.immutable_roots_valid,
            self.projection_consistent,
        )
        if not isinstance(self.repair_path, GovernmentSubsidyIntegrityRepairPath):
            raise TypeError("government subsidy integrity repair path is invalid")

    @property
    def unresolved_reason_codes(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if not self.authoritative_complete:
            reasons.append("owner_readback_incomplete")
        if not self.immutable_roots_valid:
            reasons.append("immutable_roots_invalid")
        if not self.projection_consistent:
            reasons.append("projection_inconsistent")
        if self.repair_path is GovernmentSubsidyIntegrityRepairPath.STRUCTURAL_AMBIGUITY:
            reasons.append("structural_ambiguity")
        return tuple(reasons)

    @property
    def predicate_active(self) -> bool:
        return bool(self.unresolved_reason_codes)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyClaimDriftOwnerFact:
    """Fresh readback for GOVSUB-005 without rewriting frozen claim facts."""

    claim_item_id: int
    batch_id: int
    owner_version: int
    owner_snapshot_token: str
    authoritative_complete: bool
    drift_detected: bool
    submitted: bool
    frozen_claim_immutable: bool
    fresh_schedule_matches: bool
    correction_lineage_complete: bool
    financial_invariants_valid: bool
    repair_path: GovernmentSubsidyClaimDriftRepairPath
    scheduling_snapshot_identity: str
    scheduling_snapshot_token: str
    scheduling_snapshot_version: int
    revision_resolved: bool = False

    def __post_init__(self) -> None:
        require_positive_integer(self.claim_item_id, "claim item id")
        require_positive_integer(self.batch_id, "claim batch id")
        require_nonnegative_integer(self.owner_version, "owner version")
        require_canonical_text(self.owner_snapshot_token, "owner snapshot token", 191)
        require_canonical_text(
            self.scheduling_snapshot_identity,
            "scheduling snapshot identity",
            191,
        )
        require_canonical_text(
            self.scheduling_snapshot_token,
            "scheduling snapshot token",
            191,
        )
        require_nonnegative_integer(
            self.scheduling_snapshot_version,
            "scheduling snapshot version",
        )
        _flags(
            self.authoritative_complete,
            self.drift_detected,
            self.submitted,
            self.frozen_claim_immutable,
            self.fresh_schedule_matches,
            self.correction_lineage_complete,
            self.financial_invariants_valid,
            self.revision_resolved,
        )
        if not isinstance(self.repair_path, GovernmentSubsidyClaimDriftRepairPath):
            raise TypeError("government subsidy claim drift repair path is invalid")
        if not self.submitted and self.repair_path is GovernmentSubsidyClaimDriftRepairPath.SUBMITTED_CORRECTION:
            raise ValueError("submitted correction requires a submitted claim")
        if self.submitted and self.repair_path is GovernmentSubsidyClaimDriftRepairPath.DRAFT_REVISION:
            raise ValueError("draft revision cannot repair a submitted claim")

    @property
    def unresolved_reason_codes(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if not self.authoritative_complete:
            reasons.append("owner_readback_incomplete")
        if not self.frozen_claim_immutable:
            reasons.append("frozen_claim_mutated")
        if self.drift_detected:
            if self.repair_path is GovernmentSubsidyClaimDriftRepairPath.STRUCTURAL_AMBIGUITY:
                reasons.append("structural_ambiguity")
            elif not self.revision_resolved:
                reasons.append("correction_revision_pending")
            if self.submitted and not self.correction_lineage_complete:
                reasons.append("correction_lineage_incomplete")
            if not self.fresh_schedule_matches:
                reasons.append("fresh_scheduling_snapshot_mismatch")
        if not self.financial_invariants_valid:
            reasons.append("financial_invariants_invalid")
        return tuple(reasons)

    @property
    def predicate_active(self) -> bool:
        return bool(self.unresolved_reason_codes)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyRecoveryRoot:
    """Immutable Government-owned recovery root for GOVSUB-007.

    The root records the outgoing overpayment evidence.  Only a separately typed
    incoming Finance Import fact may reduce ``remaining_excess_ntd``.
    """

    recovery_identity: str
    source_outgoing_bank_fact_identity: str
    original_return_obligation_identity: str
    lawful_amount_ntd: MoneyNTD
    actual_amount_ntd: MoneyNTD
    government_payer_identity: str
    version: int
    status: GovernmentSubsidyRecoveryStatus
    actor: str
    reason: str
    evidence_reference: str
    idempotency_key: IdempotencyKey
    receipt_reference: str
    remaining_excess_ntd: MoneyNTD | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.recovery_identity, "recovery identity"),
            (self.source_outgoing_bank_fact_identity, "source outgoing bank fact identity"),
            (self.original_return_obligation_identity, "original return obligation identity"),
            (self.government_payer_identity, "government payer identity"),
            (self.actor, "actor"),
            (self.reason, "reason"),
            (self.evidence_reference, "evidence reference"),
            (self.receipt_reference, "receipt reference"),
        ):
            require_canonical_text(value, label, 500 if label == "reason" else 191)
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("recovery idempotency key is invalid")
        require_nonnegative_integer(self.version, "recovery version")
        for value, label in (
            (self.lawful_amount_ntd, "lawful amount"),
            (self.actual_amount_ntd, "actual amount"),
        ):
            if not isinstance(value, MoneyNTD) or value.amount < 0:
                raise ValueError(f"{label} must be a nonnegative integer amount")
        if self.actual_amount_ntd.amount <= self.lawful_amount_ntd.amount:
            raise ValueError("government_subsidy_recovery_excess_missing")
        if not isinstance(self.status, GovernmentSubsidyRecoveryStatus):
            raise TypeError("recovery status is invalid")
        remaining = self.remaining_excess_ntd or self.excess_amount_ntd
        if not isinstance(remaining, MoneyNTD) or not 0 <= remaining.amount <= self.excess_amount_ntd.amount:
            raise ValueError("government_subsidy_recovery_remaining_invalid")
        if self.status is GovernmentSubsidyRecoveryStatus.RECONCILED and remaining.amount != 0:
            raise ValueError("reconciled recovery must have no remaining excess")
        if self.status is GovernmentSubsidyRecoveryStatus.PARTIALLY_RECONCILED and not 0 < remaining.amount < self.excess_amount_ntd.amount:
            raise ValueError("partial recovery status is invalid")
        object.__setattr__(self, "remaining_excess_ntd", remaining)

    @property
    def excess_amount_ntd(self) -> MoneyNTD:
        return MoneyNTD(self.actual_amount_ntd.amount - self.lawful_amount_ntd.amount)

    @property
    def predicate_active(self) -> bool:
        return self.remaining_excess_ntd.amount > 0


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyIncomingRecoveryFact:
    """Typed canonical incoming bank fact used to reconcile a recovery root."""

    bank_fact_identity: str
    amount_ntd: MoneyNTD
    government_payer_identity: str
    classification_type: str = "government_subsidy"

    def __post_init__(self) -> None:
        require_canonical_text(self.bank_fact_identity, "incoming bank fact identity", 191)
        require_canonical_text(self.government_payer_identity, "government payer identity", 191)
        require_canonical_text(self.classification_type, "classification type", 100)
        if self.classification_type != "government_subsidy":
            raise ValueError("government_subsidy_recovery_bank_fact_invalid")
        if not isinstance(self.amount_ntd, MoneyNTD) or self.amount_ntd.amount <= 0:
            raise ValueError("government_subsidy_recovery_amount_invalid")


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyRecoveryReconciliationCandidate:
    recovery_identity: str
    expected_version: int
    bank_fact_identity: str
    amount_ntd: MoneyNTD
    remaining_after_ntd: MoneyNTD
    resulting_status: GovernmentSubsidyRecoveryStatus
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReturnObligationFact:
    """Locked Government-owned return obligation used by GOVSUB-007."""

    overpayment_identity: str
    payable_identity: str
    overpayment_version: int
    payable_version: int
    overpayment_remaining_ntd: MoneyNTD
    lawful_remaining_ntd: MoneyNTD
    government_payer_identity: str
    recipient_snapshot_token: str
    overpayment_status: str
    payable_status: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.overpayment_identity, "overpayment identity"),
            (self.payable_identity, "return obligation identity"),
            (self.government_payer_identity, "government payer identity"),
            (self.recipient_snapshot_token, "recipient snapshot token"),
            (self.overpayment_status, "overpayment status"),
            (self.payable_status, "return obligation status"),
        ):
            require_canonical_text(value, label, 191)
        require_nonnegative_integer(self.overpayment_version, "overpayment version")
        require_nonnegative_integer(self.payable_version, "return obligation version")
        if (
            not isinstance(self.overpayment_remaining_ntd, MoneyNTD)
            or not isinstance(self.lawful_remaining_ntd, MoneyNTD)
            or self.lawful_remaining_ntd.amount <= 0
            or self.overpayment_remaining_ntd != self.lawful_remaining_ntd
        ):
            raise ValueError("government_overpayment_return_lineage_inconsistent")
        if self.overpayment_status not in {"return_payable", "partially_returned"}:
            raise ValueError("government_overpayment_return_not_open")
        if self.payable_status not in {"payable", "partially_paid"}:
            raise ValueError("government_overpayment_return_not_open")


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyOutgoingReturnFact:
    """Fresh immutable Finance Import fact projected for one owner command."""

    finance_import_row_id: int
    bank_fact_identity: str
    direction: str
    occurred_on: date
    amount_ntd: MoneyNTD
    government_payer_identity: str
    recipient_snapshot_token: str

    def __post_init__(self) -> None:
        require_positive_integer(self.finance_import_row_id, "finance import row id")
        for value, label in (
            (self.bank_fact_identity, "outgoing bank fact identity"),
            (self.direction, "bank fact direction"),
            (self.government_payer_identity, "government payer identity"),
            (self.recipient_snapshot_token, "recipient snapshot token"),
        ):
            require_canonical_text(value, label, 191)
        if self.direction != "outgoing":
            raise ValueError("government_subsidy_bank_fact_invalid")
        if not isinstance(self.occurred_on, date):
            raise TypeError("government subsidy bank fact date is invalid")
        if not isinstance(self.amount_ntd, MoneyNTD) or self.amount_ntd.amount <= 0:
            raise ValueError("government_subsidy_bank_fact_invalid")


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReturnReconciliationWithExcessCandidate:
    overpayment_identity: str
    payable_identity: str
    recovery_identity: str
    finance_import_row_id: int
    bank_fact_identity: str
    expected_overpayment_version: int
    expected_payable_version: int
    lawful_amount_ntd: MoneyNTD
    actual_amount_ntd: MoneyNTD
    excess_amount_ntd: MoneyNTD
    government_payer_identity: str
    recipient_snapshot_token: str
    occurred_on: date
    fingerprint: PreviewFingerprint


def build_return_reconciliation_with_excess_candidate(
    obligation: GovernmentSubsidyReturnObligationFact,
    outgoing: GovernmentSubsidyOutgoingReturnFact,
) -> GovernmentSubsidyReturnReconciliationWithExcessCandidate:
    """Build only the approved actual-greater-than-lawful GOVSUB-007 branch."""

    if outgoing.government_payer_identity != obligation.government_payer_identity:
        raise ValueError("government_overpayment_return_payer_mismatch")
    if outgoing.recipient_snapshot_token != obligation.recipient_snapshot_token:
        raise ValueError("government_overpayment_return_recipient_mismatch")
    if outgoing.amount_ntd.amount <= obligation.lawful_remaining_ntd.amount:
        raise ValueError("government_overpayment_return_excess_operation_not_applicable")
    excess = MoneyNTD(
        outgoing.amount_ntd.amount - obligation.lawful_remaining_ntd.amount
    )
    recovery_identity = f"government-subsidy-recovery:{outgoing.bank_fact_identity}"
    fingerprint = fingerprint_payload(
        {
            "operation": "government_subsidy_return_reconciliation_with_excess",
            "overpayment_identity": obligation.overpayment_identity,
            "payable_identity": obligation.payable_identity,
            "overpayment_version": obligation.overpayment_version,
            "payable_version": obligation.payable_version,
            "finance_import_row_id": outgoing.finance_import_row_id,
            "bank_fact_identity": outgoing.bank_fact_identity,
            "bank_fact_date": outgoing.occurred_on.isoformat(),
            "lawful_amount_ntd": obligation.lawful_remaining_ntd.amount,
            "actual_amount_ntd": outgoing.amount_ntd.amount,
            "excess_amount_ntd": excess.amount,
            "government_payer_identity": obligation.government_payer_identity,
            "recipient_snapshot_token": obligation.recipient_snapshot_token,
        }
    )
    return GovernmentSubsidyReturnReconciliationWithExcessCandidate(
        obligation.overpayment_identity,
        obligation.payable_identity,
        recovery_identity,
        outgoing.finance_import_row_id,
        outgoing.bank_fact_identity,
        obligation.overpayment_version,
        obligation.payable_version,
        obligation.lawful_remaining_ntd,
        outgoing.amount_ntd,
        excess,
        obligation.government_payer_identity,
        obligation.recipient_snapshot_token,
        outgoing.occurred_on,
        fingerprint,
    )


def build_recovery_reconciliation_candidate(
    root: GovernmentSubsidyRecoveryRoot,
    incoming: GovernmentSubsidyIncomingRecoveryFact,
) -> GovernmentSubsidyRecoveryReconciliationCandidate:
    if incoming.government_payer_identity != root.government_payer_identity:
        raise ValueError("government_subsidy_recovery_payer_mismatch")
    if not root.predicate_active:
        raise ValueError("government_subsidy_recovery_already_reconciled")
    if incoming.amount_ntd.amount > root.remaining_excess_ntd.amount:
        raise ValueError("government_subsidy_recovery_amount_exceeded")
    remaining = MoneyNTD(root.remaining_excess_ntd.amount - incoming.amount_ntd.amount)
    status = (
        GovernmentSubsidyRecoveryStatus.RECONCILED
        if remaining.amount == 0
        else GovernmentSubsidyRecoveryStatus.PARTIALLY_RECONCILED
    )
    fingerprint = fingerprint_payload(
        {
            "recovery_identity": root.recovery_identity,
            "recovery_version": root.version,
            "bank_fact_identity": incoming.bank_fact_identity,
            "amount_ntd": incoming.amount_ntd.amount,
            "remaining_after_ntd": remaining.amount,
            "resulting_status": status.value,
        }
    )
    return GovernmentSubsidyRecoveryReconciliationCandidate(
        root.recovery_identity,
        root.version,
        incoming.bank_fact_identity,
        incoming.amount_ntd,
        remaining,
        status,
        fingerprint,
    )


def _flags(*values: bool) -> None:
    if any(type(value) is not bool for value in values):
        raise TypeError("government subsidy owner fact flags must be bool")


__all__ = [
    "GovernmentSubsidyClaimDriftOwnerFact",
    "GovernmentSubsidyClaimDriftRepairPath",
    "GovernmentSubsidyIncomingRecoveryFact",
    "GovernmentSubsidyIntegrityOwnerFact",
    "GovernmentSubsidyIntegrityRepairPath",
    "GovernmentSubsidyRecoveryReconciliationCandidate",
    "GovernmentSubsidyRecoveryRoot",
    "GovernmentSubsidyRecoveryStatus",
    "GovernmentSubsidyOutgoingReturnFact",
    "GovernmentSubsidyReturnObligationFact",
    "GovernmentSubsidyReturnReconciliationWithExcessCandidate",
    "build_return_reconciliation_with_excess_candidate",
    "build_recovery_reconciliation_candidate",
]
