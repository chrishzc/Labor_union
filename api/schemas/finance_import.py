"""
File: finance_import.py
Description: 定義 Finance Import Preview、Apply、receipt 與 correction 的嚴格 HTTP schema。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ManualStatementBody(_StrictModel):
    fields: dict[str, str | StrictInt | None]
    duplicate_of: str | None = Field(default=None, min_length=1, max_length=191)


class StatementDuplicateBody(_StrictModel):
    candidate_identity: str = Field(min_length=1, max_length=191)
    kept_identity: str = Field(min_length=1, max_length=191)


class StatementCommandReceiptView(_StrictModel):
    identity: str | None
    saved_count: int
    excluded_count: int


class AccountingWarningBody(_StrictModel):
    item_identity: str = Field(min_length=1, max_length=191)
    kind: Literal["over_received", "over_paid", "under_paid"]
    expected_ntd: StrictInt
    actual_ntd: StrictInt
    difference_ntd: StrictInt
    source_version: str = Field(min_length=1, max_length=191)


class AccountingWarningView(AccountingWarningBody):
    dismissed: bool
    dismissed_by: str | None
    dismissed_at: str | None


class AccountingItemView(_StrictModel):
    identity: str
    direction: Literal["receivable", "payable"]
    label: str
    party: str
    expected_ntd: int
    actual_ntd: int
    has_payment: bool
    version: str
    due_date: str | None
    summary_included: bool = True
    unallocated_surplus_ntd: int = 0
    remaining_ntd: int | None = None
    noncash_ntd: int = 0
    settled: bool = False
    recognized_ntd: int = 0
    payment_stage: Literal["deposit", "first", "second"] | None = None


class AccountingTransactionView(_StrictModel):
    identity: str
    item_identity: str
    occurred_on: str
    kind: str
    amount_ntd: int
    bank: str | None


class AccountingBankFactView(_StrictModel):
    identity: str
    occurred_on: str
    direction: Literal["in", "out"]
    amount_ntd: int
    cases: list[str]
    bank: str | None = None
    cash_flow: Literal["C", "G", "PS", "PT", "RS", "RT"] | None = None


class HistoricalAccountingAmountView(_StrictModel):
    identity: str
    direction: Literal["receivable", "payable"]
    expected_ntd: int
    actual_ntd: int
    remaining_ntd: int


class HistoricalAccountingMarkerView(_StrictModel):
    case_no: str
    reason: str
    actor: str
    created_at: str
    amounts: list[HistoricalAccountingAmountView] = Field(default_factory=list)


class ArrangementEventView(_StrictModel):
    version: int = Field(gt=0)
    action: Literal["confirm_direct", "withdraw_direct"]
    reason: str
    actor: str
    created_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


class CaseArrangementView(_StrictModel):
    case_no: str
    version: int = Field(ge=0)
    events: list[ArrangementEventView] = Field(default_factory=list)


class ArrangementApplyView(_StrictModel):
    case_no: str
    applied_version: int = Field(gt=0)
    arrangement: CaseArrangementView


class ArrangementBody(_StrictModel):
    action: Literal["confirm_direct", "withdraw_direct"]
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=0, strict=True)


class SubsidyPlanEventView(_StrictModel):
    version: int = Field(gt=0)
    scheme: Literal["split", "advance", "direct"]
    actor: str
    created_at: str


class CaseSubsidyPlanView(_StrictModel):
    case_no: str
    version: int = Field(ge=0)
    events: list[SubsidyPlanEventView] = Field(default_factory=list)


class SubsidyPlanBody(_StrictModel):
    scheme: Literal["split", "advance", "direct"]
    expected_version: int = Field(ge=0, strict=True)


class SubsidyPlanApplyView(_StrictModel):
    case_no: str
    applied_version: int = Field(gt=0)
    plan: CaseSubsidyPlanView


class CollectionProgressView(_StrictModel):
    stage: Literal["deposit", "first", "second", "scheme"]
    sources_complete: bool
    expected_ntd: int | None = None
    received_ntd: int | None = None
    remaining_ntd: int | None = None
    due_date: str | None = None


class CaseAccountingView(_StrictModel):
    case_no: str
    client_name: str
    receivable_ntd: int | None
    received_ntd: int | None
    payable_ntd: int | None
    paid_ntd: int | None
    pending_warning_count: int
    client_items: list[AccountingItemView]
    staff_items: list[AccountingItemView]
    transactions: list[AccountingTransactionView]
    warnings: list[AccountingWarningView]
    bank_facts: list[AccountingBankFactView] = Field(default_factory=list)
    historical_marker: HistoricalAccountingMarkerView | None = None
    remaining_in_ntd: int | None = None
    remaining_out_ntd: int | None = None
    staff_receivable_ntd: int | None = None
    customer_amount_ntd: int | None = None
    customer_fully_received: bool | None = None
    subsidy_ntd: int | None = None
    scheme: Literal["unknown", "waiting", "split", "advance", "direct"] = "unknown"
    cash_by_flow: dict[Literal["C", "G", "PS", "PT", "RS", "RT"], int] | None = None
    cash_net_ntd: int | None = None
    customer_burden_ntd: int | None = None
    arrangement: CaseArrangementView | None = None
    scheme_conflict: bool = False
    can_confirm_direct: bool = False
    collection_progress: CollectionProgressView | None = None
    subsidy_plan: CaseSubsidyPlanView | None = None
    ongoing_completed: bool = False


class FinanceImportBatchPreviewBody(_StrictModel):
    batch_identity: str = Field(min_length=1, max_length=191)


class FinanceImportBatchSummaryView(_StrictModel):
    batch_id: int = Field(gt=0)
    batch_identity: str | None
    format_id: str
    source_file: str | None
    row_count: int = Field(ge=0)
    status: str
    batch_version: int | None = Field(default=None, ge=0)
    architecture_ready: bool
    created_at: str


class FinanceImportBatchManifestView(_StrictModel):
    batch_id: int = Field(gt=0)
    batch_identity: str
    format_id: str
    source_file: str | None
    sheet_name: str
    header_row: int = Field(gt=0)
    source_row_count: int = Field(ge=0)
    status: str
    batch_version: int = Field(ge=0)
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    classifier_version: str
    fingerprint_version: str
    canonical_row_count: int = Field(ge=0)
    occurrence_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    dispatch_event_count: int = Field(ge=0)
    reconciliation_receipt_count: int = Field(ge=0)
    created_at: str
    completed_at: str | None


class FinanceImportReviewRowSummaryView(_StrictModel):
    row_id: int = Field(gt=0)
    row_identity: str
    transaction_date: str | None
    direction: str
    amount_ntd: int = Field(gt=0)
    classification_type: str
    bank_type: Literal["receivable", "payable", "government_subsidy", "subsidy_return", "review", "legacy"] = "legacy"
    disposition: str
    reconciliation_status: str
    source_sheet: str
    source_row: int = Field(gt=0)
    occurrence_count: int = Field(gt=0)
    available_actions: list[str]
    created_at: str


class FinanceImportSourceReviewSummaryView(_StrictModel):
    review_id: int = Field(gt=0)
    review_identity: str
    source_sheet: str
    source_row: int = Field(gt=0)
    issue_codes: list[str]
    created_at: str


class FinanceImportReviewRowPageView(_StrictModel):
    batch_identity: str
    source_reviews: list[FinanceImportSourceReviewSummaryView]
    next_after_source_review_id: int | None = Field(default=None, gt=0)
    items: list[FinanceImportReviewRowSummaryView]
    next_after_row_id: int | None = Field(default=None, gt=0)


class FinanceBankReconciliationTargetView(_StrictModel):
    case_no: str
    obligation_identities: list[str] = Field(min_length=1)
    staff_id: int | None = Field(default=None, gt=0)


class FinanceBankTransactionView(_StrictModel):
    row_id: int
    row_identity: str
    transaction_date: str | None
    bank: Literal["sinopac", "taishin"]
    direction: Literal["incoming", "outgoing", "unknown"]
    amount_ntd: int
    classification_type: str
    status: Literal["pending", "posted"]
    disposition: str
    review_reason: str | None
    available_actions: list[str]
    reference: str
    counterparty_name: str | None
    cases: list[str]
    reconciliation_target: FinanceBankReconciliationTargetView | None = None


class FinanceBankTransactionPageView(_StrictModel):
    items: list[FinanceBankTransactionView]
    pending_count: int | None
    next_before_row_id: int | None


class FinanceImportHistoryEntryView(_StrictModel):
    identity: str
    started_at: str
    bank: Literal["sinopac", "taishin"] | None
    source_file: str | None
    status: Literal["saved", "posting", "posted", "blocked", "posting_failed", "failed", "legacy"]
    new_count: int | None
    duplicate_count: int | None
    reconciled_count: int | None
    pending_count: int | None
    source_warning_count: int | None
    error_code: str | None


class FinanceImportHistoryPageView(_StrictModel):
    items: list[FinanceImportHistoryEntryView]
    next_before: str | None


class FinanceImportReprocessRunSummaryView(_StrictModel):
    run_id: int = Field(gt=0)
    batch_identity: str
    classifier_version: str
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_count: int = Field(ge=0)
    changed_count: int = Field(ge=0)
    dispatch_count: int = Field(ge=0)
    reconciled_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    status: str
    created_at: str
    completed_at: str


class FinanceImportReprocessRunPageView(_StrictModel):
    items: list[FinanceImportReprocessRunSummaryView]
    next_before_run_id: int | None = Field(default=None, gt=0)


class FinanceWorkbookIngestionReceiptView(_StrictModel):
    batch_identity: str
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    canonical_created_count: int = Field(ge=0)
    duplicate_occurrence_count: int = Field(ge=0)
    source_warning_count: int = Field(default=0, ge=0)
    source_warning_created_count: int = Field(default=0, ge=0)
    replayed: bool = False


class FinanceImportJobAcceptedView(_StrictModel):
    """Accepted Finance Import command with its exact idempotency replay state."""

    job_id: str = Field(min_length=1, max_length=191)
    status_url: str = Field(min_length=1, max_length=255)
    replayed: bool


class FinanceImportIngestionOutcomeView(_StrictModel):
    status: Literal["committed", "rolled_back", "unknown"]
    receipt: FinanceWorkbookIngestionReceiptView | None
    source_content_digest: str | None
    error_code: str | None
    phase: str | None


class FinanceImportBatchApplyBody(FinanceImportBatchPreviewBody):
    expected_batch_version: StrictInt = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(default="", max_length=500)


class HistoricalOwnerSelectionBody(_StrictModel):
    row_identity: str = Field(min_length=1, max_length=191)
    case_no: str = Field(min_length=1, max_length=50)
    obligation_identity: str = Field(min_length=1, max_length=191)
    reason: str = Field(default="", max_length=500)
    evidence_references: list[str] = Field(min_length=1)


class FinanceImportHistoricalReprocessPreviewBody(_StrictModel):
    batch_identity: str = Field(min_length=1, max_length=191)
    owner_selections: list[HistoricalOwnerSelectionBody] = Field(default_factory=list)


class FinanceImportHistoricalReprocessApplyBody(
    FinanceImportHistoricalReprocessPreviewBody
):
    expected_batch_version: StrictInt = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(default="", max_length=500)


class FinanceImportHistoricalReprocessPlanView(_StrictModel):
    batch_identity: str
    batch_version: int = Field(ge=0)
    row_count: int = Field(ge=1)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_selections: list[HistoricalOwnerSelectionBody] = Field(default_factory=list)


class FinanceImportHistoricalReprocessReceiptView(_StrictModel):
    batch_identity: str
    resulting_batch_version: int = Field(gt=0)
    reprocess_run_id: int = Field(gt=0)
    reclassified_count: int = Field(ge=0)
    dispatched_count: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class FinanceImportPreviewCountsView(_StrictModel):
    source_rows: int = Field(ge=0)
    canonical_created: int = Field(ge=0)
    duplicate_occurrences: int = Field(ge=0)
    ready_dispatch: int = Field(ge=0)
    existing: int = Field(ge=0)
    manual_review: int = Field(ge=0)
    business_pending: int = Field(ge=0)
    blocked: int = Field(ge=0)


class FinanceImportDispatchSummaryView(_StrictModel):
    classification_type: str
    candidate_count: int = Field(ge=0)
    total_amount_ntd: int = Field(ge=0)


class FinanceImportRowView(_StrictModel):
    row_identity: str
    canonical_fact_version: int = Field(ge=0)
    amount_ntd: int = Field(gt=0)
    classification_type: str
    disposition: str
    target_identities: list[str]
    evidence: list[str]
    available_actions: list[str]
    integrity_violations: list[str]
    fingerprint_collision: bool
    formal_reference_conflict: bool


class FinanceImportBatchPreviewView(_StrictModel):
    batch_identity: str
    batch_version: int = Field(ge=0)
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    classifier_version: str
    fingerprint_version: str
    counts: FinanceImportPreviewCountsView
    dispatch_summaries: list[FinanceImportDispatchSummaryView]
    rows: list[FinanceImportRowView]
    blocking_codes: list[str]
    apply_allowed: bool
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class FinanceImportBatchReceiptView(_StrictModel):
    batch_identity: str
    resulting_batch_version: int = Field(gt=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reconciled_count: int = Field(ge=0)
    existing_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)


class FinanceImportBatchJobOutcomeView(_StrictModel):
    """Closed terminal view for a batch Apply durable job; never exposes raw payloads."""

    job_id: str = Field(min_length=1, max_length=191)
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(ge=0)
    result_reference: str | None = Field(default=None, min_length=1, max_length=191)
    receipt: FinanceImportBatchReceiptView | None = None


class FinanceImportCorrectionSelectionBody(_StrictModel):
    row_identity: str = Field(min_length=1, max_length=191)
    classification_type: Literal[
        "client_receipt",
        "client_refund",
        "client_refund_return",
        "client_subsidy_return",
        "government_subsidy",
        "staff_payout",
    ]
    target_obligation_identities: list[str] = Field(min_length=1)
    refund_ledger_entry_identity: str | None = Field(default=None, min_length=1, max_length=191)
    allow_partial_refund_recovery: bool = False
    allow_refund_overage_recovery: bool = False
    allow_client_receipt_overage: bool = False
    reason: str = Field(default="", max_length=500)
    evidence: list[str] = Field(min_length=1)


class FinanceImportCorrectionApplyBody(FinanceImportCorrectionSelectionBody):
    expected_batch_version: StrictInt = Field(ge=0)
    expected_canonical_fact_version: StrictInt = Field(ge=0)
    expected_alert_version: StrictInt = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class FinanceImportCorrectionAllocationView(_StrictModel):
    obligation_identity: str
    amount_ntd: int = Field(gt=0)


class FinanceImportCorrectionCandidateView(_StrictModel):
    row_identity: str
    batch_identity: str
    classification_type: str
    owning_domain: str
    bank_amount_ntd: int = Field(gt=0)
    allocations: list[FinanceImportCorrectionAllocationView]
    reason: str
    evidence: list[str]
    refund_ledger_entry_identity: str | None = None
    allow_partial_refund_recovery: bool = False
    allow_refund_overage_recovery: bool = False
    allow_client_receipt_overage: bool = False
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class FinanceImportCorrectionPreviewView(_StrictModel):
    candidate: FinanceImportCorrectionCandidateView
    batch_version: int = Field(ge=0)
    canonical_fact_version: int = Field(ge=0)
    alert_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class FinanceImportCorrectionReceiptView(_StrictModel):
    row_identity: str
    batch_identity: str
    resulting_batch_version: int = Field(gt=0)
    classification_event_count: int = Field(gt=0)
    ledger_entry_count: int = Field(gt=0)
    allocation_count: int = Field(gt=0)
    reconciliation_receipt_count: int = Field(gt=0)
    alert_resolved_event_count: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class FinanceImportCorrectionJobOutcomeView(_StrictModel):
    """Closed terminal view for a correction durable job; never exposes raw payloads."""

    job_id: str = Field(min_length=1, max_length=191)
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(ge=0)
    result_reference: str | None = Field(default=None, min_length=1, max_length=191)
    receipt: FinanceImportCorrectionReceiptView | None = None


class RefundReturnReviewPreviewBody(_StrictModel):
    finance_import_row_id: StrictInt = Field(gt=0)
    original_refund_ledger_entry_id: StrictInt = Field(gt=0)
    case_no: str = Field(min_length=1, max_length=50)
    reason: str = Field(default="", max_length=500)
    evidence: list[str] = Field(min_length=1)


class RefundReturnReviewApplyBody(RefundReturnReviewPreviewBody):
    expected_batch_version: StrictInt = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class RefundReturnReviewPreviewView(_StrictModel):
    batch_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_identity: str
    original_refund_ledger_entry_identity: str


class RefundReturnReviewReceiptView(_StrictModel):
    review_event_identity: str
    row_identity: str
    original_refund_ledger_entry_identity: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class FinanceImportTypedErrorView(_StrictModel):
    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


__all__ = [
    "FinanceImportBatchApplyBody",
    "FinanceImportBatchJobOutcomeView",
    "FinanceImportBatchManifestView",
    "FinanceImportBatchPreviewBody",
    "FinanceImportBatchPreviewView",
    "FinanceImportBatchReceiptView",
    "FinanceImportBatchSummaryView",
    "FinanceImportCorrectionApplyBody",
    "FinanceImportCorrectionJobOutcomeView",
    "FinanceImportCorrectionPreviewView",
    "FinanceImportCorrectionReceiptView",
    "FinanceImportCorrectionSelectionBody",
    "FinanceImportHistoricalReprocessApplyBody",
    "FinanceImportHistoricalReprocessPlanView",
    "FinanceImportHistoricalReprocessPreviewBody",
    "FinanceImportHistoricalReprocessReceiptView",
    "FinanceImportJobAcceptedView",
    "HistoricalOwnerSelectionBody",
    "FinanceImportReprocessRunPageView",
    "FinanceImportReprocessRunSummaryView",
    "FinanceImportReviewRowPageView",
    "FinanceImportReviewRowSummaryView",
    "FinanceImportTypedErrorView",
    "FinanceWorkbookIngestionReceiptView",
    "RefundReturnReviewApplyBody",
    "RefundReturnReviewPreviewBody",
    "RefundReturnReviewPreviewView",
    "RefundReturnReviewReceiptView",
]
