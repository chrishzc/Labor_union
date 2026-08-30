"""
File: finance_import_review_alert.py
Description: 依完成匯入批次與 occurrence 完整性根事實投影 IMPORT-006。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from domains.anomalies.registry import DesiredAlertState, default_anomaly_registry
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest
from subsystems.anomalies.ports import AnomalyRuntime, require_runtime
class _BorrowedAnomalyUnitOfWork:
    """No-op unit of work: the caller's own transaction owns commit/rollback."""

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback) -> bool:
        return False

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


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
            missing_count
            + unexpected_count
            + duplicate_count
            + inconsistent_count
            + partial_count
        ),
    }


def project_finance_import_review_alert(
    cursor: Any,
    batch_id: int,
    *,
    source_version: int = 0,
    source_event_identity: str | None = None,
    runtime: AnomalyRuntime | None = None,
) -> dict[str, Any]:
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
        cursor,
        batch_id,
        batch,
        membership_counts,
        remaining,
        inconsistent,
        latest_run,
        source_version,
        source_event_identity,
        require_runtime(runtime),
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
    source_version: int,
    source_event_identity: str | None,
    runtime: AnomalyRuntime,
) -> dict[str, Any]:
    summary = _projection_summary(batch, membership_counts, remaining, inconsistent, latest_run)
    details = _projection_details(batch_id, batch, summary, remaining, inconsistent, latest_run)
    result = _project_canonical_import006_alert(
        cursor,
        batch_id,
        summary,
        details,
        source_version=source_version,
        source_event_identity=source_event_identity,
        runtime=runtime,
    )
    return {"alert_action": result["action"], "summary": summary, "alert": result["alert"]}


def _project_canonical_import006_alert(
    cursor: Any,
    batch_id: int,
    summary: Mapping[str, Any],
    details: Mapping[str, Any],
    *,
    source_version: int,
    source_event_identity: str | None,
    runtime: AnomalyRuntime,
) -> dict[str, Any]:
    """Project IMPORT-006 through the canonical registry in the caller's UoW."""
    active = summary["integrity_inconsistent_count"] > 0
    request = _canonical_projection_request(
        batch_id,
        active,
        summary,
        details,
        source_version,
        source_event_identity,
    )
    return _project_canonical_request(cursor, request, runtime)


def _canonical_projection_request(
    batch_id,
    active,
    summary,
    details,
    source_version,
    source_event_identity,
):
    event_identity = source_event_identity or _summary_event_identity(
        batch_id,
        active,
        summary,
    )
    desired = DesiredAlertState(
        definition_code=ALERT_CODE,
        source_identity=f"finance-import-batch:{batch_id}",
        source_version=source_version,
        active=active,
        fingerprint_values={"batch_id": str(batch_id)},
    )
    return ProjectAlertRequest(
        desired=desired,
        source_event_identity=event_identity,
        consumer_identity="finance-import-integrity-anomaly-source-v1",
        partition_identity=f"finance-import-integrity:{batch_id}",
        display_snapshot=dict(details),
    )


def _project_canonical_request(cursor, request, runtime: AnomalyRuntime):
    registry = default_anomaly_registry()
    repository = runtime.anomaly_repository(cursor.connection)
    already_processed = repository.checkpoint_matches(request)
    fingerprint = registry.fingerprint(request.desired)
    loaded = repository.load_current(fingerprint, for_update=True)
    previous = None if loaded is None else loaded[0]
    if already_processed:
        return {"action": "existing", "alert": _alert_view(previous)}
    application = AnomalyApplication(
        registry,
        repository,
        _BorrowedAnomalyUnitOfWork,
    )
    resulting = application.project(request)
    return {
        "action": _projection_action(previous, resulting),
        "alert": _alert_view(resulting),
    }


def _summary_event_identity(batch_id, active, summary) -> str:
    digest = fingerprint_payload(
        {"batch_id": batch_id, "active": active, "summary": dict(summary)}
    ).value
    return f"finance-import-integrity:{batch_id}:{digest}"


def _projection_action(previous, resulting) -> str:
    if resulting is None or resulting == previous:
        return "existing"
    if previous is None:
        return "created"
    if not resulting.predicate_active:
        return "resolved"
    if not previous.predicate_active:
        return "reopened"
    return "updated"


def _alert_view(projection) -> dict[str, Any] | None:
    if projection is None:
        return None
    return {
        "fingerprint": projection.fingerprint.value,
        "predicate_active": projection.predicate_active,
        "workflow_status": projection.workflow_status.value,
        "workflow_version": projection.workflow_version,
    }


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


__all__ = [
    "ALERT_CODE",
    "ALERT_LABEL",
    "SOURCE_DOMAIN",
    "project_finance_import_review_alert",
]
