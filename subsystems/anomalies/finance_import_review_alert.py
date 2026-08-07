"""Project completed Finance Import review integrity into IMPORT-006.

This projection is deliberately derived from the completed import batch and
its occurrence membership.  It owns no finance facts; it only maintains the
current actionable anomaly state for an operator.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from subsystems.anomalies.system_alert_projection import (
    _decode_row,
    _now,
    _required_text,
    get_system_alert,
    upsert_system_alert,
)


ALERT_CODE = "IMPORT-006"
ALERT_LABEL = "銀行對帳匯入完整性異常"
SOURCE_DOMAIN = "IMPORT"
_SAMPLE_LIMIT = 20


def _positive_id(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _mapping_rows(rows: Any) -> list[Mapping[str, Any]]:
    if not isinstance(rows, list):
        rows = list(rows)
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError("cursor must return mapping rows")
    return rows


def _count_by(rows: list[Mapping[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(row.get(field) or "unknown") for row in rows)
    return {key: counts[key] for key in sorted(counts)}


def _partial_run_count(latest_run: Mapping[str, Any] | None) -> int:
    if latest_run is None:
        return 0
    dispatch_count = int(latest_run.get("dispatch_count") or 0)
    reconciled_count = int(latest_run.get("reconciled_count") or 0)
    pending_count = int(latest_run.get("pending_count") or 0)
    return int(dispatch_count != reconciled_count + pending_count)


def _integrity_summary(
    batch: Mapping[str, Any],
    membership_counts: Mapping[str, Any],
    inconsistent_count: int,
    latest_run: Mapping[str, Any] | None,
) -> dict[str, int]:
    expected_count = int(batch.get("row_count") or 0)
    occurrence_count = int(membership_counts.get("occurrence_count") or 0)
    distinct_count = int(membership_counts.get("distinct_count") or 0)
    missing_count = max(expected_count - occurrence_count, 0)
    unexpected_count = max(occurrence_count - expected_count, 0)
    duplicate_count = max(occurrence_count - distinct_count, 0)
    partial_count = _partial_run_count(latest_run)
    return {
        "missing_occurrence_count": missing_count,
        "unexpected_occurrence_count": unexpected_count,
        "duplicate_occurrence_count": duplicate_count,
        "non_pending_inconsistent_count": inconsistent_count,
        "partial_batch_count": partial_count,
        "integrity_inconsistent_count": (
            missing_count + unexpected_count + inconsistent_count + partial_count
        ),
    }


def project_finance_import_review_alert(cursor: Any, batch_id: int) -> dict[str, Any]:
    """Project one completed batch into its current IMPORT-006 alert state."""
    if not callable(getattr(cursor, "execute", None)):
        raise AssertionError("cursor must provide execute()")
    batch_id = _positive_id(batch_id, "batch_id")
    batch = _load_completed_batch(cursor, batch_id)
    membership_counts = _load_membership_counts(cursor, batch_id)
    rows = _load_member_rows(cursor, batch_id)
    remaining, inconsistent = _review_rows(rows)
    latest_run = _load_latest_completed_reprocess_run(cursor, batch_id)
    return _project_batch_integrity_alert(
        cursor, batch_id, batch, membership_counts, remaining, inconsistent, latest_run
    )


def _load_completed_batch(cursor: Any, batch_id: int) -> Mapping[str, Any]:
    cursor.execute(
        """SELECT id, format_id, source_file, sheet_name, header_row, row_count,
                  status, created_at, completed_at
           FROM finance_import_batches
           WHERE id=%s AND status='completed'""",
        (batch_id,),
    )
    batch = cursor.fetchone()
    if batch is None:
        raise ValueError("completed finance import batch was not found")
    if not isinstance(batch, Mapping):
        raise TypeError("cursor must return a mapping batch row")
    return batch


def _load_membership_counts(cursor: Any, batch_id: int) -> Mapping[str, Any]:
    cursor.execute(
        """SELECT COUNT(*) AS occurrence_count,
                  COUNT(DISTINCT finance_import_row_id) AS distinct_count
           FROM finance_import_occurrences
           WHERE batch_id=%s""",
        (batch_id,),
    )
    counts = cursor.fetchone()
    if not isinstance(counts, Mapping):
        raise TypeError("cursor must return mapping aggregate rows")
    return counts


def _load_member_rows(cursor: Any, batch_id: int) -> list[Mapping[str, Any]]:
    cursor.execute(
        """SELECT fir.id, fir.direction, fir.classification_type,
                  fir.classification_reason, fir.reconciliation_status
           FROM (
               SELECT DISTINCT finance_import_row_id
               FROM finance_import_occurrences
               WHERE batch_id=%s
           ) membership
           JOIN finance_import_rows fir ON fir.id=membership.finance_import_row_id
           ORDER BY fir.id""",
        (batch_id,),
    )
    return _mapping_rows(cursor.fetchall())


def _review_rows(
    rows: list[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    remaining = [
        row
        for row in rows
        if row.get("classification_type") == "non_business_review"
        and row.get("reconciliation_status") == "pending"
    ]
    inconsistent = [
        row
        for row in rows
        if row.get("classification_type") == "non_business_review"
        and row.get("reconciliation_status") != "pending"
    ]
    return remaining, inconsistent


def _load_latest_completed_reprocess_run(
    cursor: Any, batch_id: int
) -> Mapping[str, Any] | None:
    cursor.execute(
        """SELECT id, status, selected_count, changed_count, dispatch_count,
                  reconciled_count, pending_count, completed_at
           FROM finance_import_reprocess_runs
           WHERE batch_id=%s AND status='completed'
           ORDER BY completed_at DESC, id DESC
           LIMIT 1""",
        (batch_id,),
    )
    latest_run = cursor.fetchone()
    if latest_run is not None and not isinstance(latest_run, Mapping):
        raise TypeError("cursor must return a mapping reprocess row")
    return latest_run


def _project_batch_integrity_alert(
    cursor: Any,
    batch_id: int,
    batch: Mapping[str, Any],
    membership_counts: Mapping[str, Any],
    remaining: list[Mapping[str, Any]],
    inconsistent: list[Mapping[str, Any]],
    latest_run: Mapping[str, Any] | None,
) -> dict[str, Any]:
    summary = _projection_summary(batch, membership_counts, remaining, inconsistent, latest_run)
    details = _projection_details(batch_id, batch, summary, remaining, inconsistent, latest_run)
    case_key = f"finance-import-batch:{batch_id}"
    if summary["integrity_inconsistent_count"] > 0:
        result = upsert_system_alert(
            cursor,
            alert_code=ALERT_CODE,
            source_domain=SOURCE_DOMAIN,
            case_key=case_key,
            reason=ALERT_LABEL,
            details=details,
        )
    else:
        result = resolve_current_state_alert(
            cursor,
            alert_code=ALERT_CODE,
            case_key=case_key,
            reason="銀行對帳匯入已無完整性異常，自動解除",
            operator="system",
        )
    return {"alert_action": result["result"], "summary": summary, "alert": result.get("alert")}


def _projection_summary(
    batch: Mapping[str, Any],
    membership_counts: Mapping[str, Any],
    remaining: list[Mapping[str, Any]],
    inconsistent: list[Mapping[str, Any]],
    latest_run: Mapping[str, Any] | None,
) -> dict[str, Any]:
    pending_count = sum(row.get("reconciliation_status") == "pending" for row in remaining)
    summary = {
        "occurrence_count": int(membership_counts.get("occurrence_count") or 0),
        "distinct_count": int(membership_counts.get("distinct_count") or 0),
        "remaining_count": len(remaining),
        "pending_count": pending_count,
        "inconsistent_count": len(inconsistent),
        "direction_counts": _count_by(remaining, "direction"),
        "reason_counts": _count_by(remaining, "classification_reason"),
    }
    summary.update(_integrity_summary(batch, membership_counts, len(inconsistent), latest_run))
    return summary


def _projection_details(
    batch_id: int,
    batch: Mapping[str, Any],
    summary: Mapping[str, Any],
    remaining: list[Mapping[str, Any]],
    inconsistent: list[Mapping[str, Any]],
    latest_run: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_file = batch.get("source_file")
    source_name = Path(source_file).name if isinstance(source_file, str) and source_file else None
    sample_ids = [
        _positive_id(row.get("id"), "finance_import_row_id")
        for row in (remaining + inconsistent)[:_SAMPLE_LIMIT]
    ]
    return {
        "batch_id": batch_id,
        "format_id": batch.get("format_id"),
        "source_file_label": source_name,
        "sheet_name": batch.get("sheet_name"),
        "header_row": batch.get("header_row"),
        "row_count": batch.get("row_count"),
        "batch_status": batch.get("status"),
        **summary,
        "sample_row_ids": sample_ids,
        "reason_counts": [
            {"key": key, "count": count}
            for key, count in summary["reason_counts"].items()
        ],
        "last_reprocess": _last_reprocess_details(latest_run),
        "reconciliation_state": "pending",
        "occurrence_state": "materialized",
    }


def _last_reprocess_details(latest_run: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if latest_run is None:
        return None
    completed_at = latest_run.get("completed_at")
    return {
        "run_id": latest_run.get("id"),
        "status": latest_run.get("status"),
        "selected_count": latest_run.get("selected_count"),
        "changed_count": latest_run.get("changed_count"),
        "dispatch_count": latest_run.get("dispatch_count"),
        "reconciled_count": latest_run.get("reconciled_count"),
        "pending_count": latest_run.get("pending_count"),
        "completed_at": str(completed_at) if completed_at is not None else None,
    }


def scan_completed_finance_import_review_alerts(cursor: Any) -> dict[str, int]:
    """Re-project IMPORT-006 for every completed Finance Import batch."""
    if not callable(getattr(cursor, "execute", None)):
        raise AssertionError("cursor must provide execute()")
    cursor.execute(
        """SELECT id
           FROM finance_import_batches
           WHERE status='completed'
           ORDER BY id"""
    )
    batches = _mapping_rows(cursor.fetchall())
    counts = {"created": 0, "updated": 0, "reopened": 0, "resolved": 0, "unchanged": 0}
    for batch in batches:
        action = project_finance_import_review_alert(
            cursor, _positive_id(batch.get("id"), "batch_id")
        )["alert_action"]
        if action == "existing":
            counts["unchanged"] += 1
        elif action in counts:
            counts[action] += 1
        else:
            raise RuntimeError(f"unsupported IMPORT-006 projection action: {action}")
    return counts


def resolve_current_state_alert(
    cursor: Any,
    *,
    alert_code: str,
    case_key: str,
    reason: str,
    operator: str = "system",
) -> dict[str, Any]:
    """Resolve a present open alert while retaining claimed/resolved history."""
    alert_code = _required_text(alert_code, "alert_code", 50)
    case_key = _required_text(case_key, "case_key", 100)
    operator = _required_text(operator, "operator", 100)
    reason = _required_text(reason, "reason", 500)
    cursor.execute(
        """SELECT * FROM system_alerts
           WHERE alert_code=%s AND case_key=%s
           FOR UPDATE""",
        (alert_code, case_key),
    )
    alert = cursor.fetchone()
    if alert is None:
        return {"result": "existing", "alert": None}
    if alert["status"] == "resolved":
        return {"result": "existing", "alert": _decode_row(alert)}
    cursor.execute(
        """UPDATE system_alerts
           SET status='resolved', resolved_by=%s, resolved_at=%s,
               resolution_reason=%s
           WHERE id=%s""",
        (operator, _now(), reason, alert["id"]),
    )
    return {"result": "resolved", "alert": get_system_alert(cursor, alert["id"])}


__all__ = [
    "ALERT_CODE",
    "ALERT_LABEL",
    "SOURCE_DOMAIN",
    "project_finance_import_review_alert",
    "resolve_current_state_alert",
    "scan_completed_finance_import_review_alerts",
]
