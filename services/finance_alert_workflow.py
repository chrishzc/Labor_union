from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping

from services.finance_alert_events import append_finance_alert_event


_ALERT_COLUMNS = """id, alert_key, alert_code, source_domain, source_type,
source_id, finance_import_row_id, finance_import_batch_id, reason,
expected_amount, actual_amount, difference_amount, candidate_snapshot, status,
claimed_by, claimed_at, resolved_by, resolved_at, resolution_reason,
created_at, updated_at"""
_STATUSES = frozenset({"open", "claimed", "resolved"})


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


def _page_value(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{field} is outside the allowed range")
    return value


def _datetime_value(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field} must be a datetime")
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _require_transaction(cursor: Any) -> None:
    connection = getattr(cursor, "connection", None)
    get_autocommit = getattr(connection, "get_autocommit", None)
    if not callable(get_autocommit):
        raise RuntimeError("cursor must expose its transaction connection")
    if get_autocommit():
        raise RuntimeError("finance alert workflow requires autocommit disabled")


def _workflow_event_key(alert_id: int, event_type: str) -> str:
    key = f"finance-alert:{alert_id}:{event_type}"
    assert len(key) <= 191, "workflow event key must fit the schema"
    return key


def _select_alert(
    cursor: Any,
    alert_id: int,
    *,
    lock: bool,
) -> Mapping[str, Any] | None:
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        f"SELECT {_ALERT_COLUMNS} FROM finance_alerts WHERE id=%s{suffix}",
        (alert_id,),
    )
    return cursor.fetchone()


def _select_workflow_event(cursor: Any, event_key: str) -> Mapping[str, Any] | None:
    cursor.execute(
        """SELECT id, alert_id, event_key, event_type, source_domain, source_type,
                  source_id, actor, reason, event_snapshot, occurred_at, created_at
           FROM finance_alert_events
           WHERE event_key=%s
           FOR UPDATE""",
        (event_key,),
    )
    return cursor.fetchone()


def _reload_alert(cursor: Any, alert_id: int) -> dict[str, Any]:
    alert = _select_alert(cursor, alert_id, lock=False)
    if alert is None:
        raise RuntimeError("updated finance alert could not be reloaded")
    return dict(alert)


def list_finance_alerts(
    cursor: Any,
    *,
    status: str | None = None,
    alert_code: str | None = None,
    source_domain: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    limit = _page_value(limit, "limit", minimum=1, maximum=200)
    offset = _page_value(offset, "offset", minimum=0, maximum=1_000_000)
    clauses: list[str] = []
    params: list[Any] = []
    if status is not None:
        status = _required_text(status, "status")
        if status not in _STATUSES:
            raise ValueError("invalid finance alert status")
        clauses.append("status=%s")
        params.append(status)
    if alert_code is not None:
        clauses.append("alert_code=%s")
        params.append(_required_text(alert_code, "alert_code"))
    if source_domain is not None:
        clauses.append("source_domain=%s")
        params.append(_required_text(source_domain, "source_domain"))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor.execute(
        f"""SELECT {_ALERT_COLUMNS}
            FROM finance_alerts{where}
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s""",
        tuple(params + [limit, offset]),
    )
    return [dict(row) for row in cursor.fetchall()]


def get_finance_alert(
    cursor: Any,
    alert_id: Any,
) -> dict[str, Any] | None:
    alert_id = _positive_id(alert_id, "alert_id")
    alert = _select_alert(cursor, alert_id, lock=False)
    if alert is None:
        return None
    cursor.execute(
        """SELECT id, alert_id, event_key, event_type, source_domain, source_type,
                  source_id, actor, reason, event_snapshot, occurred_at, created_at
           FROM finance_alert_events
           WHERE alert_id=%s
           ORDER BY occurred_at, id""",
        (alert_id,),
    )
    result = dict(alert)
    result["events"] = [dict(row) for row in cursor.fetchall()]
    return result


def claim_finance_alert(
    cursor: Any,
    *,
    alert_id: Any,
    operator: Any,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    _require_transaction(cursor)
    alert_id = _positive_id(alert_id, "alert_id")
    operator = _required_text(operator, "operator")
    supplied_at = (
        _datetime_value(occurred_at, "occurred_at")
        if occurred_at is not None
        else None
    )
    alert = _select_alert(cursor, alert_id, lock=True)
    if alert is None:
        raise ValueError("alert_id does not exist")
    status = alert.get("status")
    event_key = _workflow_event_key(alert_id, "claimed")

    if status == "resolved":
        return {"result": "conflict", "alert": dict(alert)}
    if status == "claimed":
        if alert.get("claimed_by") != operator:
            return {"result": "conflict", "alert": dict(alert)}
        existing_event = _select_workflow_event(cursor, event_key)
        if existing_event is None:
            raise RuntimeError("claimed alert is missing its claimed event")
        claim_time = alert.get("claimed_at")
        if not isinstance(claim_time, datetime):
            raise RuntimeError("claimed alert has invalid claimed_at")
        append_finance_alert_event(
            cursor,
            alert_id=alert_id,
            event_key=event_key,
            event_type="claimed",
            source_domain="finance_alert",
            source_type="finance_alert",
            source_id=str(alert_id),
            actor=operator,
            event_snapshot={"claimed_by": operator, "status": "claimed"},
            occurred_at=claim_time,
        )
        return {"result": "existing", "alert": dict(alert)}
    if status != "open":
        raise RuntimeError("finance alert has an invalid workflow status")
    if _select_workflow_event(cursor, event_key) is not None:
        raise RuntimeError("open alert already has a claimed event")

    claim_time = supplied_at or datetime.now(timezone.utc).replace(tzinfo=None)
    cursor.execute("SAVEPOINT finance_alert_claim")
    try:
        cursor.execute(
            """UPDATE finance_alerts
               SET status='claimed', claimed_by=%s, claimed_at=%s
               WHERE id=%s AND status='open'""",
            (operator, claim_time, alert_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("finance alert claim update lost its row lock")
        append_finance_alert_event(
            cursor,
            alert_id=alert_id,
            event_key=event_key,
            event_type="claimed",
            source_domain="finance_alert",
            source_type="finance_alert",
            source_id=str(alert_id),
            actor=operator,
            event_snapshot={"claimed_by": operator, "status": "claimed"},
            occurred_at=claim_time,
        )
        updated = _reload_alert(cursor, alert_id)
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT finance_alert_claim")
        cursor.execute("RELEASE SAVEPOINT finance_alert_claim")
        raise
    cursor.execute("RELEASE SAVEPOINT finance_alert_claim")
    return {"result": "claimed", "alert": updated}


def resolve_finance_alert(
    cursor: Any,
    *,
    alert_id: Any,
    operator: Any,
    reason: Any,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    _require_transaction(cursor)
    alert_id = _positive_id(alert_id, "alert_id")
    operator = _required_text(operator, "operator")
    reason = _required_text(reason, "reason")
    supplied_at = (
        _datetime_value(occurred_at, "occurred_at")
        if occurred_at is not None
        else None
    )
    alert = _select_alert(cursor, alert_id, lock=True)
    if alert is None:
        raise ValueError("alert_id does not exist")
    status = alert.get("status")
    event_key = _workflow_event_key(alert_id, "resolved")

    if status == "resolved":
        if (
            alert.get("resolved_by") != operator
            or alert.get("resolution_reason") != reason
        ):
            return {"result": "conflict", "alert": dict(alert)}
        existing_event = _select_workflow_event(cursor, event_key)
        if existing_event is None:
            raise RuntimeError("resolved alert is missing its resolved event")
        resolved_at = alert.get("resolved_at")
        if not isinstance(resolved_at, datetime):
            raise RuntimeError("resolved alert has invalid resolved_at")
        append_finance_alert_event(
            cursor,
            alert_id=alert_id,
            event_key=event_key,
            event_type="resolved",
            source_domain="finance_alert",
            source_type="finance_alert",
            source_id=str(alert_id),
            actor=operator,
            reason=reason,
            event_snapshot={
                "resolution_reason": reason,
                "resolved_by": operator,
                "status": "resolved",
            },
            occurred_at=resolved_at,
        )
        return {"result": "existing", "alert": dict(alert)}
    if status == "claimed" and alert.get("claimed_by") != operator:
        return {"result": "conflict", "alert": dict(alert)}
    if status not in {"open", "claimed"}:
        raise RuntimeError("finance alert has an invalid workflow status")
    if _select_workflow_event(cursor, event_key) is not None:
        raise RuntimeError("unresolved alert already has a resolved event")

    resolved_at = supplied_at or datetime.now(timezone.utc).replace(tzinfo=None)
    cursor.execute("SAVEPOINT finance_alert_resolve")
    try:
        cursor.execute(
            """UPDATE finance_alerts
               SET status='resolved', resolved_by=%s, resolved_at=%s,
                   resolution_reason=%s
               WHERE id=%s AND status=%s""",
            (operator, resolved_at, reason, alert_id, status),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("finance alert resolve update lost its row lock")
        append_finance_alert_event(
            cursor,
            alert_id=alert_id,
            event_key=event_key,
            event_type="resolved",
            source_domain="finance_alert",
            source_type="finance_alert",
            source_id=str(alert_id),
            actor=operator,
            reason=reason,
            event_snapshot={
                "resolution_reason": reason,
                "resolved_by": operator,
                "status": "resolved",
            },
            occurred_at=resolved_at,
        )
        updated = _reload_alert(cursor, alert_id)
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT finance_alert_resolve")
        cursor.execute("RELEASE SAVEPOINT finance_alert_resolve")
        raise
    cursor.execute("RELEASE SAVEPOINT finance_alert_resolve")
    return {"result": "resolved", "alert": updated}
