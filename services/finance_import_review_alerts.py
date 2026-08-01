"""Materialize unresolved finance-import review rows as one system alert per batch."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from services.system_alert_service import (
    resolve_current_state_alert,
    upsert_system_alert,
)


ALERT_CODE = "IMPORT-006"
ALERT_LABEL = "銀行對帳匯入待人工分類"
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


def _count_by(
    rows: list[Mapping[str, Any]],
    field: str,
) -> dict[str, int]:
    counts = Counter(
        str(row.get(field) or "unknown")
        for row in rows
    )
    return {key: counts[key] for key in sorted(counts)}


def project_finance_import_review_alert(
    cursor: Any,
    batch_id: int,
) -> dict[str, Any]:
    """Project the current review state for one completed import batch."""
    assert callable(getattr(cursor, "execute", None)), "cursor must provide execute()"
    batch_id = _positive_id(batch_id, "batch_id")
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

    cursor.execute(
        """SELECT COUNT(*) AS occurrence_count,
                  COUNT(DISTINCT finance_import_row_id) AS distinct_count
           FROM finance_import_occurrences
           WHERE batch_id=%s""",
        (batch_id,),
    )
    membership_counts = cursor.fetchone()
    if not isinstance(membership_counts, Mapping):
        raise TypeError("cursor must return mapping aggregate rows")

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
    rows = _mapping_rows(cursor.fetchall())
    remaining = [
        row for row in rows
        if row.get("classification_type") == "non_business_review"
        and row.get("reconciliation_status") == "pending"
    ]
    inconsistent = [
        row for row in rows
        if row.get("classification_type") == "non_business_review"
        and row.get("reconciliation_status") != "pending"
    ]
    pending_count = sum(
        row.get("reconciliation_status") == "pending" for row in rows
    )

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

    source_file = batch.get("source_file")
    source_name = (
        Path(source_file).name
        if isinstance(source_file, str) and source_file
        else None
    )
    sample_ids = [
        _positive_id(row.get("id"), "finance_import_row_id")
        for row in (remaining + inconsistent)[:_SAMPLE_LIMIT]
    ]
    summary = {
        "occurrence_count": int(membership_counts.get("occurrence_count") or 0),
        "distinct_count": int(membership_counts.get("distinct_count") or 0),
        "remaining_count": len(remaining),
        "pending_count": pending_count,
        "inconsistent_count": len(inconsistent),
        "direction_counts": _count_by(remaining, "direction"),
        "reason_counts": _count_by(remaining, "classification_reason"),
    }
    details = {
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
        "last_reprocess": (
            {
                "run_id": latest_run.get("id"),
                "status": latest_run.get("status"),
                "selected_count": latest_run.get("selected_count"),
                "changed_count": latest_run.get("changed_count"),
                "dispatch_count": latest_run.get("dispatch_count"),
                "reconciled_count": latest_run.get("reconciled_count"),
                "pending_count": latest_run.get("pending_count"),
                "completed_at": (
                    str(latest_run.get("completed_at"))
                    if latest_run.get("completed_at") is not None
                    else None
                ),
            }
            if latest_run is not None
            else None
        ),
        "reconciliation_state": "pending",
        "occurrence_state": "materialized",
    }
    case_key = f"finance-import-batch:{batch_id}"
    if remaining or inconsistent:
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
            reason="銀行對帳匯入已無待人工分類流水，自動解除",
            operator="system",
        )
    return {
        "alert_action": result["result"],
        "summary": summary,
        "alert": result.get("alert"),
    }


def scan_completed_finance_import_review_alerts(
    cursor: Any,
) -> dict[str, int]:
    """Refresh IMPORT-006 for every completed batch without reclassification."""
    assert callable(getattr(cursor, "execute", None)), "cursor must provide execute()"
    cursor.execute(
        """SELECT id
           FROM finance_import_batches
           WHERE status='completed'
           ORDER BY id"""
    )
    batches = _mapping_rows(cursor.fetchall())
    counts = {
        "created": 0,
        "updated": 0,
        "reopened": 0,
        "resolved": 0,
        "unchanged": 0,
    }
    for batch in batches:
        result = project_finance_import_review_alert(
            cursor,
            _positive_id(batch.get("id"), "batch_id"),
        )
        action = result["alert_action"]
        if action == "existing":
            counts["unchanged"] += 1
        elif action in counts:
            counts[action] += 1
        else:
            raise RuntimeError(f"unsupported IMPORT-006 projection action: {action}")
    return counts
