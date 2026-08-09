"""Produce a bounded, rollback-only reclassification plan for old import batches.

The historical apply path is intentionally retired.  The remaining command is
strictly a diagnostic: it locks and reads the canonical rows, calculates the
current classification plan, and always rolls its database transaction back.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import json
import re
from time import monotonic
from typing import Any

from domains.finance_import.transaction_classifier import classify_finance_transaction
from infrastructure.mysql.mysql_adapter import get_connection
from scripts.imports.finance_normalized_row import validate_normalized_row
from subsystems.finance_import.identity_maps import load_finance_identity_maps


CLASSIFIER_VERSION = "finance_transaction_classifier:v1"
DEFAULT_SAFETY_LIMIT = 5000
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")


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
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, default=_json_default)


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
    if not isinstance(fingerprint, str) or _FINGERPRINT.fullmatch(fingerprint) is None:
        raise ValueError("canonical row fingerprint is invalid")
    normalized = {
        "format_id": row.get("format_id"), "source_file": row.get("source_file"),
        "source_bank_account": row.get("source_bank_account"), "sheet_name": row.get("sheet_name"),
        "source_row": row.get("source_row"), "source_reference": row.get("source_reference"),
        "transaction_date": _iso_date(row.get("transaction_date")),
        "transaction_time": _iso_time(row.get("transaction_time")),
        "posting_date": _iso_date(row.get("posting_date")), "value_date": _iso_date(row.get("value_date")),
        "debit": row.get("debit"), "credit": row.get("credit"), "direction": row.get("direction"),
        "balance": row.get("balance"), "currency": row.get("currency"), "summary": row.get("summary"),
        "memo": row.get("memo"), "counterparty_name": row.get("counterparty_name"),
        "counterparty_account": row.get("counterparty_account"), "cancellation_code": row.get("cancellation_code"),
        "bank_references": _strict_json(row.get("bank_references"), "bank_references", dict),
        "warnings": _strict_json(row.get("warnings"), "warnings", list),
        "raw_payload": _strict_json(row.get("raw_payload"), "raw_payload", dict),
    }
    return validate_normalized_row(normalized)


def _identity_ids(value: Any, field: str) -> list[int]:
    decoded = _strict_json(value, field, list)
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in decoded):
        raise ValueError(f"{field} must contain positive integer ids")
    return decoded


def _before_tuple(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"classification_type": row.get("classification_type"), "classification_reason": row.get("classification_reason"), "matched_identity_ids": _identity_ids(row.get("matched_identity_ids"), "matched_identity_ids"), "resolved_counterparty_account": row.get("resolved_counterparty_account")}


def _after_tuple(classification: Mapping[str, Any]) -> dict[str, Any]:
    identities = classification.get("matched_identity_ids")
    if not isinstance(identities, list):
        raise ValueError("classifier matched_identity_ids must be a list")
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in identities):
        raise ValueError("classifier matched_identity_ids are invalid")
    return {"classification_type": classification.get("classification_type"), "classification_reason": classification.get("reason"), "matched_identity_ids": identities, "resolved_counterparty_account": classification.get("resolved_counterparty_account")}


def _db_identity(cursor: Any) -> dict[str, str]:
    cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server_name")
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise TypeError("cursor must return a mapping DB identity")
    database = row.get("database_name")
    if not isinstance(database, str) or not database:
        raise RuntimeError("database identity is unavailable")
    return {"database": database, "server": str(row.get("server_name") or "")}


def _plan_fingerprint(db_identity: Mapping[str, str], batch_id: int, plans: list[dict[str, Any]]) -> str:
    payload = {"db_identity": dict(db_identity), "batch_id": batch_id, "classifier_version": CLASSIFIER_VERSION, "rows": [{"row_id": plan["row_id"], "before": plan["before"], "after": plan["after"]} for plan in plans]}
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _reason_counts(plans: list[dict[str, Any]], side: str) -> dict[str, int]:
    counts = Counter(str(plan[side].get("classification_reason") or "none") for plan in plans)
    return {key: counts[key] for key in sorted(counts)}


def _formal_transaction_exists(cursor: Any, row_id: int) -> bool:
    cursor.execute("""SELECT EXISTS(SELECT 1 FROM client_payment_transactions WHERE finance_import_row_id=%s) AS client_tx,
                      EXISTS(SELECT 1 FROM government_subsidy_transactions WHERE finance_import_row_id=%s) AS government_tx,
                      EXISTS(SELECT 1 FROM staff_actual_transfers WHERE raw_import_reference=%s) AS staff_tx""", (row_id, row_id, f"finance_import_row:{row_id}"))
    result = cursor.fetchone()
    if not isinstance(result, Mapping):
        raise TypeError("cursor must return a mapping transaction check")
    return any(bool(result.get(key)) for key in ("client_tx", "government_tx", "staff_tx"))


def _preview_dispatch(after: Mapping[str, Any]) -> dict[str, Any]:
    """Report the retired dispatch boundary without invoking any writer."""
    if after["classification_type"] == "non_business_review":
        return {"result": "not_dispatched", "reason": after["classification_reason"], "formal_references": {}}
    return {"result": "pending", "reason": "reprocessing_apply_requires_formal_workflow", "formal_references": {}}


def _fetch_candidate_rows(cursor: Any, batch_id: int, safety_limit: int) -> list[Mapping[str, Any]]:
    cursor.execute("""SELECT DISTINCT fir.id AS finance_import_row_id FROM finance_import_occurrences occurrence
                      JOIN finance_import_rows fir ON fir.id=occurrence.finance_import_row_id
                      WHERE occurrence.batch_id=%s AND fir.classification_type='non_business_review'
                        AND fir.reconciliation_status='pending' ORDER BY fir.id""", (batch_id,))
    candidates = list(cursor.fetchall())
    if any(not isinstance(row, Mapping) for row in candidates):
        raise TypeError("cursor must return mapping candidate rows")
    candidate_ids = [_positive_id(row.get("finance_import_row_id"), "finance_import_row_id") for row in candidates]
    if len(candidate_ids) > safety_limit:
        raise ValueError("eligible rows exceed safety_limit")
    if not candidate_ids:
        return []
    placeholders = ", ".join(["%s"] * len(candidate_ids))
    cursor.execute(f"""SELECT fir.* FROM finance_import_rows fir WHERE fir.id IN ({placeholders})
                       AND fir.classification_type='non_business_review' AND fir.reconciliation_status='pending'
                       ORDER BY fir.id FOR UPDATE""", tuple(candidate_ids))
    rows = list(cursor.fetchall())
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError("cursor must return mapping canonical rows")
    locked_ids = [_positive_id(row.get("id"), "finance_import_row_id") for row in rows]
    if locked_ids != candidate_ids:
        raise RuntimeError("eligible rows changed before lock acquisition")
    return rows


def reprocess_finance_import_batch(batch_id: int, actor: str | None = None, dry_run: bool = True, expected_plan_fingerprint: str | None = None, safety_limit: int = DEFAULT_SAFETY_LIMIT) -> dict[str, Any]:
    """Create the legacy reprocess dry-run report; applying is permanently retired."""
    if not callable(get_connection):
        raise AssertionError("database connection factory is required")
    batch_id = _positive_id(batch_id, "batch_id")
    if not isinstance(dry_run, bool):
        raise TypeError("dry_run must be a boolean")
    if isinstance(safety_limit, bool) or not isinstance(safety_limit, int) or safety_limit < 1:
        raise ValueError("safety_limit must be a positive integer")
    if not dry_run:
        raise ValueError("legacy_finance_import_reprocess_apply_retired")
    started = monotonic()
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            identity = _db_identity(cursor)
            cursor.execute("""SELECT id, format_id, source_file, sheet_name, header_row, row_count, status, created_at, completed_at
                              FROM finance_import_batches WHERE id=%s AND status='completed' FOR UPDATE""", (batch_id,))
            batch = cursor.fetchone()
            if not isinstance(batch, Mapping):
                raise ValueError("completed finance import batch was not found")
            rows = _fetch_candidate_rows(cursor, batch_id, safety_limit)
            identity_maps = load_finance_identity_maps(cursor)
            plans: list[dict[str, Any]] = []
            for row in rows:
                row_id = _positive_id(row.get("id"), "finance_import_row_id")
                if _formal_transaction_exists(cursor, row_id):
                    raise RuntimeError("eligible non_business_review row already has a formal transaction")
                after = _after_tuple(classify_finance_transaction(_normalized_row(row), identity_maps["client_refund_accounts"], identity_maps["staff_accounts"], identity_maps.get("client_subsidy_return_accounts", {}), identity_maps.get("client_receipt_candidates", ())))
                plans.append({"row_id": row_id, "before": _before_tuple(row), "after": after})
            plan_fingerprint = _plan_fingerprint(identity, batch_id, plans)
            if expected_plan_fingerprint is not None and plan_fingerprint != expected_plan_fingerprint:
                raise RuntimeError("finance import reprocess plan is stale")
            changed = [plan for plan in plans if plan["before"] != plan["after"]]
            events = [{**plan, **{"dispatch_result": _preview_dispatch(plan["after"])["result"], "dispatch_reason": _preview_dispatch(plan["after"])["reason"], "dispatch_references": {}}} for plan in changed]
            dispatch_attempted = sum(event["after"]["classification_type"] != "non_business_review" for event in events)
            pending_count = dispatch_attempted
            elapsed = max(monotonic() - started, 0.0)
            result_summary = {"batch_manifest": {"batch_id": batch_id, "format_id": batch.get("format_id"), "source_file": batch.get("source_file"), "sheet_name": batch.get("sheet_name"), "header_row": batch.get("header_row"), "declared_row_count": batch.get("row_count"), "selected_distinct_count": len(plans)}, "classification_summary": {"selected": len(plans), "changed": len(changed), "unchanged": len(plans) - len(changed), "before_reason_counts": _reason_counts(plans, "before"), "after_reason_counts": _reason_counts(plans, "after")}, "dispatch_summary": {"attempted": dispatch_attempted, "reconciled": 0, "pending": pending_count, "bounded_references": []}, "elapsed_seconds": elapsed, "rows_per_second": len(plans) / elapsed if elapsed > 0 else 0.0}
            return {"db_identity": identity, **result_summary, "alert_action": {"alert_action": "not_projected", "summary": {"remaining_count": len(plans)}}, "plan_fingerprint": plan_fingerprint, "transaction_outcome": "rolled_back", "run_id": None}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.rollback()
        connection.close()


__all__ = ["DEFAULT_SAFETY_LIMIT", "reprocess_finance_import_batch"]
