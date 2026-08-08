"""Explicit, auditable reclassification of one completed finance import batch."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import json
import re
import time as clock
from typing import Any

from scripts.imports.finance_normalized_row import validate_normalized_row
from services.db_service import get_connection
from services.finance_identity_maps import load_finance_identity_maps
from services.finance_import_dispatch import dispatch_finance_import_row
from services.finance_import_review_alerts import (
    project_finance_import_review_alert,
)
from domains.finance_import.transaction_classifier import classify_finance_transaction


CLASSIFIER_VERSION = "finance_transaction_classifier:v1"
DEFAULT_SAFETY_LIMIT = 5000
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_DERIVED_FIELDS = (
    "classification_type",
    "classification_reason",
    "matched_identity_ids",
    "resolved_counterparty_account",
)


def _positive_id(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=_json_default,
    )


def _strict_json(value: Any, field: str, expected: type) -> Any:
    if isinstance(value, expected):
        decoded = value
    elif isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field} contains invalid JSON") from exc
    else:
        raise ValueError(f"{field} must be {expected.__name__} JSON")
    if not isinstance(decoded, expected):
        raise ValueError(f"{field} must decode to {expected.__name__}")
    return decoded


def _iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return date.fromisoformat(value[:10]).isoformat()
    raise ValueError("canonical date value is invalid")


def _iso_time(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value.replace(microsecond=0).isoformat()
    if isinstance(value, str):
        return time.fromisoformat(value).replace(microsecond=0).isoformat()
    raise ValueError("canonical time value is invalid")


def _normalized_row(row: Mapping[str, Any]) -> dict[str, Any]:
    fingerprint = row.get("dedup_fingerprint")
    if not isinstance(fingerprint, str) or not _FINGERPRINT.fullmatch(fingerprint):
        raise ValueError("canonical row fingerprint is invalid")
    normalized = {
        "format_id": row.get("format_id"),
        "source_file": row.get("source_file"),
        "source_bank_account": row.get("source_bank_account"),
        "sheet_name": row.get("sheet_name"),
        "source_row": row.get("source_row"),
        "source_reference": row.get("source_reference"),
        "transaction_date": _iso_date(row.get("transaction_date")),
        "transaction_time": _iso_time(row.get("transaction_time")),
        "posting_date": _iso_date(row.get("posting_date")),
        "value_date": _iso_date(row.get("value_date")),
        "debit": row.get("debit"),
        "credit": row.get("credit"),
        "direction": row.get("direction"),
        "balance": row.get("balance"),
        "currency": row.get("currency"),
        "summary": row.get("summary"),
        "memo": row.get("memo"),
        "counterparty_name": row.get("counterparty_name"),
        "counterparty_account": row.get("counterparty_account"),
        "cancellation_code": row.get("cancellation_code"),
        "bank_references": _strict_json(
            row.get("bank_references"),
            "bank_references",
            dict,
        ),
        "warnings": _strict_json(row.get("warnings"), "warnings", list),
        "raw_payload": _strict_json(
            row.get("raw_payload"),
            "raw_payload",
            dict,
        ),
    }
    return validate_normalized_row(normalized)


def _identity_ids(value: Any, field: str) -> list[int]:
    decoded = _strict_json(value, field, list)
    if any(
        isinstance(item, bool) or not isinstance(item, int) or item < 1
        for item in decoded
    ):
        raise ValueError(f"{field} must contain positive integer ids")
    return decoded


def _before_tuple(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "classification_type": row.get("classification_type"),
        "classification_reason": row.get("classification_reason"),
        "matched_identity_ids": _identity_ids(
            row.get("matched_identity_ids"),
            "matched_identity_ids",
        ),
        "resolved_counterparty_account": row.get(
            "resolved_counterparty_account"
        ),
    }


def _after_tuple(classification: Mapping[str, Any]) -> dict[str, Any]:
    identities = classification.get("matched_identity_ids")
    if not isinstance(identities, list):
        raise ValueError("classifier matched_identity_ids must be a list")
    if any(
        isinstance(item, bool) or not isinstance(item, int) or item < 1
        for item in identities
    ):
        raise ValueError("classifier matched_identity_ids are invalid")
    return {
        "classification_type": classification.get("classification_type"),
        "classification_reason": classification.get("reason"),
        "matched_identity_ids": identities,
        "resolved_counterparty_account": classification.get(
            "resolved_counterparty_account"
        ),
    }


def _formal_transaction_exists(cursor: Any, row_id: int) -> bool:
    cursor.execute(
        """SELECT
             EXISTS(
               SELECT 1 FROM client_payment_transactions
               WHERE finance_import_row_id=%s
             ) AS client_tx,
             EXISTS(
               SELECT 1 FROM government_subsidy_transactions
               WHERE finance_import_row_id=%s
             ) AS government_tx,
             EXISTS(
               SELECT 1 FROM staff_actual_transfers
               WHERE raw_import_reference=%s
             ) AS staff_tx""",
        (row_id, row_id, f"finance_import_row:{row_id}"),
    )
    result = cursor.fetchone()
    if not isinstance(result, Mapping):
        raise TypeError("cursor must return a mapping transaction check")
    return any(bool(result.get(key)) for key in ("client_tx", "government_tx", "staff_tx"))


def _db_identity(cursor: Any) -> dict[str, str]:
    cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server_name")
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise TypeError("cursor must return a mapping DB identity")
    database = row.get("database_name")
    server = row.get("server_name")
    if not isinstance(database, str) or not database:
        raise RuntimeError("database identity is unavailable")
    return {"database": database, "server": str(server or "")}


def _plan_fingerprint(
    db_identity: Mapping[str, str],
    batch_id: int,
    plans: list[dict[str, Any]],
) -> str:
    payload = {
        "db_identity": dict(db_identity),
        "batch_id": batch_id,
        "classifier_version": CLASSIFIER_VERSION,
        "rows": [
            {
                "row_id": plan["row_id"],
                "before": plan["before"],
                "after": plan["after"],
            }
            for plan in plans
        ],
    }
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _reason_counts(
    plans: list[dict[str, Any]],
    side: str,
) -> dict[str, int]:
    counts = Counter(
        str(plan[side].get("classification_reason") or "none")
        for plan in plans
    )
    return {key: counts[key] for key in sorted(counts)}


def _decode_stored_json(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        decoded = json.loads(value)
        if isinstance(decoded, dict):
            return decoded
    raise ValueError("stored reprocess summary is invalid")


def _replay_conflict() -> RuntimeError:
    return RuntimeError("finance import reprocess replay is partial or stale")


def _stored_event_tuple(
    event: Mapping[str, Any],
    prefix: str,
) -> dict[str, Any]:
    return {
        "classification_type": event.get(f"{prefix}_classification_type"),
        "classification_reason": event.get(
            f"{prefix}_classification_reason"
        ),
        "matched_identity_ids": _identity_ids(
            event.get(f"{prefix}_matched_identity_ids"),
            f"{prefix}_matched_identity_ids",
        ),
        "resolved_counterparty_account": event.get(
            f"{prefix}_resolved_counterparty_account"
        ),
    }


def _validate_replay_dispatch_state(
    cursor: Any,
    row: Mapping[str, Any],
    event: Mapping[str, Any],
) -> tuple[bool, bool]:
    classification_type = event.get("after_classification_type")
    dispatch_result = event.get("dispatch_result")
    is_business = classification_type != "non_business_review"
    if is_business and dispatch_result not in {
        "reconciled",
        "existing",
        "pending",
    }:
        raise _replay_conflict()
    if not is_business and dispatch_result != "not_dispatched":
        raise _replay_conflict()

    formal_transaction = _formal_transaction_exists(
        cursor,
        _positive_id(row.get("id"), "finance_import_row_id"),
    )
    reconciliation_status = row.get("reconciliation_status")
    if dispatch_result in {"reconciled", "existing"}:
        if not formal_transaction or reconciliation_status != "reconciled":
            raise _replay_conflict()
        return True, False
    if formal_transaction or reconciliation_status != "pending":
        raise _replay_conflict()
    return False, dispatch_result == "pending"


def _validate_existing_run(
    cursor: Any,
    *,
    run: Mapping[str, Any],
    batch_id: int,
    expected_plan_fingerprint: str,
    db_identity: dict[str, str],
    safety_limit: int,
) -> dict[str, Any]:
    run_id = _positive_id(run.get("id"), "reprocess_run_id")
    if run.get("classifier_version") != CLASSIFIER_VERSION:
        raise _replay_conflict()
    result_summary = _decode_stored_json(run.get("result_summary"))
    classification_summary = result_summary.get("classification_summary")
    dispatch_summary = result_summary.get("dispatch_summary")
    batch_manifest = result_summary.get("batch_manifest")
    if not all(
        isinstance(value, Mapping)
        for value in (
            classification_summary,
            dispatch_summary,
            batch_manifest,
        )
    ):
        raise _replay_conflict()

    count_fields = (
        "selected_count",
        "changed_count",
        "dispatch_count",
        "reconciled_count",
        "pending_count",
    )
    try:
        counts = {field: int(run.get(field)) for field in count_fields}
    except (TypeError, ValueError) as exc:
        raise _replay_conflict() from exc
    if (
        counts["selected_count"] > safety_limit
        or counts["changed_count"] > counts["selected_count"]
        or counts["dispatch_count"] > counts["changed_count"]
        or counts["reconciled_count"] + counts["pending_count"]
        > counts["dispatch_count"]
        or int(batch_manifest.get("batch_id")) != batch_id
        or int(batch_manifest.get("selected_distinct_count"))
        != counts["selected_count"]
        or int(classification_summary.get("selected"))
        != counts["selected_count"]
        or int(classification_summary.get("changed"))
        != counts["changed_count"]
        or int(dispatch_summary.get("attempted"))
        != counts["dispatch_count"]
        or int(dispatch_summary.get("reconciled"))
        != counts["reconciled_count"]
        or int(dispatch_summary.get("pending"))
        != counts["pending_count"]
    ):
        raise _replay_conflict()

    cursor.execute(
        """SELECT COUNT(DISTINCT finance_import_row_id) AS distinct_count
           FROM finance_import_occurrences
           WHERE batch_id=%s""",
        (batch_id,),
    )
    membership = cursor.fetchone()
    if (
        not isinstance(membership, Mapping)
        or int(membership.get("distinct_count") or 0)
        != counts["selected_count"]
    ):
        raise _replay_conflict()

    cursor.execute(
        """SELECT finance_import_row_id,
                  before_classification_type,
                  before_classification_reason,
                  before_matched_identity_ids,
                  before_resolved_counterparty_account,
                  after_classification_type,
                  after_classification_reason,
                  after_matched_identity_ids,
                  after_resolved_counterparty_account,
                  dispatch_result
           FROM finance_import_reclassification_events
           WHERE run_id=%s
           ORDER BY finance_import_row_id
           FOR UPDATE""",
        (run_id,),
    )
    events = list(cursor.fetchall())
    if (
        len(events) != counts["changed_count"]
        or any(not isinstance(event, Mapping) for event in events)
    ):
        raise _replay_conflict()
    event_ids = [
        _positive_id(
            event.get("finance_import_row_id"),
            "finance_import_row_id",
        )
        for event in events
    ]
    if len(set(event_ids)) != len(event_ids):
        raise _replay_conflict()

    event_rows: dict[int, Mapping[str, Any]] = {}
    if event_ids:
        placeholders = ", ".join(["%s"] * len(event_ids))
        cursor.execute(
            f"""SELECT fir.*
                FROM finance_import_rows fir
                JOIN (
                    SELECT DISTINCT finance_import_row_id
                    FROM finance_import_occurrences
                    WHERE batch_id=%s
                ) membership
                  ON membership.finance_import_row_id=fir.id
                WHERE fir.id IN ({placeholders})
                ORDER BY fir.id
                FOR UPDATE""",
            (batch_id, *event_ids),
        )
        current_event_rows = list(cursor.fetchall())
        if (
            len(current_event_rows) != len(event_ids)
            or any(
                not isinstance(row, Mapping)
                for row in current_event_rows
            )
        ):
            raise _replay_conflict()
        event_rows = {
            _positive_id(row.get("id"), "finance_import_row_id"): row
            for row in current_event_rows
        }

    cursor.execute(
        """SELECT fir.*
           FROM finance_import_rows fir
           JOIN (
               SELECT DISTINCT finance_import_row_id
               FROM finance_import_occurrences
               WHERE batch_id=%s
           ) membership
             ON membership.finance_import_row_id=fir.id
           WHERE fir.classification_type='non_business_review'
             AND fir.reconciliation_status='pending'
           ORDER BY fir.id
           FOR UPDATE""",
        (batch_id,),
    )
    eligible_rows = list(cursor.fetchall())
    if any(not isinstance(row, Mapping) for row in eligible_rows):
        raise _replay_conflict()
    event_id_set = set(event_ids)
    unchanged_rows = [
        row
        for row in eligible_rows
        if _positive_id(row.get("id"), "finance_import_row_id")
        not in event_id_set
    ]
    if len(event_ids) + len(unchanged_rows) != counts["selected_count"]:
        raise _replay_conflict()

    identity_maps = load_finance_identity_maps(cursor)
    plans: list[dict[str, Any]] = []
    dispatch_count = 0
    reconciled_count = 0
    pending_count = 0
    for event, row_id in zip(events, event_ids, strict=True):
        row = event_rows.get(row_id)
        if row is None:
            raise _replay_conflict()
        before = _stored_event_tuple(event, "before")
        after = _stored_event_tuple(event, "after")
        if before == after or _before_tuple(row) != after:
            raise _replay_conflict()
        normalized = _normalized_row(row)
        live_after = _after_tuple(
            classify_finance_transaction(
                normalized,
                identity_maps["client_refund_accounts"],
                identity_maps["staff_accounts"],
            )
        )
        if live_after != after:
            raise _replay_conflict()
        reconciled, pending = _validate_replay_dispatch_state(
            cursor,
            row,
            event,
        )
        if after["classification_type"] != "non_business_review":
            dispatch_count += 1
        reconciled_count += int(reconciled)
        pending_count += int(pending)
        plans.append({"row_id": row_id, "before": before, "after": after})

    for row in unchanged_rows:
        row_id = _positive_id(row.get("id"), "finance_import_row_id")
        if _formal_transaction_exists(cursor, row_id):
            raise _replay_conflict()
        before = _before_tuple(row)
        after = _after_tuple(
            classify_finance_transaction(
                _normalized_row(row),
                identity_maps["client_refund_accounts"],
                identity_maps["staff_accounts"],
            )
        )
        if before != after:
            raise _replay_conflict()
        plans.append({"row_id": row_id, "before": before, "after": after})

    plans.sort(key=lambda plan: plan["row_id"])
    if (
        dispatch_count != counts["dispatch_count"]
        or reconciled_count != counts["reconciled_count"]
        or pending_count != counts["pending_count"]
        or _plan_fingerprint(db_identity, batch_id, plans)
        != expected_plan_fingerprint
    ):
        raise _replay_conflict()
    return result_summary


def _existing_result(
    cursor: Any,
    *,
    batch_id: int,
    expected_plan_fingerprint: str,
    db_identity: dict[str, str],
    safety_limit: int,
) -> dict[str, Any] | None:
    cursor.execute(
        """SELECT id, actor, classifier_version, selected_count,
                  changed_count, dispatch_count, reconciled_count,
                  pending_count, request_summary, result_summary
           FROM finance_import_reprocess_runs
           WHERE batch_id=%s AND plan_fingerprint=%s AND status='completed'
           FOR UPDATE""",
        (batch_id, expected_plan_fingerprint),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    if not isinstance(row, Mapping):
        raise TypeError("cursor must return a mapping reprocess run")
    result_summary = _validate_existing_run(
        cursor,
        run=row,
        batch_id=batch_id,
        expected_plan_fingerprint=expected_plan_fingerprint,
        db_identity=db_identity,
        safety_limit=safety_limit,
    )
    alert_projection = project_finance_import_review_alert(cursor, batch_id)
    return {
        "db_identity": db_identity,
        **result_summary,
        "alert_action": alert_projection,
        "plan_fingerprint": expected_plan_fingerprint,
        "transaction_outcome": "existing",
        "run_id": row.get("id"),
    }


def reprocess_finance_import_batch(
    batch_id: int,
    *,
    actor: str | None = None,
    dry_run: bool = True,
    expected_plan_fingerprint: str | None = None,
    safety_limit: int = DEFAULT_SAFETY_LIMIT,
) -> dict[str, Any]:
    """Reclassify one completed batch in one connection-owned transaction."""
    assert callable(get_connection), "database connection factory is required"
    batch_id = _positive_id(batch_id, "batch_id")
    if not isinstance(dry_run, bool):
        raise TypeError("dry_run must be a boolean")
    if isinstance(safety_limit, bool) or not isinstance(safety_limit, int) or safety_limit < 1:
        raise ValueError("safety_limit must be a positive integer")
    if not dry_run:
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("actor is required for apply")
        if (
            not isinstance(expected_plan_fingerprint, str)
            or not _FINGERPRINT.fullmatch(expected_plan_fingerprint)
        ):
            raise ValueError("expected_plan_fingerprint is required for apply")
    effective_actor = actor.strip() if isinstance(actor, str) and actor.strip() else "dry-run"
    started = clock.monotonic()
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            identity = _db_identity(cursor)
            cursor.execute(
                """SELECT id, format_id, source_file, sheet_name, header_row,
                          row_count, status, created_at, completed_at
                   FROM finance_import_batches
                   WHERE id=%s AND status='completed'
                   FOR UPDATE""",
                (batch_id,),
            )
            batch = cursor.fetchone()
            if not isinstance(batch, Mapping):
                raise ValueError("completed finance import batch was not found")
            if not dry_run:
                existing = _existing_result(
                    cursor,
                    batch_id=batch_id,
                    expected_plan_fingerprint=expected_plan_fingerprint,
                    db_identity=identity,
                    safety_limit=safety_limit,
                )
                if existing is not None:
                    connection.rollback()
                    return existing

            cursor.execute(
                """SELECT DISTINCT fir.id AS finance_import_row_id
                   FROM finance_import_occurrences occurrence
                   JOIN finance_import_rows fir
                     ON fir.id=occurrence.finance_import_row_id
                   WHERE occurrence.batch_id=%s
                     AND fir.classification_type='non_business_review'
                     AND fir.reconciliation_status='pending'
                   ORDER BY fir.id""",
                (batch_id,),
            )
            candidate_records = list(cursor.fetchall())
            if any(not isinstance(row, Mapping) for row in candidate_records):
                raise TypeError("cursor must return mapping candidate rows")
            candidate_ids = [
                _positive_id(row.get("finance_import_row_id"), "finance_import_row_id")
                for row in candidate_records
            ]
            if len(candidate_ids) > safety_limit:
                raise ValueError("eligible rows exceed safety_limit")

            rows: list[Mapping[str, Any]] = []
            if candidate_ids:
                placeholders = ", ".join(["%s"] * len(candidate_ids))
                cursor.execute(
                    f"""SELECT fir.*
                        FROM finance_import_rows fir
                        WHERE fir.id IN ({placeholders})
                          AND fir.classification_type='non_business_review'
                          AND fir.reconciliation_status='pending'
                        ORDER BY fir.id
                        FOR UPDATE""",
                    tuple(candidate_ids),
                )
                rows = list(cursor.fetchall())
            if any(not isinstance(row, Mapping) for row in rows):
                raise TypeError("cursor must return mapping canonical rows")
            locked_ids = [
                _positive_id(row.get("id"), "finance_import_row_id")
                for row in rows
            ]
            if locked_ids != candidate_ids:
                raise RuntimeError("eligible rows changed before lock acquisition")

            identity_maps = load_finance_identity_maps(cursor)
            plans: list[dict[str, Any]] = []
            for row in rows:
                row_id = _positive_id(row.get("id"), "finance_import_row_id")
                if _formal_transaction_exists(cursor, row_id):
                    raise RuntimeError(
                        "eligible non_business_review row already has a formal transaction"
                    )
                normalized = _normalized_row(row)
                before = _before_tuple(row)
                classification = classify_finance_transaction(
                    normalized,
                    identity_maps["client_refund_accounts"],
                    identity_maps["staff_accounts"],
                )
                plans.append(
                    {
                        "row_id": row_id,
                        "before": before,
                        "after": _after_tuple(classification),
                    }
                )

            plan_fingerprint = _plan_fingerprint(
                identity,
                batch_id,
                plans,
            )
            if not dry_run and plan_fingerprint != expected_plan_fingerprint:
                raise RuntimeError("finance import reprocess plan is stale")

            changed_plans = [
                plan for plan in plans if plan["before"] != plan["after"]
            ]
            events: list[dict[str, Any]] = []
            dispatch_attempted = 0
            reconciled_count = 0
            pending_count = 0
            bounded_references: list[dict[str, Any]] = []
            for plan in changed_plans:
                after = plan["after"]
                cursor.execute(
                    """UPDATE finance_import_rows
                       SET classification_type=%s,
                           classification_reason=%s,
                           matched_identity_ids=%s,
                           resolved_counterparty_account=%s,
                           classified_at=CURRENT_TIMESTAMP
                       WHERE id=%s
                         AND classification_type='non_business_review'
                         AND reconciliation_status='pending'""",
                    (
                        after["classification_type"],
                        after["classification_reason"],
                        _json(after["matched_identity_ids"]),
                        after["resolved_counterparty_account"],
                        plan["row_id"],
                    ),
                )
                if getattr(cursor, "rowcount", 1) != 1:
                    raise RuntimeError("eligible row changed while reprocessing")

                dispatch = {
                    "result": "not_dispatched",
                    "reason": after["classification_reason"],
                    "formal_references": {},
                }
                if after["classification_type"] != "non_business_review":
                    dispatch_attempted += 1
                    dispatch = dispatch_finance_import_row(
                        cursor,
                        plan["row_id"],
                        batch_id,
                    )
                    if dispatch["result"] in {"reconciled", "existing"}:
                        reconciled_count += 1
                    else:
                        pending_count += 1
                    if dispatch.get("formal_references") and len(bounded_references) < 20:
                        bounded_references.append(
                            {
                                "finance_import_row_id": plan["row_id"],
                                "references": dispatch["formal_references"],
                            }
                        )
                events.append(
                    {
                        **plan,
                        "dispatch_result": dispatch["result"],
                        "dispatch_reason": dispatch.get("reason"),
                        "dispatch_references": dispatch.get(
                            "formal_references",
                            {},
                        ),
                    }
                )

            classification_summary = {
                "selected": len(plans),
                "changed": len(changed_plans),
                "unchanged": len(plans) - len(changed_plans),
                "before_reason_counts": _reason_counts(plans, "before"),
                "after_reason_counts": _reason_counts(plans, "after"),
            }
            dispatch_summary = {
                "attempted": dispatch_attempted,
                "reconciled": reconciled_count,
                "pending": pending_count,
                "bounded_references": bounded_references,
            }
            batch_manifest = {
                "batch_id": batch_id,
                "format_id": batch.get("format_id"),
                "source_file": batch.get("source_file"),
                "sheet_name": batch.get("sheet_name"),
                "header_row": batch.get("header_row"),
                "declared_row_count": batch.get("row_count"),
                "selected_distinct_count": len(plans),
            }
            elapsed = max(clock.monotonic() - started, 0.0)
            result_summary = {
                "batch_manifest": batch_manifest,
                "classification_summary": classification_summary,
                "dispatch_summary": dispatch_summary,
                "elapsed_seconds": elapsed,
                "rows_per_second": (
                    len(plans) / elapsed if elapsed > 0 else 0.0
                ),
            }
            cursor.execute(
                """INSERT INTO finance_import_reprocess_runs
                       (batch_id, batch_status, actor, classifier_version,
                        plan_fingerprint, selected_count, changed_count,
                        dispatch_count, reconciled_count, pending_count,
                        request_summary, result_summary, status)
                   VALUES (%s, 'completed', %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, 'completed')""",
                (
                    batch_id,
                    effective_actor,
                    CLASSIFIER_VERSION,
                    plan_fingerprint,
                    len(plans),
                    len(changed_plans),
                    dispatch_attempted,
                    reconciled_count,
                    pending_count,
                    _json(
                        {
                            "batch_id": batch_id,
                            "dry_run": dry_run,
                            "safety_limit": safety_limit,
                        }
                    ),
                    _json(result_summary),
                ),
            )
            run_id = _positive_id(cursor.lastrowid, "reprocess_run_id")
            for event in events:
                before = event["before"]
                after = event["after"]
                cursor.execute(
                    """INSERT INTO finance_import_reclassification_events
                           (run_id, finance_import_row_id, actor,
                            before_classification_type,
                            before_classification_reason,
                            before_matched_identity_ids,
                            before_resolved_counterparty_account,
                            after_classification_type,
                            after_classification_reason,
                            after_matched_identity_ids,
                            after_resolved_counterparty_account,
                            dispatch_result, dispatch_reason,
                            dispatch_references)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                               %s, %s, %s, %s)""",
                    (
                        run_id,
                        event["row_id"],
                        effective_actor,
                        before["classification_type"],
                        before["classification_reason"],
                        _json(before["matched_identity_ids"]),
                        before["resolved_counterparty_account"],
                        after["classification_type"],
                        after["classification_reason"],
                        _json(after["matched_identity_ids"]),
                        after["resolved_counterparty_account"],
                        event["dispatch_result"],
                        event["dispatch_reason"],
                        _json(event["dispatch_references"]),
                    ),
                )

            alert_projection = project_finance_import_review_alert(
                cursor,
                batch_id,
            )
            result = {
                "db_identity": identity,
                **result_summary,
                "alert_action": alert_projection,
                "plan_fingerprint": plan_fingerprint,
                "transaction_outcome": "rolled_back" if dry_run else "committed",
                "run_id": None if dry_run else run_id,
            }
        if dry_run:
            connection.rollback()
        else:
            connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
