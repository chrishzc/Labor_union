"""Typed HTTP contracts for the Government Subsidy owner."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GovernmentSubsidyAllocationIntentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_identity: int = Field(gt=0)
    amount_ntd: int = Field(gt=0)


class GovernmentSubsidyReceiptIntentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finance_import_row_id: int = Field(gt=0)
    batch_id: int | None = Field(default=None, gt=0)
    allocations: list[GovernmentSubsidyAllocationIntentView] = Field(
        default_factory=list
    )


class GovernmentSubsidyReversalIntentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finance_import_row_id: int = Field(gt=0)
    source_receipt_id: int = Field(gt=0)
    allocations: list[GovernmentSubsidyAllocationIntentView] = Field(
        default_factory=list
    )


class GovernmentSubsidyClaimPlanningIntentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_year: int = Field(gt=0)
    quarter: int = Field(ge=1, le=4)
    revision: int = Field(gt=0)


class GovernmentSubsidyClaimPlanningPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: GovernmentSubsidyClaimPlanningIntentView


class GovernmentSubsidyClaimApplyFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_batch_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class GovernmentSubsidyClaimPlanningApplyBody(
    GovernmentSubsidyClaimPlanningPreviewBody,
    GovernmentSubsidyClaimApplyFields,
):
    pass


class GovernmentSubsidyClaimSubmissionPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GovernmentSubsidyClaimSubmissionApplyBody(
    GovernmentSubsidyClaimApplyFields
):
    pass


class GovernmentSubsidyApprovalItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(gt=0)
    approved_amount_ntd: int = Field(ge=0)


class GovernmentSubsidyClaimApprovalPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_approvals: list[GovernmentSubsidyApprovalItemView] = Field(
        min_length=1
    )


class GovernmentSubsidyClaimApprovalApplyBody(
    GovernmentSubsidyClaimApprovalPreviewBody,
    GovernmentSubsidyClaimApplyFields,
):
    pass


class GovernmentSubsidyItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(gt=0)
    assignment_id: int = Field(gt=0)
    case_no: str
    staff_id: int = Field(gt=0)
    claimed_hours: int = Field(gt=0)
    unit_price_ntd: int = Field(gt=0)
    requested_amount_ntd: int = Field(gt=0)
    approved_amount_ntd: int = Field(ge=0)
    net_allocated_ntd: int = Field(ge=0)
    outstanding_ntd: int = Field(ge=0)


class GovernmentSubsidyBatchView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: int = Field(gt=0)
    batch_identity: str
    batch_version: int = Field(ge=0)
    status: str
    requested_total_ntd: int = Field(ge=0)
    approved_total_ntd: int = Field(ge=0)
    net_allocated_ntd: int = Field(ge=0)
    outstanding_ntd: int = Field(ge=0)
    items: list[GovernmentSubsidyItemView]


class GovernmentSubsidyClaimBatchPageView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batches: list[GovernmentSubsidyBatchView]
    next_cursor: int | None = Field(default=None, gt=0)


class GovernmentSubsidyPlannedItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int | None = Field(default=None, gt=0)
    assignment_id: int = Field(gt=0)
    case_no: str
    staff_id: int = Field(gt=0)
    claimed_hours: int = Field(gt=0)
    unit_price_ntd: int = Field(gt=0)
    requested_amount_ntd: int = Field(gt=0)
    approved_amount_ntd: int = Field(default=0, ge=0)


class GovernmentSubsidyClaimPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    batch_id: int | None = Field(default=None, gt=0)
    batch_identity: str
    batch_version: int = Field(ge=0)
    resulting_batch_version: int = Field(gt=0)
    before_status: str | None = None
    after_status: str
    total_ntd: int = Field(ge=0)
    items: list[GovernmentSubsidyPlannedItemView]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class GovernmentSubsidyClaimReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    batch_id: int = Field(gt=0)
    batch_version: int = Field(gt=0)
    status: str
    item_count: int = Field(gt=0)
    total_ntd: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class GovernmentSubsidyAllocationCandidateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_item_id: int = Field(gt=0)
    amount_ntd: int = Field(gt=0)
    reversal_of_allocation_id: int | None = Field(default=None, gt=0)


class GovernmentSubsidyPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    bank_fact_identity: str
    batch_id: int = Field(gt=0)
    batch_version: int = Field(ge=0)
    resulting_batch_version: int = Field(gt=0)
    source_receipt_id: int | None = Field(default=None, gt=0)
    amount_ntd: int = Field(gt=0)
    allocations: list[GovernmentSubsidyAllocationCandidateView]
    before_status: str
    after_status: str
    before_net_allocated_ntd: int = Field(ge=0)
    after_net_allocated_ntd: int = Field(ge=0)
    outstanding_ntd: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class GovernmentSubsidyReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    transaction_id: int = Field(gt=0)
    batch_id: int = Field(gt=0)
    batch_version: int = Field(gt=0)
    bank_fact_identity: str
    amount_ntd: int = Field(gt=0)
    allocation_count: int = Field(gt=0)
    status: str
    outstanding_ntd: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class GovernmentSubsidyTypedErrorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


class GovernmentRefundAccountInputView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bank_code: str = Field(min_length=1, max_length=32)
    account_number: str = Field(min_length=1, max_length=191)
    account_name: str = Field(min_length=1, max_length=191)
    effective_from: str = Field(min_length=10, max_length=10)
    reason: str = Field(min_length=1, max_length=500)
    evidence_reference: str = Field(min_length=1, max_length=500)


class GovernmentPayerAccountPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: GovernmentRefundAccountInputView


class GovernmentPayerAccountApplyBody(GovernmentPayerAccountPreviewBody):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class GovernmentPayerAccountView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bank_code: str
    account_display: str
    account_name: str
    effective_from: str
    effective_until: str | None = None


class GovernmentPayerMasterView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payer_identity: str
    payer_name: str
    active_refund_account: GovernmentPayerAccountView | None = None


class GovernmentPayerAccountPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payer_identity: str
    effective_from: str
    previous_effective_from: str | None = None
    account_display: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class GovernmentPayerAccountReceiptView(GovernmentPayerAccountPreviewView):
    replayed: bool

class GovernmentSubsidyOverageReceiptIntentView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finance_import_row_id: int = Field(gt=0)
    batch_id: int = Field(gt=0)
    allocations: list[GovernmentSubsidyAllocationIntentView] = Field(min_length=1)
    evidence_reference: str = Field(min_length=1, max_length=500)

class GovernmentSubsidyOverageReceiptPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: GovernmentSubsidyOverageReceiptIntentView

class GovernmentSubsidyOverageReceiptApplyBody(GovernmentSubsidyOverageReceiptPreviewBody):
    expected_batch_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class GovernmentSubsidyOverpaymentOffsetIntentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_item_id: int = Field(gt=0)
    amount_ntd: int = Field(gt=0)


class GovernmentSubsidyOverpaymentOffsetPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overpayment_identity: str = Field(min_length=1, max_length=191)
    targets: list[GovernmentSubsidyOverpaymentOffsetIntentView] = Field(min_length=1)


class GovernmentSubsidyOverpaymentOffsetApplyBody(
    GovernmentSubsidyOverpaymentOffsetPreviewBody
):
    expected_overpayment_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)
    evidence_reference: str = Field(min_length=1, max_length=500)


class GovernmentSubsidyOverpaymentReturnPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overpayment_identity: str = Field(min_length=1, max_length=191)
    due_date: str = Field(min_length=10, max_length=10)
    evidence_reference: str = Field(min_length=1, max_length=500)


class GovernmentSubsidyOverpaymentReturnApplyBody(
    GovernmentSubsidyOverpaymentReturnPreviewBody
):
    expected_overpayment_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class GovernmentSubsidyOverpaymentDispositionPreviewBody(BaseModel):
    """One typed intent for the finite offset-or-return disposition branch."""

    model_config = ConfigDict(extra="forbid")

    overpayment_identity: str = Field(min_length=1, max_length=191)
    disposition: Literal["offset", "return"]
    targets: list[GovernmentSubsidyOverpaymentOffsetIntentView] = Field(
        default_factory=list
    )
    due_date: str | None = Field(default=None, min_length=10, max_length=10)
    evidence_reference: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_the_selected_branch_inputs(self):
        if self.disposition == "offset" and self.targets and self.due_date is None:
            return self
        if self.disposition == "offset":
            raise ValueError("government_subsidy_overpayment_offset_targets_required")
        if not self.targets and self.due_date is not None:
            return self
        raise ValueError("government_subsidy_overpayment_return_due_date_required")


class GovernmentSubsidyOverpaymentDispositionApplyBody(
    GovernmentSubsidyOverpaymentDispositionPreviewBody
):
    expected_overpayment_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class GovernmentOverpaymentReturnReconciliationPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overpayment_identity: str = Field(min_length=1, max_length=191)
    finance_import_row_id: int = Field(gt=0)


class GovernmentOverpaymentReturnReconciliationApplyBody(
    GovernmentOverpaymentReturnReconciliationPreviewBody
):
    expected_overpayment_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)
    evidence_reference: str = Field(min_length=1, max_length=500)


class GovernmentOverpaymentReturnReconciliationPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overpayment_identity: str
    overpayment_version: int = Field(ge=0)
    payable_identity: str
    bank_fact_identity: str
    amount_ntd: int = Field(gt=0)
    remaining_after_ntd: int = Field(ge=0)
    resulting_status: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class GovernmentSubsidyOverpaymentPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overpayment_identity: str
    overpayment_version: int = Field(ge=0)
    remaining_before_ntd: int = Field(ge=0)
    disposition_amount_ntd: int = Field(gt=0)
    remaining_after_ntd: int = Field(ge=0)
    resulting_status: str
    disposition_kind: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class GovernmentSubsidyOverpaymentReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overpayment_identity: str
    remaining_after_ntd: int = Field(ge=0)
    status: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    payable_identity: str | None = None


__all__ = [
    "GovernmentSubsidyAllocationCandidateView",
    "GovernmentSubsidyAllocationIntentView",
    "GovernmentSubsidyApprovalItemView",
    "GovernmentSubsidyBatchView",
    "GovernmentSubsidyClaimApprovalApplyBody",
    "GovernmentSubsidyClaimApprovalPreviewBody",
    "GovernmentSubsidyClaimBatchPageView",
    "GovernmentSubsidyClaimPlanningApplyBody",
    "GovernmentSubsidyClaimPlanningIntentView",
    "GovernmentSubsidyClaimPlanningPreviewBody",
    "GovernmentSubsidyClaimPreviewView",
    "GovernmentSubsidyClaimReceiptView",
    "GovernmentSubsidyClaimSubmissionApplyBody",
    "GovernmentSubsidyClaimSubmissionPreviewBody",
    "GovernmentSubsidyPreviewView",
    "GovernmentSubsidyReceiptIntentView",
    "GovernmentSubsidyReceiptView",
    "GovernmentSubsidyReversalIntentView",
    "GovernmentSubsidyTypedErrorView",
    "GovernmentRefundAccountInputView",
    "GovernmentPayerAccountPreviewBody",
    "GovernmentPayerAccountApplyBody",
    "GovernmentPayerAccountView",
    "GovernmentPayerMasterView",
    "GovernmentPayerAccountPreviewView",
    "GovernmentPayerAccountReceiptView",
    "GovernmentSubsidyOverpaymentOffsetApplyBody",
    "GovernmentSubsidyOverpaymentOffsetPreviewBody",
    "GovernmentSubsidyOverpaymentReturnApplyBody",
    "GovernmentSubsidyOverpaymentReturnPreviewBody",
    "GovernmentSubsidyOverpaymentDispositionApplyBody",
    "GovernmentSubsidyOverpaymentDispositionPreviewBody",
    "GovernmentOverpaymentReturnReconciliationApplyBody",
    "GovernmentOverpaymentReturnReconciliationPreviewBody",
    "GovernmentOverpaymentReturnReconciliationPreviewView",
    "GovernmentSubsidyOverpaymentPreviewView",
    "GovernmentSubsidyOverpaymentReceiptView",
]
