"""Strict public views for persisted historical-baseline projector state."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


_Fingerprint = str
_DeliveryStatus = Literal[
    "pending",
    "processing",
    "retryable_failed",
    "committed_unverified",
    "processed",
    "dead_letter",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HistoricalBaselineRepairReferralView(_StrictModel):
    step: StrictInt = Field(ge=1, le=11)
    contract_id: str = Field(min_length=1, max_length=191)
    owner_domain: str = Field(min_length=1, max_length=100)
    repair_target: str = Field(min_length=1, max_length=191)
    repair_capability: str = Field(min_length=1, max_length=191)


class HistoricalBaselineAlertDisplayView(_StrictModel):
    case_no: str = Field(min_length=1, max_length=50)
    earliest_blocked_step: StrictInt | None = Field(default=None, ge=1, le=11)
    active_count: StrictInt = Field(ge=0)
    repair_referrals: list[HistoricalBaselineRepairReferralView]
    projection_fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_referrals(self):
        if self.active_count != len(self.repair_referrals):
            raise ValueError("historical_baseline_referral_count_mismatch")
        expected_step = (
            None
            if not self.repair_referrals
            else min(item.step for item in self.repair_referrals)
        )
        if self.earliest_blocked_step != expected_step:
            raise ValueError("historical_baseline_earliest_step_mismatch")
        return self


class HistoricalBaselineDeliveryView(_StrictModel):
    delivery_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_trigger_identity: str = Field(min_length=1, max_length=191)
    payload_digest: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    source_kind: Literal["baseline_confirmed", "owner_repair"]
    source_domain: str = Field(min_length=1, max_length=100)
    source_event_identity: str = Field(min_length=1, max_length=191)
    source_version: StrictInt = Field(ge=0)
    partition_key: str = Field(min_length=1, max_length=191)
    projection_sequence: StrictInt | None = Field(default=None, ge=1)
    projector_receipt_identity: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    status: _DeliveryStatus
    attempt_count: StrictInt = Field(ge=0)
    max_attempts: StrictInt = Field(ge=1)
    next_attempt_at: datetime | None
    lease_expires_at: datetime | None
    last_error_code: str | None = Field(default=None, min_length=1, max_length=191)

    @model_validator(mode="after")
    def validate_delivery_state(self):
        if self.attempt_count > self.max_attempts:
            raise ValueError("historical_baseline_delivery_attempts_invalid")
        if self.status in {"committed_unverified", "processed"}:
            if self.projection_sequence is None or self.projector_receipt_identity is None:
                raise ValueError("historical_baseline_delivery_receipt_missing")
        elif self.projector_receipt_identity is not None:
            raise ValueError("historical_baseline_delivery_receipt_unexpected")
        return self


class HistoricalBaselineReceiptView(_StrictModel):
    projector_receipt_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_trigger_identity: str = Field(min_length=1, max_length=191)
    source_trigger_version: StrictInt = Field(ge=0)
    payload_digest: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(
        min_length=1,
        max_length=191,
        pattern=r"^[a-z0-9][a-z0-9._:-]{0,190}$",
    )
    case_no: str = Field(min_length=1, max_length=50)
    order_identity: str = Field(min_length=1, max_length=191)
    catalog_identity: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_version: StrictInt = Field(ge=1)
    whole_vector_fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    whole_vector_count: StrictInt = Field(ge=1)
    emitted_occurrence_set_digest: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    emitted_occurrence_set_count: StrictInt = Field(ge=0)
    active_membership_set_digest: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    active_membership_set_count: StrictInt = Field(ge=0)
    umbrella_identity: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    projection_sequence: StrictInt = Field(ge=1)
    current_alert_fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    expected_readback_digest: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    result_state: Literal["projected", "held_active"]

    @model_validator(mode="after")
    def validate_result_state(self):
        expected = "projected" if self.active_membership_set_count == 0 else "held_active"
        if self.result_state != expected:
            raise ValueError("historical_baseline_receipt_result_state_mismatch")
        return self


class HistoricalBaselineMembershipView(_StrictModel):
    membership_identity: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    set_ordinal: StrictInt = Field(ge=1)
    occurrence_identity: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")


class HistoricalBaselinePostCommitReadbackView(_StrictModel):
    readback_identity: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    readback_attempt: StrictInt = Field(ge=1)
    expected_readback_digest: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    actual_readback_digest: _Fingerprint | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    emitted_occurrence_set_digest: _Fingerprint | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    emitted_occurrence_set_count: StrictInt | None = Field(default=None, ge=0)
    active_membership_set_digest: _Fingerprint | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    active_membership_set_count: StrictInt | None = Field(default=None, ge=0)
    state_event_set_digest: _Fingerprint | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    successor_set_digest: _Fingerprint | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    workflow_event_set_digest: _Fingerprint | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    current_alert_fingerprint: _Fingerprint | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    result: Literal["exact", "mismatch", "unknown"]
    error_code: str | None = Field(default=None, min_length=1, max_length=191)

    @model_validator(mode="after")
    def validate_readback_result(self):
        if (self.result == "exact") != (self.error_code is None):
            raise ValueError("historical_baseline_readback_result_mismatch")
        return self


class HistoricalBaselineCurrentAlertView(_StrictModel):
    fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    definition_code: Literal["HISTORICAL-BASELINE-ROOTS-001"]
    definition_version: Literal[1]
    source_domain: Literal["historical_baseline"]
    source_identity: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    source_version: StrictInt = Field(ge=1)
    predicate_active: bool
    workflow_status: Literal["open", "claimed", "resolved"]
    workflow_version: StrictInt = Field(ge=0)
    projection_version: StrictInt = Field(ge=0)
    display: HistoricalBaselineAlertDisplayView

    @model_validator(mode="after")
    def validate_alert_state(self):
        if self.predicate_active != (self.display.active_count > 0):
            raise ValueError("historical_baseline_alert_predicate_mismatch")
        if (self.workflow_status == "resolved") == self.predicate_active:
            raise ValueError("historical_baseline_alert_workflow_mismatch")
        return self


class HistoricalBaselineReconciliationView(_StrictModel):
    status: Literal["processed", "not_ready", "outcome_unknown"]
    delivery_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    projector_receipt_identity: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    reason_code: str | None = Field(default=None, min_length=1, max_length=191)
    referral: Literal[
        "none",
        "wait_for_projector_commit",
        "retry_original_trigger_reconcile",
    ]


class HistoricalBaselineProjectorReadModelView(_StrictModel):
    delivery: HistoricalBaselineDeliveryView
    receipt: HistoricalBaselineReceiptView | None
    active_memberships: list[HistoricalBaselineMembershipView]
    post_commit_readback: HistoricalBaselinePostCommitReadbackView | None
    current_alert: HistoricalBaselineCurrentAlertView | None
    reconciliation: HistoricalBaselineReconciliationView

    @model_validator(mode="after")
    def validate_projection_binding(self):
        if self.reconciliation.delivery_identity != self.delivery.delivery_identity:
            raise ValueError("historical_baseline_reconciliation_delivery_mismatch")
        receipt_identity = (
            None if self.receipt is None else self.receipt.projector_receipt_identity
        )
        if self.reconciliation.projector_receipt_identity != receipt_identity:
            raise ValueError("historical_baseline_reconciliation_receipt_mismatch")
        if self.delivery.projector_receipt_identity != receipt_identity:
            raise ValueError("historical_baseline_delivery_receipt_mismatch")
        if self.receipt is None:
            if self.active_memberships or self.post_commit_readback or self.current_alert:
                raise ValueError("historical_baseline_projector_receipt_missing")
            return self
        if self.receipt.source_trigger_identity != self.delivery.source_trigger_identity:
            raise ValueError("historical_baseline_source_trigger_mismatch")
        if self.receipt.payload_digest != self.delivery.payload_digest:
            raise ValueError("historical_baseline_payload_digest_mismatch")
        if self.receipt.projection_sequence != self.delivery.projection_sequence:
            raise ValueError("historical_baseline_projection_sequence_mismatch")
        if len(self.active_memberships) != self.receipt.active_membership_set_count:
            raise ValueError("historical_baseline_membership_count_mismatch")
        if [item.set_ordinal for item in self.active_memberships] != list(
            range(1, len(self.active_memberships) + 1)
        ):
            raise ValueError("historical_baseline_membership_ordinal_mismatch")
        if self.current_alert is None:
            raise ValueError("historical_baseline_current_alert_missing")
        if self.current_alert.source_identity != self.receipt.umbrella_identity:
            raise ValueError("historical_baseline_alert_umbrella_mismatch")
        if self.current_alert.source_version != self.receipt.projection_sequence:
            raise ValueError("historical_baseline_alert_source_version_mismatch")
        if self.current_alert.display.case_no != self.receipt.case_no:
            raise ValueError("historical_baseline_alert_case_mismatch")
        if self.current_alert.display.active_count != self.receipt.active_membership_set_count:
            raise ValueError("historical_baseline_alert_count_mismatch")
        return self


__all__ = ["HistoricalBaselineProjectorReadModelView"]
