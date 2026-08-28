"""Typed read model for persisted historical-baseline projector state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from infrastructure.mysql.historical_baseline_projector_delivery import (
    HistoricalBaselineDeliveryStatus,
)
from shared_kernel.fingerprints import PreviewFingerprint


class HistoricalBaselineProjectorQueryError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class HistoricalBaselineRepairReferralView:
    step: int
    contract_id: str
    owner_domain: str
    repair_target: str
    repair_capability: str


@dataclass(frozen=True, slots=True)
class HistoricalBaselineAlertDisplayView:
    case_no: str
    earliest_blocked_step: int | None
    active_count: int
    repair_referrals: tuple[HistoricalBaselineRepairReferralView, ...]
    projection_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class HistoricalBaselineDeliveryView:
    delivery_identity: str
    source_trigger_identity: str
    payload_digest: PreviewFingerprint
    source_kind: Literal["baseline_confirmed", "owner_repair"]
    source_domain: str
    source_event_identity: str
    source_version: int
    partition_key: str
    projection_sequence: int | None
    projector_receipt_identity: str | None
    status: HistoricalBaselineDeliveryStatus
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    last_error_code: str | None


@dataclass(frozen=True, slots=True)
class HistoricalBaselineReceiptView:
    projector_receipt_identity: str
    source_trigger_identity: str
    source_trigger_version: int
    payload_digest: PreviewFingerprint
    idempotency_key: str
    case_no: str
    order_identity: str
    catalog_identity: PreviewFingerprint
    catalog_version: int
    whole_vector_fingerprint: PreviewFingerprint
    whole_vector_count: int
    emitted_occurrence_set_digest: PreviewFingerprint
    emitted_occurrence_set_count: int
    emitted_occurrence_identities: tuple[PreviewFingerprint, ...]
    active_membership_set_digest: PreviewFingerprint
    active_membership_set_count: int
    umbrella_identity: PreviewFingerprint
    projection_sequence: int
    current_alert_fingerprint: PreviewFingerprint
    expected_readback_digest: PreviewFingerprint
    result_state: Literal["projected", "held_active"]


@dataclass(frozen=True, slots=True)
class HistoricalBaselineMembershipView:
    membership_identity: PreviewFingerprint
    set_ordinal: int
    occurrence_identity: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class HistoricalBaselinePostCommitReadbackView:
    readback_identity: PreviewFingerprint
    readback_attempt: int
    expected_readback_digest: PreviewFingerprint
    actual_readback_digest: PreviewFingerprint | None
    emitted_occurrence_set_digest: PreviewFingerprint | None
    emitted_occurrence_set_count: int | None
    active_membership_set_digest: PreviewFingerprint | None
    active_membership_set_count: int | None
    state_event_set_digest: PreviewFingerprint | None
    successor_set_digest: PreviewFingerprint | None
    workflow_event_set_digest: PreviewFingerprint | None
    current_alert_fingerprint: PreviewFingerprint | None
    result: Literal["exact", "mismatch", "unknown"]
    error_code: str | None


@dataclass(frozen=True, slots=True)
class HistoricalBaselineCurrentAlertView:
    fingerprint: PreviewFingerprint
    definition_code: str
    definition_version: int
    source_domain: str
    source_identity: PreviewFingerprint
    source_version: int
    predicate_active: bool
    workflow_status: Literal["open", "claimed", "resolved"]
    workflow_version: int
    projection_version: int
    display: HistoricalBaselineAlertDisplayView


@dataclass(frozen=True, slots=True)
class HistoricalBaselineProjectorReadModel:
    delivery: HistoricalBaselineDeliveryView
    receipt: HistoricalBaselineReceiptView | None
    active_memberships: tuple[HistoricalBaselineMembershipView, ...]
    post_commit_readback: HistoricalBaselinePostCommitReadbackView | None
    current_alert: HistoricalBaselineCurrentAlertView | None

    def __post_init__(self) -> None:
        if self.receipt is None:
            if self.active_memberships or self.post_commit_readback or self.current_alert:
                raise HistoricalBaselineProjectorQueryError(
                    "projector_read_model_receipt_missing"
                )
            return
        if len(self.active_memberships) != self.receipt.active_membership_set_count:
            raise HistoricalBaselineProjectorQueryError(
                "projector_read_model_membership_count_mismatch"
            )
        if self.current_alert is None:
            raise HistoricalBaselineProjectorQueryError(
                "projector_read_model_current_alert_missing"
            )


@dataclass(frozen=True, slots=True)
class HistoricalBaselineReconcileByIdentityResult:
    status: Literal["processed", "not_ready", "outcome_unknown"]
    delivery_identity: str
    projector_receipt_identity: str | None
    reason_code: str | None
    referral: Literal[
        "none",
        "wait_for_projector_commit",
        "retry_original_trigger_reconcile",
    ]


class HistoricalBaselineProjectorReadPort(Protocol):
    def query_by_delivery_identity(
        self, delivery_identity: str
    ) -> HistoricalBaselineProjectorReadModel | None: ...

    def query_latest_by_case(
        self, case_no: str
    ) -> HistoricalBaselineProjectorReadModel | None: ...


def historical_baseline_reconcile_by_identity_disposition(
    model: HistoricalBaselineProjectorReadModel,
) -> HistoricalBaselineReconcileByIdentityResult:
    delivery = model.delivery
    receipt_identity = (
        None
        if model.receipt is None
        else model.receipt.projector_receipt_identity
    )
    if delivery.status is HistoricalBaselineDeliveryStatus.PROCESSED:
        return HistoricalBaselineReconcileByIdentityResult(
            status="processed",
            delivery_identity=delivery.delivery_identity,
            projector_receipt_identity=receipt_identity,
            reason_code=None,
            referral="none",
        )
    if delivery.status is not HistoricalBaselineDeliveryStatus.COMMITTED_UNVERIFIED:
        return HistoricalBaselineReconcileByIdentityResult(
            status="not_ready",
            delivery_identity=delivery.delivery_identity,
            projector_receipt_identity=receipt_identity,
            reason_code="projector_delivery_not_committed",
            referral="wait_for_projector_commit",
        )
    return HistoricalBaselineReconcileByIdentityResult(
        status="outcome_unknown",
        delivery_identity=delivery.delivery_identity,
        projector_receipt_identity=receipt_identity,
        reason_code="projector_emitted_occurrence_snapshot_not_persisted",
        referral="retry_original_trigger_reconcile",
    )

__all__ = [
    "HistoricalBaselineAlertDisplayView",
    "HistoricalBaselineCurrentAlertView",
    "HistoricalBaselineDeliveryView",
    "HistoricalBaselineMembershipView",
    "HistoricalBaselinePostCommitReadbackView",
    "HistoricalBaselineProjectorQueryError",
    "HistoricalBaselineProjectorReadPort",
    "HistoricalBaselineProjectorReadModel",
    "HistoricalBaselineReceiptView",
    "HistoricalBaselineReconcileByIdentityResult",
    "HistoricalBaselineRepairReferralView",
    "historical_baseline_reconcile_by_identity_disposition",
]
