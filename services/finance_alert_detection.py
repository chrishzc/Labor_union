from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


def _required_text(value: Any, field: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _money(value: Any, field: str, *, allow_negative: bool = False) -> Decimal | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not amount.is_finite():
        raise ValueError(f"{field} must be a finite decimal")
    if not allow_negative and amount < 0:
        raise ValueError(f"{field} must not be negative")
    return amount


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("JSON Decimal values must be finite")
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="microseconds")
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(f"unsupported JSON value: {type(value).__name__}")


def _json_text(value: Any, field: str) -> str:
    try:
        normalized = _json_value(value)
        return json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be valid JSON data") from exc


def _stored_json_text(value: Any, field: str) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"stored {field} is invalid JSON") from exc
    return _json_text(value, field)


def _identity_key(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    key = f"{prefix}:{hashlib.sha256(payload).hexdigest()}"
    assert len(key) <= 191, "generated identity must fit the schema key"
    return key


def _datetime_value(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field} must be a datetime")
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _same_datetime(left: Any, right: datetime) -> bool:
    if not isinstance(left, datetime):
        return False
    if left.tzinfo is not None:
        left = left.astimezone(timezone.utc).replace(tzinfo=None)
    return left == right


def _require_transaction(cursor: Any) -> None:
    connection = getattr(cursor, "connection", None)
    get_autocommit = getattr(connection, "get_autocommit", None)
    if not callable(get_autocommit):
        raise RuntimeError("cursor must expose its transaction connection")
    if get_autocommit():
        raise RuntimeError("finance alert detection requires autocommit disabled")


def _validate_import_reference(
    cursor: Any,
    finance_import_row_id: int | None,
    finance_import_batch_id: int | None,
) -> None:
    if finance_import_row_id is not None:
        row_id = int(finance_import_row_id)
        if row_id <= 0:
            raise ValueError("finance_import_row_id must be positive")
        if finance_import_batch_id is None:
            cursor.execute(
                "SELECT id FROM finance_import_rows WHERE id=%s",
                (row_id,),
            )
        else:
            batch_id = int(finance_import_batch_id)
            if batch_id <= 0:
                raise ValueError("finance_import_batch_id must be positive")
            cursor.execute(
                """SELECT r.id
                   FROM finance_import_rows r
                   LEFT JOIN finance_import_occurrences o
                     ON o.finance_import_row_id=r.id AND o.batch_id=%s
                   WHERE r.id=%s AND (r.batch_id=%s OR o.id IS NOT NULL)
                   LIMIT 1""",
                (batch_id, row_id, batch_id),
            )
        if cursor.fetchone() is None:
            raise ValueError("finance import row/batch relation does not exist")
        return

    if finance_import_batch_id is not None:
        batch_id = int(finance_import_batch_id)
        if batch_id <= 0:
            raise ValueError("finance_import_batch_id must be positive")
        cursor.execute(
            "SELECT id FROM finance_import_batches WHERE id=%s",
            (batch_id,),
        )
        if cursor.fetchone() is None:
            raise ValueError("finance_import_batch_id does not exist")


def _alert_immutable_values(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("alert_code"),
        row.get("source_domain"),
        row.get("source_type"),
        str(row.get("source_id")),
        row.get("finance_import_row_id"),
        row.get("finance_import_batch_id"),
        row.get("reason"),
        _money(row.get("expected_amount"), "stored expected_amount"),
        _money(row.get("actual_amount"), "stored actual_amount"),
        _money(
            row.get("difference_amount"),
            "stored difference_amount",
            allow_negative=True,
        ),
        _stored_json_text(row.get("candidate_snapshot"), "candidate_snapshot"),
    )


def _select_alert(cursor: Any, alert_key: str) -> Mapping[str, Any] | None:
    cursor.execute(
        """SELECT id, alert_key, alert_code, source_domain, source_type, source_id,
                  finance_import_row_id, finance_import_batch_id, reason,
                  expected_amount, actual_amount, difference_amount,
                  candidate_snapshot, status, claimed_by, claimed_at,
                  resolved_by, resolved_at, resolution_reason, created_at, updated_at
           FROM finance_alerts
           WHERE alert_key=%s
           FOR UPDATE""",
        (alert_key,),
    )
    return cursor.fetchone()


def _select_event(cursor: Any, event_key: str) -> Mapping[str, Any] | None:
    cursor.execute(
        """SELECT id, alert_id, event_key, event_type, source_domain, source_type,
                  source_id, actor, reason, event_snapshot, occurred_at, created_at
           FROM finance_alert_events
           WHERE event_key=%s""",
        (event_key,),
    )
    return cursor.fetchone()


def create_or_get_finance_alert(
    cursor: Any,
    *,
    alert_code: str,
    source_domain: str,
    source_type: str,
    source_id: str,
    reason: str,
    candidate_snapshot: Any,
    finance_import_row_id: int | None = None,
    finance_import_batch_id: int | None = None,
    expected_amount: Any = None,
    actual_amount: Any = None,
    difference_amount: Any = None,
    detected_at: datetime,
) -> dict[str, Any]:
    """Create an alert and detected event inside the caller's open transaction."""
    _require_transaction(cursor)
    alert_code = _required_text(alert_code, "alert_code")
    source_domain = _required_text(source_domain, "source_domain")
    source_type = _required_text(source_type, "source_type")
    source_id = _required_text(source_id, "source_id")
    reason = _required_text(reason, "reason")
    expected = _money(expected_amount, "expected_amount")
    actual = _money(actual_amount, "actual_amount")
    difference = _money(
        difference_amount,
        "difference_amount",
        allow_negative=True,
    )
    snapshot_text = _json_text(candidate_snapshot, "candidate_snapshot")
    occurred_at = _datetime_value(detected_at, "detected_at")
    row_id = int(finance_import_row_id) if finance_import_row_id is not None else None
    batch_id = (
        int(finance_import_batch_id)
        if finance_import_batch_id is not None
        else None
    )
    _validate_import_reference(cursor, row_id, batch_id)

    canonical_identity = (
        ("finance_import_row", str(row_id))
        if row_id is not None
        else (source_domain, source_type, source_id)
    )
    alert_key = _identity_key("finance-alert", alert_code, *canonical_identity)
    detected_event_key = _identity_key("finance-alert-detected", alert_key)
    immutable = (
        alert_code,
        source_domain,
        source_type,
        source_id,
        row_id,
        batch_id,
        reason,
        expected,
        actual,
        difference,
        snapshot_text,
    )

    alert = _select_alert(cursor, alert_key)
    if alert is not None:
        if _alert_immutable_values(alert) != immutable:
            raise ValueError("alert_key conflicts with immutable detection data")
        event = _select_event(cursor, detected_event_key)
        if event is None:
            raise RuntimeError("existing alert is missing its detected event")
        expected_event_snapshot = _json_text(
            {
                "alert_code": alert_code,
                "candidate_snapshot": json.loads(snapshot_text),
                "finance_import_batch_id": batch_id,
                "finance_import_row_id": row_id,
            },
            "detected event snapshot",
        )
        event_values = (
            event.get("alert_id"),
            event.get("event_type"),
            event.get("source_domain"),
            event.get("source_type"),
            str(event.get("source_id")),
            event.get("actor"),
            event.get("reason"),
            _stored_json_text(event.get("event_snapshot"), "event_snapshot"),
            event.get("occurred_at"),
        )
        expected_values = (
            alert.get("id"),
            "detected",
            source_domain,
            source_type,
            source_id,
            None,
            reason,
            expected_event_snapshot,
            occurred_at,
        )
        if (
            event_values[:-1] != expected_values[:-1]
            or not _same_datetime(event_values[-1], expected_values[-1])
        ):
            raise ValueError("detected event conflicts with immutable detection data")
        return {"result": "existing", "alert": dict(alert)}

    cursor.execute("SAVEPOINT finance_alert_detection")
    try:
        cursor.execute(
            """INSERT INTO finance_alerts (
                   alert_key, alert_code, source_domain, source_type, source_id,
                   finance_import_row_id, finance_import_batch_id, reason,
                   expected_amount, actual_amount, difference_amount,
                   candidate_snapshot
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                alert_key,
                alert_code,
                source_domain,
                source_type,
                source_id,
                row_id,
                batch_id,
                reason,
                expected,
                actual,
                difference,
                snapshot_text,
            ),
        )
        alert_id = int(cursor.lastrowid)
        detected_snapshot = _json_text(
            {
                "alert_code": alert_code,
                "candidate_snapshot": json.loads(snapshot_text),
                "finance_import_batch_id": batch_id,
                "finance_import_row_id": row_id,
            },
            "detected event snapshot",
        )
        cursor.execute(
            """INSERT INTO finance_alert_events (
                   alert_id, event_key, event_type, source_domain, source_type,
                   source_id, actor, reason, event_snapshot, occurred_at
               ) VALUES (%s, %s, 'detected', %s, %s, %s, NULL, %s, %s, %s)""",
            (
                alert_id,
                detected_event_key,
                source_domain,
                source_type,
                source_id,
                reason,
                detected_snapshot,
                occurred_at,
            ),
        )
        alert = _select_alert(cursor, alert_key)
        if alert is None:
            raise RuntimeError("created finance alert could not be reloaded")
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT finance_alert_detection")
        cursor.execute("RELEASE SAVEPOINT finance_alert_detection")
        raise
    cursor.execute("RELEASE SAVEPOINT finance_alert_detection")
    return {"result": "created", "alert": dict(alert)}
