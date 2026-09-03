"""
File: historical_review_remediation.py
Description: 定義歷史訂單 review 更正的canonical 候選與完成規則。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


class HistoricalReviewDisposition(StrEnum):
    CORRECTED_SOURCE_ADOPTED = "corrected_source_adopted"
    SUPERSEDED_BY_REPLACEMENT_REVIEW = "superseded_by_replacement_review"


@dataclass(frozen=True, slots=True)
class HistoricalReviewConflict:
    issue_code: str
    field_path: str
    field_label: str
    rule: str
    source_value: str
    current_value: str
    allowed_values: tuple[str, ...]
    process_blocker: str


@dataclass(frozen=True, slots=True)
class HistoricalReviewContext:
    review_identity: str
    source_event_identity: str
    source_content_digest: str
    case_identity: str
    case_no: str
    original_adoption_receipt_id: int
    original_outcome: str
    original_lifecycle_event_id: int | None
    review_version: int
    remediation_version: int
    conflicts: tuple[HistoricalReviewConflict, ...]
    order_client_name: str = ""
    prior_alert_active: bool = True


@dataclass(frozen=True, slots=True)
class HistoricalReviewCorrectionSource:
    workbook_digest: str
    source_identity: str
    source_fingerprint: str
    case_no: str | None
    client_name: str | None
    issue_codes: tuple[str, ...]
    source_row: object


@dataclass(frozen=True, slots=True)
class HistoricalReviewCorrectionCandidate:
    prior_review_identity: str
    source: HistoricalReviewCorrectionSource
    disposition: HistoricalReviewDisposition
    successor_required: bool
    blockers: tuple[str, ...]
    fingerprint: PreviewFingerprint


def build_correction_candidate(
    context: HistoricalReviewContext,
    source: HistoricalReviewCorrectionSource,
) -> HistoricalReviewCorrectionCandidate:
    if context.remediation_version != 0:
        raise ValueError("historical_order_remediation_already_applied")
    if source.case_no != context.case_no:
        raise ValueError("historical_order_correction_case_mismatch")
    if not source.client_name:
        raise ValueError("historical_order_correction_client_missing")
    if context.order_client_name and source.client_name != context.order_client_name:
        raise ValueError("historical_order_correction_client_mismatch")
    blockers = tuple(sorted(set(source.issue_codes)))
    disposition = (
        HistoricalReviewDisposition.SUPERSEDED_BY_REPLACEMENT_REVIEW
        if blockers
        else HistoricalReviewDisposition.CORRECTED_SOURCE_ADOPTED
    )
    fingerprint = fingerprint_payload(
        {
            "prior_review_identity": context.review_identity,
            "workbook_digest": source.workbook_digest,
            "source_identity": source.source_identity,
            "source_fingerprint": source.source_fingerprint,
            "disposition": disposition.value,
            "blockers": blockers,
        }
    )
    return HistoricalReviewCorrectionCandidate(
        context.review_identity,
        source,
        disposition,
        bool(blockers),
        blockers,
        fingerprint,
    )


def conflict_for_issue(
    issue_code: str, *, source_value: object = "", current_value: object = ""
) -> HistoricalReviewConflict:
    mapping = {
        "historical_status_invalid": ("status", "訂單狀態", "狀態必須是 0、1 或 2", ("0", "1", "2")),
        "historical_current_status_conflict": ("status", "訂單狀態", "來源狀態必須通過 Orders 採納規則", ("0", "1", "2")),
        "historical_order_date_range_invalid": ("service_period", "服務期間", "開始日期不得晚於結束日期", ("有效日期區間",)),
        "historical_order_start_date_invalid": ("actual_start_date", "實際開始日", "開始日必須是有效日期", ("有效日期",)),
        "historical_order_end_date_invalid": ("actual_end_date", "實際結束日", "結束日必須是有效日期", ("有效日期",)),
        "historical_staff_not_found": ("assignment.staff", "服務月嫂", "月嫂姓名必須唯一對應現有月嫂", ("唯一月嫂姓名",)),
        "historical_staff_ambiguous": ("assignment.staff", "服務月嫂", "月嫂姓名不可對應多筆主檔", ("唯一月嫂姓名",)),
        "historical_assignment_conflict": ("assignment", "服務指派", "指派必須通過 Orders 指派規則", ("不與現有有效指派衝突",)),
        "historical_assignment_evidence_insufficient": ("assignment", "服務指派期間", "必須提供可驗證的個別服務期間", ("完整開始日與結束日",)),
    }
    field_path, label, rule, allowed = mapping.get(
        issue_code,
        (issue_code, "歷史訂單欄位", "必須通過 Orders 正式規則", ("符合 Orders 正式規則的值",)),
    )
    source = str(source_value).strip() or "未保留；請核對原始匯入檔"
    current = str(current_value).strip() or "目前無可顯示值；請依欄位規則修正"
    return HistoricalReviewConflict(
        issue_code,
        field_path,
        label,
        rule,
        source,
        current,
        allowed,
        "此 review 未解除前，歷史訂單匯入待確認流程不能完成。",
    )


__all__ = [
    "HistoricalReviewConflict",
    "HistoricalReviewContext",
    "HistoricalReviewCorrectionCandidate",
    "HistoricalReviewCorrectionSource",
    "HistoricalReviewDisposition",
    "build_correction_candidate",
    "conflict_for_issue",
]
