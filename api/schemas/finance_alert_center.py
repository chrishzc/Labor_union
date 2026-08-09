"""Shared API contracts for the finance and system alert center."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
import json
from collections.abc import Mapping
from typing import Annotated, Any, Generic, Literal, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AlertFamily(str, Enum):
    FINANCE = "finance"
    SYSTEM = "system"


class AlertStatus(str, Enum):
    OPEN = "open"
    CLAIMED = "claimed"
    RESOLVED = "resolved"


class TypedErrorCode(str, Enum):
    VALIDATION_ERROR = "validation_error"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    UNAVAILABLE = "unavailable"
    INTERNAL_ERROR = "internal_error"


class AlertQuery(_ContractModel):
    family: AlertFamily
    status: AlertStatus | None = None
    alert_code: str | None = Field(default=None, min_length=1, max_length=191)
    source_domain: str | None = Field(default=None, min_length=1, max_length=100)
    limit: StrictInt = Field(default=50, ge=1, le=200)
    offset: StrictInt = Field(default=0, ge=0, le=1_000_000)


class ClaimAlertCommand(_ContractModel):
    alert_id: StrictInt = Field(..., ge=1)
    operator: str = Field(..., min_length=1, max_length=100)

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("operator is required")
        return value


class ResolveAlertCommand(ClaimAlertCommand):
    reason: str = Field(..., min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason is required")
        return value


class ScanAlertsCommand(_ContractModel):
    family: Literal[AlertFamily.SYSTEM] = AlertFamily.SYSTEM


class ClaimAlertRequest(_ContractModel):
    operator: str = Field(..., min_length=1, max_length=100)

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("operator is required")
        return value


class ResolveAlertRequest(ClaimAlertRequest):
    reason: str = Field(..., min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason is required")
        return value


class FieldErrorViewModel(_ContractModel):
    field: str = Field(..., min_length=1, max_length=191)
    message: str = Field(..., min_length=1, max_length=1000)


class TypedErrorViewModel(_ContractModel):
    code: TypedErrorCode
    message: str = Field(..., min_length=1, max_length=1000)
    field_errors: list[FieldErrorViewModel] | None = None
    retryable: bool | None = None


class AlertSummaryViewModel(_ContractModel):
    family: AlertFamily
    id: StrictInt = Field(..., ge=1)
    alert_code: str = Field(..., min_length=1, max_length=191)
    label: str = Field(..., min_length=1, max_length=255)
    source_domain: str = Field(..., min_length=1, max_length=100)
    source_reference: str = Field(..., min_length=1, max_length=255)
    reason: str = Field(..., min_length=1, max_length=1000)
    status: AlertStatus
    claimed_by: str | None = Field(default=None, max_length=100)
    claimed_at: datetime | None = None
    resolved_by: str | None = Field(default=None, max_length=100)
    resolved_at: datetime | None = None
    resolution_reason: str | None = Field(default=None, max_length=1000)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaginationViewModel(_ContractModel):
    limit: StrictInt = Field(..., ge=1, le=200)
    offset: StrictInt = Field(..., ge=0, le=1_000_000)
    returned_count: StrictInt = Field(..., ge=0)
    has_more: bool


class AlertListViewModel(_ContractModel):
    items: list[AlertSummaryViewModel]
    pagination: PaginationViewModel


JsonScalar = str | int | float | bool | None


class DisplayFieldViewModel(_ContractModel):
    name: str = Field(..., min_length=1, max_length=100)
    value: JsonScalar


class FinanceAlertEventViewModel(_ContractModel):
    id: StrictInt = Field(..., ge=1)
    event_type: str = Field(..., min_length=1, max_length=100)
    actor: str | None = Field(default=None, max_length=100)
    reason: str | None = Field(default=None, max_length=1000)
    occurred_at: datetime | None = None
    created_at: datetime | None = None
    snapshot: list[DisplayFieldViewModel] = Field(default_factory=list, max_length=20)


class FinanceAlertDetailViewModel(_ContractModel):
    kind: Literal["finance_alert"] = "finance_alert"
    alert: AlertSummaryViewModel
    expected_amount: Decimal | None = None
    actual_amount: Decimal | None = None
    difference_amount: Decimal | None = None
    candidate: list[DisplayFieldViewModel] = Field(default_factory=list, max_length=20)
    events: list[FinanceAlertEventViewModel] = Field(default_factory=list, max_length=200)


class CountByKeyViewModel(_ContractModel):
    key: str = Field(..., min_length=1, max_length=255)
    count: StrictInt = Field(..., ge=0)


class ReprocessSummaryViewModel(_ContractModel):
    run_id: StrictInt | None = Field(default=None, ge=1)
    status: str | None = Field(default=None, max_length=100)
    selected_count: StrictInt | None = Field(default=None, ge=0)
    changed_count: StrictInt | None = Field(default=None, ge=0)
    dispatch_count: StrictInt | None = Field(default=None, ge=0)
    reconciled_count: StrictInt | None = Field(default=None, ge=0)
    pending_count: StrictInt | None = Field(default=None, ge=0)
    completed_at: datetime | None = None


class ImportReviewBatchViewModel(_ContractModel):
    kind: Literal["import_review_batch"] = "import_review_batch"
    alert: AlertSummaryViewModel
    batch_id: StrictInt = Field(..., ge=1)
    format_id: str | None = Field(default=None, max_length=100)
    source_file_label: str | None = Field(default=None, max_length=255)
    batch_status: str | None = Field(default=None, max_length=100)
    row_count: StrictInt | None = Field(default=None, ge=0)
    occurrence_count: StrictInt = Field(..., ge=0)
    distinct_count: StrictInt = Field(..., ge=0)
    remaining_count: StrictInt = Field(..., ge=0)
    direction_counts: list[CountByKeyViewModel] = Field(default_factory=list)
    reason_counts: list[CountByKeyViewModel] = Field(default_factory=list)
    sample_row_ids: list[StrictInt] = Field(default_factory=list, max_length=20)
    last_reprocess: ReprocessSummaryViewModel | None = None
    classification_state: Literal["non_business_review"] = "non_business_review"
    reconciliation_state: str | None = Field(default=None, max_length=100)
    occurrence_state: str | None = Field(default=None, max_length=100)

    @field_validator("sample_row_ids")
    @classmethod
    def validate_sample_row_ids(cls, value: list[int]) -> list[int]:
        if any(isinstance(item, bool) or item < 1 for item in value):
            raise ValueError("sample_row_ids must contain positive integers")
        return value


class SystemAlertDetailViewModel(_ContractModel):
    kind: Literal["system_alert"] = "system_alert"
    alert: AlertSummaryViewModel
    details: list[DisplayFieldViewModel] = Field(default_factory=list, max_length=20)


AlertDetailViewModel = Annotated[
    Union[
        FinanceAlertDetailViewModel,
        ImportReviewBatchViewModel,
        SystemAlertDetailViewModel,
    ],
    Field(discriminator="kind"),
]


class AlertActionViewModel(_ContractModel):
    action: Literal["claim", "resolve"]
    result: Literal["existing", "claimed", "resolved"]
    message: str = Field(..., min_length=1, max_length=1000)
    alert: AlertSummaryViewModel


class ScanCodeSummaryViewModel(_ContractModel):
    alert_code: str = Field(..., min_length=1, max_length=191)
    created: StrictInt = Field(default=0, ge=0)
    updated: StrictInt = Field(default=0, ge=0)
    reopened: StrictInt = Field(default=0, ge=0)
    resolved: StrictInt = Field(default=0, ge=0)
    unchanged: StrictInt = Field(default=0, ge=0)


class ScanSummaryViewModel(_ContractModel):
    items: list[ScanCodeSummaryViewModel]


T = TypeVar("T")


class AlertCenterResponse(_ContractModel, Generic[T]):
    success: bool = True
    message: str = Field(default="Success", max_length=1000)
    data: T | None = None
    error: TypedErrorViewModel | None = None

    @field_validator("error")
    @classmethod
    def validate_error_shape(
        cls, value: TypedErrorViewModel | None, info: Any
    ) -> TypedErrorViewModel | None:
        success = info.data.get("success", True)
        if success and value is not None:
            raise ValueError("successful response must not contain an error")
        if not success and value is None:
            raise ValueError("failed response requires a typed error")
        return value


_SAFE_DISPLAY_KEYS = frozenset(
    {
        "assignment_id",
        "batch_id",
        "case_no",
        "classification_reason",
        "classification_type",
        "finance_import_row_id",
        "format_id",
        "match_id",
        "payment_stage",
        "reason",
        "reference",
        "row_id",
        "schedule_id",
        "source_id",
        "staff_id",
        "status",
        "transaction_id",
    }
)


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field} must contain valid JSON") from exc
        if isinstance(decoded, Mapping):
            return {str(key): item for key, item in decoded.items()}
    raise ValueError(f"{field} must be an object")


def _display_fields(value: Any, field: str) -> list[DisplayFieldViewModel]:
    if value in (None, "", {}):
        return []
    source = _mapping(value, field)
    result: list[DisplayFieldViewModel] = []
    for key in sorted(source):
        if key not in _SAFE_DISPLAY_KEYS:
            continue
        item = source[key]
        if item is not None and not isinstance(item, (str, int, float, bool)):
            continue
        rendered: JsonScalar = item
        if isinstance(item, str):
            rendered = item[:500]
        result.append(DisplayFieldViewModel(name=key, value=rendered))
        if len(result) == 20:
            break
    return result


def alert_summary_from_record(
    record: Mapping[str, Any],
    family: AlertFamily,
) -> AlertSummaryViewModel:
    source_reference = (
        record.get("source_id")
        or record.get("case_key")
        or record.get("finance_import_row_id")
        or record.get("finance_import_batch_id")
    )
    alert_code = record.get("alert_code")
    return AlertSummaryViewModel(
        family=family,
        id=record.get("id"),
        alert_code=alert_code,
        label=(
            "銀行對帳匯入待人工分類"
            if alert_code == "IMPORT-006"
            else str(alert_code or "")
        ),
        source_domain=record.get("source_domain"),
        source_reference=str(source_reference or ""),
        reason=record.get("reason"),
        status=record.get("status"),
        claimed_by=record.get("claimed_by"),
        claimed_at=record.get("claimed_at"),
        resolved_by=record.get("resolved_by"),
        resolved_at=record.get("resolved_at"),
        resolution_reason=record.get("resolution_reason"),
        created_at=record.get("created_at"),
        updated_at=record.get("updated_at"),
    )


def finance_alert_detail_from_record(
    record: Mapping[str, Any],
) -> FinanceAlertDetailViewModel:
    events: list[FinanceAlertEventViewModel] = []
    raw_events = record.get("events") or []
    if not isinstance(raw_events, list) or len(raw_events) > 200:
        raise ValueError("finance alert events must be a bounded list")
    for event in raw_events:
        if not isinstance(event, Mapping):
            raise ValueError("finance alert event must be an object")
        events.append(
            FinanceAlertEventViewModel(
                id=event.get("id"),
                event_type=event.get("event_type"),
                actor=event.get("actor"),
                reason=event.get("reason"),
                occurred_at=event.get("occurred_at"),
                created_at=event.get("created_at"),
                snapshot=_display_fields(
                    event.get("event_snapshot"), "event_snapshot"
                ),
            )
        )
    return FinanceAlertDetailViewModel(
        alert=alert_summary_from_record(record, AlertFamily.FINANCE),
        expected_amount=record.get("expected_amount"),
        actual_amount=record.get("actual_amount"),
        difference_amount=record.get("difference_amount"),
        candidate=_display_fields(
            record.get("candidate_snapshot"), "candidate_snapshot"
        ),
        events=events,
    )


def _count_items(value: Any, field: str) -> list[CountByKeyViewModel]:
    if value in (None, {}, []):
        return []
    if isinstance(value, list):
        if len(value) > 200:
            raise ValueError(f"{field} exceeds maximum entries")
        return [
            CountByKeyViewModel.model_validate(item)
            for item in value
        ]
    source = _mapping(value, field)
    if len(source) > 200:
        raise ValueError(f"{field} exceeds maximum entries")
    return [
        CountByKeyViewModel(key=key, count=count)
        for key, count in sorted(source.items())
    ]


def _positive_batch_id(record: Mapping[str, Any], details: Mapping[str, Any]) -> Any:
    value = details.get("batch_id") or record.get("finance_import_batch_id")
    if value is None:
        case_key = str(record.get("case_key") or "")
        prefix = "finance-import-batch:"
        if case_key.startswith(prefix):
            value = case_key[len(prefix) :]
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    return value


def system_alert_detail_from_record(
    record: Mapping[str, Any],
) -> ImportReviewBatchViewModel | SystemAlertDetailViewModel:
    summary = alert_summary_from_record(record, AlertFamily.SYSTEM)
    details = _mapping(record.get("details"), "details")
    if record.get("alert_code") != "IMPORT-006":
        return SystemAlertDetailViewModel(
            alert=summary,
            details=_display_fields(details, "details"),
        )
    raw_samples = details.get("sample_row_ids") or []
    if not isinstance(raw_samples, list):
        raise ValueError("sample_row_ids must be a list")
    raw_reprocess = details.get("last_reprocess_summary")
    if raw_reprocess is None:
        raw_reprocess = details.get("last_reprocess")
    if raw_reprocess:
        reprocess = _mapping(raw_reprocess, "last_reprocess")
        last_reprocess = ReprocessSummaryViewModel(
            run_id=reprocess.get("run_id") or reprocess.get("id"),
            status=reprocess.get("status"),
            selected_count=reprocess.get("selected_count"),
            changed_count=reprocess.get("changed_count"),
            dispatch_count=reprocess.get("dispatch_count"),
            reconciled_count=reprocess.get("reconciled_count"),
            pending_count=reprocess.get("pending_count"),
            completed_at=reprocess.get("completed_at"),
        )
    else:
        last_reprocess = None
    source_file_label = details.get("source_file_label")
    if source_file_label is None and details.get("source_file"):
        source_file_label = (
            str(details["source_file"]).replace("\\", "/").rsplit("/", 1)[-1]
        )
    return ImportReviewBatchViewModel(
        alert=summary,
        batch_id=_positive_batch_id(record, details),
        format_id=details.get("format_id"),
        source_file_label=source_file_label,
        batch_status=details.get("batch_status"),
        row_count=details.get("row_count"),
        occurrence_count=details.get("occurrence_count"),
        distinct_count=details.get("distinct_count"),
        remaining_count=details.get("remaining_count"),
        direction_counts=_count_items(
            details.get("direction_counts"), "direction_counts"
        ),
        reason_counts=_count_items(details.get("reason_counts"), "reason_counts"),
        sample_row_ids=raw_samples[:20],
        last_reprocess=last_reprocess,
        reconciliation_state=details.get("reconciliation_state"),
        occurrence_state=details.get("occurrence_state"),
    )


def action_view_from_result(
    result: Mapping[str, Any],
    *,
    family: AlertFamily,
    action: Literal["claim", "resolve"],
) -> AlertActionViewModel:
    outcome = result.get("result")
    if outcome not in {"existing", "claimed", "resolved"}:
        raise ValueError("unsupported alert workflow result")
    alert = result.get("alert")
    if not isinstance(alert, Mapping):
        raise ValueError("alert workflow result has no alert")
    return AlertActionViewModel(
        action=action,
        result=outcome,
        message=(
            "警示已認領"
            if outcome == "claimed"
            else "警示已解除"
            if outcome == "resolved"
            else "相同操作已完成"
        ),
        alert=alert_summary_from_record(alert, family),
    )


def scan_summary_from_result(
    result: Mapping[str, Any],
) -> ScanSummaryViewModel:
    items: list[ScanCodeSummaryViewModel] = []
    for alert_code, raw_counts in sorted(result.items()):
        if not isinstance(raw_counts, Mapping):
            raise ValueError("scan summary item must be an object")
        items.append(
            ScanCodeSummaryViewModel(
                alert_code=str(alert_code),
                created=raw_counts.get("created", 0),
                updated=raw_counts.get("updated", 0),
                reopened=raw_counts.get("reopened", 0),
                resolved=raw_counts.get("resolved", 0),
                unchanged=raw_counts.get("unchanged", 0),
            )
        )
    return ScanSummaryViewModel(items=items)


__all__ = [
    "AlertActionViewModel",
    "AlertCenterResponse",
    "AlertDetailViewModel",
    "AlertFamily",
    "AlertListViewModel",
    "AlertQuery",
    "AlertStatus",
    "AlertSummaryViewModel",
    "ClaimAlertCommand",
    "ClaimAlertRequest",
    "CountByKeyViewModel",
    "DisplayFieldViewModel",
    "FinanceAlertDetailViewModel",
    "FinanceAlertEventViewModel",
    "ImportReviewBatchViewModel",
    "PaginationViewModel",
    "ReprocessSummaryViewModel",
    "ResolveAlertCommand",
    "ResolveAlertRequest",
    "ScanAlertsCommand",
    "ScanCodeSummaryViewModel",
    "ScanSummaryViewModel",
    "SystemAlertDetailViewModel",
    "TypedErrorCode",
    "TypedErrorViewModel",
    "action_view_from_result",
    "alert_summary_from_record",
    "finance_alert_detail_from_record",
    "scan_summary_from_result",
    "system_alert_detail_from_record",
]
