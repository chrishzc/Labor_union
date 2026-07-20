from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

import pymysql


_WORKFLOW_EVENT_TYPES = frozenset({"claimed", "resolved"})
_FORMAL_EVENT_TYPES = frozenset(
    {"failed", "returned", "retransferred", "reversed"}
)
_SOURCE_TABLES = {
    "client_payment_transaction": "client_payment_transactions",
    "staff_payment_transaction": "staff_payment_transactions",
    "staff_actual_transfer": "staff_actual_transfers",
    "government_subsidy_transaction": "government_subsidy_transactions",
}
_RETRANSFER_TYPES = frozenset({"receipt", "transfer"})
_RETURN_TYPES = frozenset({"refund", "return"})


def _required_text(value: Any, field: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _positive_id(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive integer")
    if isinstance(value, int):
        identifier = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        identifier = int(value.strip())
    else:
        raise ValueError(f"{field} must be a positive integer")
    if identifier <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return identifier


def _datetime_value(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field} must be a datetime")
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("JSON Decimal values must be finite")
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, datetime):
        return _datetime_value(value, "JSON datetime").isoformat(
            timespec="microseconds"
        )
    if isinstance(value, date):
        return value.isoformat()
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
        return json.dumps(
            _json_value(value),
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
        raise RuntimeError("finance alert events require autocommit disabled")


def _select_alert(cursor: Any, alert_id: int) -> Mapping[str, Any] | None:
    cursor.execute(
        """SELECT id, status, claimed_by, claimed_at, resolved_by, resolved_at,
                  resolution_reason
           FROM finance_alerts
           WHERE id=%s
           FOR UPDATE""",
        (alert_id,),
    )
    return cursor.fetchone()


def _select_event(cursor: Any, event_key: str) -> Mapping[str, Any] | None:
    cursor.execute(
        """SELECT id, alert_id, event_key, event_type, source_domain, source_type,
                  source_id, actor, reason, event_snapshot, occurred_at, created_at
           FROM finance_alert_events
           WHERE event_key=%s
           FOR UPDATE""",
        (event_key,),
    )
    return cursor.fetchone()


def _select_formal_source(
    cursor: Any,
    source_type: str,
    source_id: int,
) -> Mapping[str, Any] | None:
    table = _SOURCE_TABLES.get(source_type)
    if table is None:
        raise ValueError("source_type is not an allowed formal transaction source")
    assert table in _SOURCE_TABLES.values(), "formal source table must be fixed"
    cursor.execute(
        f"""SELECT id, transaction_type, transaction_status, external_reference
            FROM {table}
            WHERE id=%s
            FOR UPDATE""",
        (source_id,),
    )
    return cursor.fetchone()


def _validate_workflow_source(
    *,
    alert: Mapping[str, Any],
    alert_id: int,
    event_type: str,
    source_domain: str,
    source_type: str,
    source_id: str,
    actor: str | None,
    reason: str | None,
) -> None:
    if source_domain != "finance_alert" or source_type != "finance_alert":
        raise ValueError("workflow events must use the finance_alert source")
    if source_id != str(alert_id):
        raise ValueError("workflow source_id must equal alert_id")
    if actor is None:
        raise ValueError(f"{event_type} event requires actor")
    if event_type == "resolved" and reason is None:
        raise ValueError("resolved event requires reason")
    if event_type == "claimed":
        if alert.get("status") not in {"claimed", "resolved"}:
            raise ValueError("claimed event requires a claimed alert projection")
        if alert.get("claimed_by") != actor or alert.get("claimed_at") is None:
            raise ValueError("claimed event actor does not match alert projection")
    else:
        if alert.get("status") != "resolved":
            raise ValueError("resolved event requires a resolved alert projection")
        if alert.get("resolved_by") != actor or alert.get("resolved_at") is None:
            raise ValueError("resolved event actor does not match alert projection")
        if alert.get("resolution_reason") != reason:
            raise ValueError("resolved event reason does not match alert projection")


def _validate_formal_source(
    cursor: Any,
    *,
    event_type: str,
    source_type: str,
    source_id: int,
    original_source_id: int | None,
) -> None:
    source = _select_formal_source(cursor, source_type, source_id)
    if source is None:
        raise ValueError("formal source transaction does not exist")
    transaction_type = source.get("transaction_type")
    status = source.get("transaction_status")

    if event_type == "failed":
        if status != "failed":
            raise ValueError("failed event requires transaction_status=failed")
        return
    if event_type == "returned":
        if transaction_type not in _RETURN_TYPES or status != "succeeded":
            raise ValueError("returned event requires a succeeded return or refund")
        return
    if event_type == "reversed":
        if transaction_type != "reversal" and status != "reversed":
            raise ValueError(
                "reversed event requires a reversal row or reversed status"
            )
        return

    if original_source_id is None:
        raise ValueError("retransferred event requires original_source_id")
    if original_source_id == source_id:
        raise ValueError("retransferred source and original must differ")
    original = _select_formal_source(cursor, source_type, original_source_id)
    if original is None:
        raise ValueError("original formal transaction does not exist")
    new_reference = str(source.get("external_reference") or "").strip()
    old_reference = str(original.get("external_reference") or "").strip()
    if (
        status != "succeeded"
        or transaction_type not in _RETRANSFER_TYPES
        or not new_reference
        or not old_reference
        or new_reference == old_reference
    ):
        raise ValueError(
            "retransferred event requires a new succeeded transfer or receipt"
        )


def _event_matches(
    event: Mapping[str, Any],
    *,
    alert_id: int,
    event_key: str,
    event_type: str,
    source_domain: str,
    source_type: str,
    source_id: str,
    actor: str | None,
    reason: str | None,
    snapshot_text: str,
    occurred_at: datetime,
) -> bool:
    stored = (
        event.get("alert_id"),
        event.get("event_key"),
        event.get("event_type"),
        event.get("source_domain"),
        event.get("source_type"),
        str(event.get("source_id")),
        event.get("actor"),
        event.get("reason"),
        _stored_json_text(event.get("event_snapshot"), "event_snapshot"),
    )
    expected = (
        alert_id,
        event_key,
        event_type,
        source_domain,
        source_type,
        source_id,
        actor,
        reason,
        snapshot_text,
    )
    return stored == expected and _same_datetime(
        event.get("occurred_at"),
        occurred_at,
    )


def append_finance_alert_event(
    cursor: Any,
    *,
    alert_id: int,
    event_key: str,
    event_type: str,
    source_domain: str,
    source_type: str,
    source_id: Any,
    event_snapshot: Any,
    occurred_at: datetime,
    actor: str | None = None,
    reason: str | None = None,
    original_source_id: Any = None,
) -> dict[str, Any]:
    """Append one immutable event inside the caller's open transaction."""
    _require_transaction(cursor)
    alert_id = _positive_id(alert_id, "alert_id")
    event_key = _required_text(event_key, "event_key")
    if len(event_key) > 191:
        raise ValueError("event_key exceeds schema length")
    event_type = _required_text(event_type, "event_type")
    if event_type not in _WORKFLOW_EVENT_TYPES | _FORMAL_EVENT_TYPES:
        raise ValueError("unsupported finance alert event_type")
    source_domain = _required_text(source_domain, "source_domain")
    source_type = _required_text(source_type, "source_type")
    source_id_text = _required_text(source_id, "source_id")
    actor = _required_text(actor, "actor") if actor is not None else None
    reason = _required_text(reason, "reason") if reason is not None else None
    occurred_at = _datetime_value(occurred_at, "occurred_at")

    alert = _select_alert(cursor, alert_id)
    if alert is None:
        raise ValueError("alert_id does not exist")

    if event_type in _WORKFLOW_EVENT_TYPES:
        if original_source_id is not None:
            raise ValueError("workflow events do not accept original_source_id")
        _validate_workflow_source(
            alert=alert,
            alert_id=alert_id,
            event_type=event_type,
            source_domain=source_domain,
            source_type=source_type,
            source_id=source_id_text,
            actor=actor,
            reason=reason,
        )
    else:
        source_id_int = _positive_id(source_id, "source_id")
        source_id_text = str(source_id_int)
        if event_type != "retransferred" and original_source_id is not None:
            raise ValueError(
                "original_source_id is only valid for retransferred events"
            )
        original_id = (
            _positive_id(original_source_id, "original_source_id")
            if original_source_id is not None
            else None
        )
        _validate_formal_source(
            cursor,
            event_type=event_type,
            source_type=source_type,
            source_id=source_id_int,
            original_source_id=original_id,
        )
        if event_type == "retransferred":
            if not isinstance(event_snapshot, Mapping):
                raise ValueError(
                    "retransferred event_snapshot must be a JSON object"
                )
            supplied_original = event_snapshot.get("original_source_id")
            if (
                supplied_original is not None
                and _positive_id(
                    supplied_original,
                    "event_snapshot.original_source_id",
                )
                != original_id
            ):
                raise ValueError(
                    "event_snapshot original_source_id conflicts with input"
                )
            event_snapshot = dict(event_snapshot)
            event_snapshot["original_source_id"] = original_id

    snapshot_text = _json_text(event_snapshot, "event_snapshot")

    existing = _select_event(cursor, event_key)
    if existing is not None:
        if not _event_matches(
            existing,
            alert_id=alert_id,
            event_key=event_key,
            event_type=event_type,
            source_domain=source_domain,
            source_type=source_type,
            source_id=source_id_text,
            actor=actor,
            reason=reason,
            snapshot_text=snapshot_text,
            occurred_at=occurred_at,
        ):
            raise ValueError("event_key conflicts with immutable event data")
        return {"result": "existing", "event": dict(existing)}

    cursor.execute("SAVEPOINT finance_alert_event_append")
    try:
        cursor.execute(
            """INSERT INTO finance_alert_events (
                   alert_id, event_key, event_type, source_domain, source_type,
                   source_id, actor, reason, event_snapshot, occurred_at
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                alert_id,
                event_key,
                event_type,
                source_domain,
                source_type,
                source_id_text,
                actor,
                reason,
                snapshot_text,
                occurred_at,
            ),
        )
        created = _select_event(cursor, event_key)
        if created is None:
            raise RuntimeError("created finance alert event could not be reloaded")
    except pymysql.err.IntegrityError:
        cursor.execute("ROLLBACK TO SAVEPOINT finance_alert_event_append")
        concurrent = _select_event(cursor, event_key)
        cursor.execute("RELEASE SAVEPOINT finance_alert_event_append")
        if concurrent is None or not _event_matches(
            concurrent,
            alert_id=alert_id,
            event_key=event_key,
            event_type=event_type,
            source_domain=source_domain,
            source_type=source_type,
            source_id=source_id_text,
            actor=actor,
            reason=reason,
            snapshot_text=snapshot_text,
            occurred_at=occurred_at,
        ):
            raise ValueError("event_key conflicts with immutable event data")
        return {"result": "existing", "event": dict(concurrent)}
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT finance_alert_event_append")
        cursor.execute("RELEASE SAVEPOINT finance_alert_event_append")
        raise
    cursor.execute("RELEASE SAVEPOINT finance_alert_event_append")
    return {"result": "created", "event": dict(created)}
