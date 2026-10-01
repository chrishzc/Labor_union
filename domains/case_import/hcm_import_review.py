"""
File: hcm_import_review.py
Description: 定義 HCM review identity、去敏證據與欄位級 warning 展開。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time, timedelta
import hashlib
import math
import re
from typing import Mapping

from domains.anomalies.import_warning_tracking import (
    ImportWarningOccurrence,
    UnknownImportWarningIssueError,
    build_import_warning_occurrence,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from domains.case_import.client_import_validation import VALID_CITIES, validate_hcm_row
from domains.case_import.hcm_resubmission import hcm_field_targets
from domains.clients.profile import CLIENT_PROFILE_FIELD_SET, ClientProfileValidationError, validate_changes

HCM_SKIP_REJECT_REASON_PATH = "review.skip_missing_reject_reason"
HCM_SKIP_FIELD_PREFIX = "review.skip_field:"


def hcm_field_skip_path(source_field: str) -> str:
    return HCM_SKIP_FIELD_PREFIX + source_field


def validate_hcm_field_skip(*, source_field: str, unresolved_fields: tuple[str, ...], is_current: bool) -> None:
    if not is_current or source_field not in unresolved_fields:
        raise ValueError("hcm_review_skip_no_longer_available")


def validate_missing_reject_reason_skip(*, issue_codes: tuple[str, ...],
                                      reject_reason: object, already_skipped: bool,
                                      is_current: bool) -> None:
    """An explicit disposition suppresses only this missing-field warning."""
    if not is_current or already_skipped or reject_reason is not None and str(reject_reason).strip():
        raise ValueError("hcm_review_skip_no_longer_available")
    if "hcm_field_missing:不符合原因" not in issue_codes:
        raise ValueError("hcm_review_skip_field_not_allowed")


def unresolved_hcm_review_fields(
    fields: tuple[str, ...], current_values: Mapping[str, object],
) -> tuple[str, ...]:
    """Recheck original field warnings against current authoritative roots.

    Historical source evidence stays immutable. Unknown fields remain visible;
    a save only resolves fields whose current value passes the HCM field rule.
    """
    unresolved = []
    for field in fields:
        try:
            targets = hcm_field_targets(field)
        except ValueError:
            unresolved.append(field)
            continue
        value = current_values.get(targets[0])
        profile_field = targets[0].removeprefix("clients.")
        if len(targets) == 1 and targets[0].startswith("clients.") and profile_field in CLIENT_PROFILE_FIELD_SET:
            try:
                validate_changes({profile_field: value}, city_allowlist=VALID_CITIES)
            except ClientProfileValidationError:
                unresolved.append(field)
            continue
        if field == "服務時間":
            value = _current_service_time(current_values)
        if value is None or not str(value).strip() or field in validate_hcm_row({field: value}):
            unresolved.append(field)
    return tuple(unresolved)


def _current_service_time(values: Mapping[str, object]) -> str | None:
    hours = values.get("orders.service_hours_per_day")
    try:
        number = float(hours) if not isinstance(hours, bool) else 0
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not 0 < number <= 24:
        return None
    clocks = []
    for field in ("orders.service_start_time", "orders.service_end_time"):
        value = values.get(field)
        if isinstance(value, time):
            clock = value.strftime("%H:%M")
        elif isinstance(value, timedelta) and 0 <= value.total_seconds() < 86400:
            seconds = int(value.total_seconds())
            clock = f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"
        else:
            clock = str(value)
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::00)?", clock):
            return None
        clocks.append(clock[:5])
    offset = values.get("orders.service_end_day_offset")
    if isinstance(offset, bool) or offset not in (0, 1):
        return None
    return f"{number:g}小時 {clocks[0]}-{clocks[1]}"


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
    if issue_code == "hcm_case_import:case_import_bootstrap_blocked":
        return "HCM-SYSTEM-001"
    raise UnknownImportWarningIssueError(owning_lane="hcm", issue_code=issue_code)


def _hcm_field_path(issue_code: str) -> str:
    if issue_code.startswith("hcm_identity:"):
        return "$client_link"
    if issue_code == "hcm_case_import:case_import_bootstrap_blocked":
        return "$case_setup"
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
    "unresolved_hcm_review_fields",
    "unresolved_hcm_review_fields",
]
