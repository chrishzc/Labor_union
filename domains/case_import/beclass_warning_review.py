"""
File: beclass_warning_review.py
Description: 映射 BeClass 已登錄 issue、姓名追溯狀態、明確 no-warning 與未知狀態。
"""

from __future__ import annotations

from dataclasses import replace

from domains.anomalies.import_warning_tracking import (
    ImportWarningOccurrence,
    ImportWarningTrackingStatus,
    UnknownImportWarningIssueError,
    build_import_warning_occurrence,
)
from domains.case_import.beclass_import_review import BeClassImportSourceKind


def build_beclass_warning_occurrences(
    *,
    source_kind: BeClassImportSourceKind,
    source_event_identity: str,
    identifier: str,
    issue_codes: tuple[str, ...],
) -> tuple[ImportWarningOccurrence, ...]:
    warnings: list[ImportWarningOccurrence] = []
    for issue_code in issue_codes:
        mapped = _warning_type(source_kind, issue_code)
        if mapped is None:
            if _is_explicit_no_warning(source_kind, issue_code):
                continue
            raise UnknownImportWarningIssueError(
                owning_lane=f"beclass_{source_kind.value}", issue_code=issue_code
            )
        logical_code, field_path = mapped
        warning = build_import_warning_occurrence(
            owning_lane=f"beclass_{source_kind.value}",
            source_event_identity=source_event_identity,
            logical_code=logical_code,
            field_path=field_path,
            subject=identifier,
            issue_codes=(issue_code,),
        )
        if (
            source_kind is BeClassImportSourceKind.STAFF
            and issue_code == "historical_name_changed"
        ):
            warning = replace(
                warning,
                tracking_status=ImportWarningTrackingStatus.AUTO_RESOLVED,
            )
        warnings.append(warning)
    return tuple(warnings)


def _warning_type(
    source_kind: BeClassImportSourceKind, issue_code: str
) -> tuple[str, str] | None:
    if source_kind is BeClassImportSourceKind.CLIENT:
        if issue_code.startswith("client_field_missing:"):
            return "CLIENT-BECLASS-SOURCE-001", issue_code.removeprefix(
                "client_field_missing:"
            )
        if issue_code.startswith("client_field_invalid:"):
            return "CLIENT-BECLASS-SOURCE-001", issue_code.removeprefix(
                "client_field_invalid:"
            )
        if issue_code in {
            "查詢序號",
            "姓名",
            "報名時間",
            "行動電話",
            "Email",
            "縣市",
            "出生年",
            "補助款退款:銀行代號+分行代號",
        }:
            return "CLIENT-BECLASS-SOURCE-001", issue_code
        if issue_code == "client_beclass_source_payload_conflict":
            return "CLIENT-BECLASS-SOURCE-001", "$source_row"
        if issue_code == "client_case_binding_not_unique":
            return "CLIENT-BECLASS-BIND-003", "$case_link"
        if issue_code == "client_case_binding_no_client":
            return "CLIENT-BECLASS-BIND-001", "$client_link"
        if issue_code == "client_case_binding_multiple_clients":
            return "CLIENT-BECLASS-BIND-002", "$client_link"
        if issue_code == "client_case_binding_case_not_unique":
            return "CLIENT-BECLASS-BIND-003", "$case_link"
        if issue_code == "case_import_cooking_requirement_ambiguous":
            return "CLIENT-BECLASS-SOURCE-001", "$requires_cooking"
        return None
    if source_kind is BeClassImportSourceKind.STAFF:
        if issue_code == "身分證字號":
            return "STAFF-BECLASS-IDENTITY-001", "身分證字號"
        if issue_code == "姓名":
            return "STAFF-BECLASS-NAME-001", "姓名"
        if issue_code == "duplicate_identity_card":
            return "STAFF-BECLASS-IDENTITY-002", "$identity_card"
        if issue_code == "identity_name_mismatch":
            return "STAFF-BECLASS-FIELD-002", "姓名"
        if issue_code == "blocked_identity":
            return "STAFF-BECLASS-IDENTITY-001", "身分證字號"
        if issue_code == "identity_conflict":
            return "STAFF-BECLASS-IDENTITY-002", "$identity_card"
        if issue_code.startswith("staff_field_invalid:"):
            return "STAFF-BECLASS-FIELD-002", issue_code.removeprefix(
                "staff_field_invalid:"
            )
        if issue_code.startswith("historical_nonempty_conflict:"):
            return "STAFF-BECLASS-FIELD-002", issue_code.removeprefix(
                "historical_nonempty_conflict:"
            )
        if issue_code == "historical_name_changed":
            return "STAFF-BECLASS-NAME-002", "姓名"
        if issue_code in {
            "報名時間",
            "民國出生年月日",
            "行動電話",
            "EMAIL",
            "縣市",
            "銀行代3碼+分行代號4碼",
        }:
            return "STAFF-BECLASS-FIELD-002", issue_code
    return None


def _is_explicit_no_warning(
    source_kind: BeClassImportSourceKind, issue_code: str
) -> bool:
    if source_kind is BeClassImportSourceKind.CLIENT:
        return issue_code == "duplicate_query_no"
    return False


__all__ = ["build_beclass_warning_occurrences"]
