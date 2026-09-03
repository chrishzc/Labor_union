"""
File: hcm_import_review.py
Description: 定義 HCM review identity、去敏證據與欄位級 warning 展開。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Mapping

from domains.anomalies.import_warning_tracking import (
    ImportWarningOccurrence,
    UnknownImportWarningIssueError,
    build_import_warning_occurrence,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


@dataclass(frozen=True, slots=True)
class HcmImportReviewRoot:
    review_identity: str
    source_event_identity: str
    source_content_digest: str
    source_sheet_identity: str
    source_row: int
    case_identity: str
    source_fingerprint: PreviewFingerprint
    issue_codes: tuple[str, ...]
    evidence_snapshot: Mapping[str, object]


def build_hcm_import_review_root(
    *,
    source_content_digest: str,
    source_sheet: str,
    source_row: int,
    case_identity: object,
    issue_codes: tuple[str, ...],
    evidence_snapshot: Mapping[str, object],
) -> HcmImportReviewRoot:
    _require_sha256(source_content_digest, "source content digest")
    if not isinstance(source_row, int) or isinstance(source_row, bool) or source_row <= 0:
        raise ValueError("source row must be a positive integer")
    normalized_issues = tuple(sorted(set(issue_codes)))
    if not normalized_issues or any(not issue.strip() for issue in normalized_issues):
        raise ValueError("issue codes must be non-empty canonical text")
    sheet_identity = _sha256_text(source_sheet.strip())
    source_identity = f"hcm-workbook:{source_content_digest}:{sheet_identity}:row:{source_row}"
    review_identity = f"hcm-review:{_sha256_text(source_identity)}"
    case_identity_value = _canonical_case_identity(case_identity, source_row)
    bounded_evidence = _bounded_evidence(evidence_snapshot)
    fingerprint = fingerprint_payload(
        {
            "source_event_identity": source_identity,
            "case_identity": case_identity_value,
            "issue_codes": normalized_issues,
            "evidence_snapshot": bounded_evidence,
        }
    )
    return HcmImportReviewRoot(
        review_identity,
        source_identity,
        source_content_digest,
        sheet_identity,
        source_row,
        case_identity_value,
        fingerprint,
        normalized_issues,
        bounded_evidence,
    )


def opened_anomaly_snapshot(root: HcmImportReviewRoot) -> dict[str, object]:
    return {
        "definition_code": "IMPORT-004",
        "review_identity": root.review_identity,
        "source_row": root.source_row,
        "case_identity": root.case_identity,
        "issue_codes": root.issue_codes,
        "active": True,
        "source_version": 1,
    }


def build_hcm_warning_occurrences(
    root: HcmImportReviewRoot,
) -> tuple[ImportWarningOccurrence, ...]:
    return build_hcm_warning_occurrences_from_review(
        source_event_identity=root.source_event_identity,
        case_identity=root.case_identity,
        issue_codes=root.issue_codes,
    )


def build_hcm_warning_occurrences_from_review(
    *,
    source_event_identity: str,
    case_identity: str,
    issue_codes: tuple[str, ...],
) -> tuple[ImportWarningOccurrence, ...]:
    if "hcm_case_import:case_import_case_no_required" in issue_codes:
        return ()
    return tuple(
        build_import_warning_occurrence(
            owning_lane="hcm",
            source_event_identity=source_event_identity,
            logical_code=_hcm_logical_code(issue_code),
            field_path=_hcm_field_path(issue_code),
            subject=case_identity,
            issue_codes=(issue_code,),
        )
        for issue_code in issue_codes
    )


def _hcm_logical_code(issue_code: str) -> str:
    if issue_code.startswith("hcm_field_missing:"):
        return "HCM-FIELD-001"
    if issue_code.startswith("hcm_field_invalid:"):
        return "HCM-FIELD-002"
    if issue_code in {
        "hcm_identity:hcm_unique_candidate",
        "hcm_identity:hcm_duplicate_application",
    }:
        return "HCM-LINK-001"
    if issue_code == "hcm_identity:hcm_identity_ambiguous":
        return "HCM-LINK-002"
    if issue_code == "hcm_case_import:case_import_existing_source_conflict":
        return "HCM-CASE-002"
    raise UnknownImportWarningIssueError(owning_lane="hcm", issue_code=issue_code)


def _hcm_field_path(issue_code: str) -> str:
    if issue_code.startswith("hcm_identity:"):
        return "$client_link"
    if issue_code.startswith("hcm_case_import:"):
        return "$source_row"
    _, separator, field_path = issue_code.partition(":")
    return field_path if separator and field_path else "$source_row"


def _bounded_evidence(snapshot: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(snapshot, Mapping):
        raise TypeError("evidence snapshot must be a mapping")
    bounded: dict[str, object] = {}
    for field, value in snapshot.items():
        field_name = str(field).strip()
        if not field_name or isinstance(value, (dict, list, tuple, set)):
            raise ValueError("evidence snapshot must contain bounded scalar values")
        if value is not None and not isinstance(value, (int, bool)):
            raise ValueError("evidence snapshot only permits bounded numeric or boolean metadata")
        bounded[field_name] = value
    return bounded


def _canonical_case_identity(case_identity: object, source_row: int) -> str:
    raw = str(case_identity or "").strip()
    return raw if raw else f"hcm-row-{source_row}"

def _require_sha256(value: str, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "HcmImportReviewRoot",
    "build_hcm_import_review_root",
    "build_hcm_warning_occurrences",
    "build_hcm_warning_occurrences_from_review",
    "opened_anomaly_snapshot",
]
