"""Mutable "process reminder" alerts, stored in system_alerts.

Unlike finance_alerts (immutable event-sourced, for audit-sensitive money
matters), system_alerts is a simple rolling-update table: one row per
(alert_code, case_key), whose `details` JSON gets overwritten on every
rescan. There is no append-only event history here on purpose -- these are
staff reminders ("go fix this case"), not records that need to survive
tamper-proof for an audit.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

_STATUSES = frozenset({"open", "claimed", "resolved"})
_MAX_DETAILS_BYTES = 32_768
_MAX_DETAILS_DEPTH = 8
_MAX_DETAILS_ITEMS = 200
_MAX_LIST_LIMIT = 200
_MAX_LIST_OFFSET = 1_000_000
_SENSITIVE_DETAIL_KEYS = frozenset(
    {
        "account",
        "account_no",
        "account_number",
        "bank_account",
        "bank_account_no",
        "bank_account_number",
        "password",
        "raw_payload",
        "raw_row",
        "row_payload",
        "完整銀行帳號",
        "完整帳號",
        "密碼",
        "銀行帳號",
    }
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _decode_details(details: Any) -> dict[str, Any]:
    if isinstance(details, dict):
        return details
    if isinstance(details, str):
        try:
            decoded = json.loads(details)
        except json.JSONDecodeError as exc:
            raise ValueError("stored system alert details are invalid JSON") from exc
        if isinstance(decoded, dict):
            return decoded
    raise ValueError("stored system alert details must be an object")


def _decode_row(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row["details"] = _decode_details(row.get("details"))
    # UI 沿用 finance_alerts 慣用的 source_id 欄位名稱做顯示，這裡補一個別名。
    row.setdefault("source_id", row.get("case_key"))
    return row


def _required_text(value: Any, field: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    value = value.strip()
    if len(value) > max_length:
        raise ValueError(f"{field} exceeds maximum length")
    return value


def _normalize_detail_key(key: str) -> tuple[str, frozenset[str]]:
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key.strip())
    normalized = re.sub(r"[^\w]+", "_", snake, flags=re.UNICODE).strip("_").casefold()
    return normalized, frozenset(token for token in normalized.split("_") if token)


def _partial_account_reference_kind(
    normalized: str, tokens: frozenset[str]
) -> str | None:
    if (
        "last4" in tokens
        or {"last", "4"} <= tokens
        or "末四碼" in normalized
        or "尾四碼" in normalized
    ):
        return "last4"
    if (
        {"masked", "mask"} & tokens
        or "遮罩" in normalized
        or "掩碼" in normalized
    ):
        return "masked"
    return None


def _is_safe_partial_account_value(value: Any, kind: str) -> bool:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return False
    rendered = str(value).strip()
    if not rendered or len(rendered) > 32:
        return False
    mask_characters = "*•●#xX"
    contains_mask = any(character in rendered for character in mask_characters)
    if contains_mask:
        visible = re.sub(r"[^A-Za-z0-9]", "", rendered)
        visible = visible.replace("x", "").replace("X", "")
        return len(visible) <= 4
    return kind == "last4" and re.fullmatch(r"[A-Za-z0-9]{1,4}", rendered) is not None


def _is_sensitive_detail_key(key: str, value: Any) -> bool:
    normalized, tokens = _normalize_detail_key(key)
    compact = normalized.replace("_", "")
    if any("payload" in token for token in tokens):
        return True
    if {"raw", "row"} <= tokens or compact == "rawrow":
        return True
    is_account_reference = (
        normalized in _SENSITIVE_DETAIL_KEYS
        or "帳號" in normalized
        or (
            "account" in tokens
            and (
                len(tokens) == 1
                or "bank" in tokens
                or "number" in tokens
                or "no" in tokens
            )
        )
    )
    if not is_account_reference:
        return False
    partial_kind = _partial_account_reference_kind(normalized, tokens)
    if partial_kind is not None and _is_safe_partial_account_value(value, partial_kind):
        return False
    return True


def _validate_details_value(value: Any, *, depth: int = 0) -> None:
    if depth > _MAX_DETAILS_DEPTH:
        raise ValueError("system alert details exceed maximum depth")
    if isinstance(value, dict):
        if len(value) > _MAX_DETAILS_ITEMS:
            raise ValueError("system alert details contain too many items")
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError("system alert detail keys must be strings")
            if _is_sensitive_detail_key(key, nested):
                raise ValueError("system alert details contain forbidden sensitive data")
            _validate_details_value(nested, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_DETAILS_ITEMS:
            raise ValueError("system alert details contain too many items")
        for nested in value:
            _validate_details_value(nested, depth=depth + 1)
        return
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    raise ValueError("system alert details must be JSON serializable")


def _encode_details(details: dict[str, Any]) -> str:
    if not isinstance(details, dict):
        raise ValueError("system alert details must be an object")
    _validate_details_value(details)
    try:
        encoded = json.dumps(
            details,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("system alert details must be valid JSON") from exc
    if len(encoded.encode("utf-8")) > _MAX_DETAILS_BYTES:
        raise ValueError("system alert details exceed maximum size")
    return encoded


def _stored_details_equal(stored: Any, current_json: str) -> bool:
    """Compare legacy materialized JSON without re-validating old content."""
    try:
        decoded = _decode_details(stored)
        canonical = json.dumps(
            decoded,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return False
    return canonical == current_json


def upsert_system_alert(
    cursor: Any,
    *,
    alert_code: str,
    source_domain: str,
    case_key: str,
    reason: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    """Create or roll-update the alert for (alert_code, case_key).

    Reopens a previously-resolved row if the problem has recurred. Leaves a
    `claimed` row's status alone (a human is already on it) but still
    refreshes `details`/`reason` underneath so they see current data.
    """
    alert_code = _required_text(alert_code, "alert_code", 50)
    source_domain = _required_text(source_domain, "source_domain", 50)
    case_key = _required_text(case_key, "case_key", 100)
    reason = _required_text(reason, "reason", 500)
    details_json = _encode_details(details)
    cursor.execute(
        """SELECT id, source_domain, reason, details, status FROM system_alerts
           WHERE alert_code=%s AND case_key=%s
           FOR UPDATE""",
        (alert_code, case_key),
    )
    existing = cursor.fetchone()
    now = _now()
    if existing is None:
        cursor.execute(
            """INSERT INTO system_alerts
                   (alert_code, source_domain, case_key, reason, details, status)
               VALUES (%s, %s, %s, %s, %s, 'open')""",
            (alert_code, source_domain, case_key, reason, details_json),
        )
        alert_id = cursor.lastrowid
        result = "created"
    else:
        alert_id = existing["id"]
        if existing["status"] == "resolved":
            cursor.execute(
                """UPDATE system_alerts
                   SET source_domain=%s, reason=%s, details=%s, status='open',
                       claimed_by=NULL, claimed_at=NULL, resolved_by=NULL,
                       resolved_at=NULL, resolution_reason=NULL, updated_at=%s
                   WHERE id=%s""",
                (source_domain, reason, details_json, now, alert_id),
            )
            result = "reopened"
        elif (
            existing["source_domain"] == source_domain
            and existing["reason"] == reason
            and _stored_details_equal(existing["details"], details_json)
        ):
            result = "existing"
        else:
            cursor.execute(
                """UPDATE system_alerts
                   SET source_domain=%s, reason=%s, details=%s, updated_at=%s
                   WHERE id=%s""",
                (source_domain, reason, details_json, now, alert_id),
            )
            result = "updated"
    cursor.execute("SELECT * FROM system_alerts WHERE id=%s", (alert_id,))
    return {"result": result, "alert": _decode_row(cursor.fetchone())}


def resolve_absent_alerts(
    cursor: Any,
    *,
    alert_code: str,
    still_open_case_keys: set[str],
    reason: str,
    operator: str = "system",
) -> int:
    """Resolve open (not claimed) rows for alert_code whose case_key cleared up."""
    cursor.execute(
        "SELECT id, case_key FROM system_alerts WHERE alert_code=%s AND status='open'",
        (alert_code,),
    )
    resolved = 0
    now = _now()
    for row in cursor.fetchall():
        if row["case_key"] in still_open_case_keys:
            continue
        cursor.execute(
            """UPDATE system_alerts
               SET status='resolved', resolved_by=%s, resolved_at=%s, resolution_reason=%s
               WHERE id=%s""",
            (operator, now, reason, row["id"]),
        )
        resolved += 1
    return resolved


def resolve_if_exists(
    cursor: Any,
    *,
    alert_code: str,
    case_key: str,
    reason: str,
    operator: str = "system",
) -> bool:
    """Resolve one specific (alert_code, case_key) row if it's currently open.

    For per-row callers (like a single import row that turned out clean) that
    can't compute a "still open" set the way a full-table rescan can.
    """
    cursor.execute(
        "SELECT id FROM system_alerts WHERE alert_code=%s AND case_key=%s AND status='open'",
        (alert_code, case_key),
    )
    row = cursor.fetchone()
    if row is None:
        return False
    cursor.execute(
        """UPDATE system_alerts
           SET status='resolved', resolved_by=%s, resolved_at=%s, resolution_reason=%s
           WHERE id=%s""",
        (operator, _now(), reason, row["id"]),
    )
    return True


def resolve_current_state_alert(
    cursor: Any,
    *,
    alert_code: str,
    case_key: str,
    reason: str,
    operator: str = "system",
) -> dict[str, Any]:
    """Resolve an alert after an explicit current-state projection says it cleared.

    Unlike the legacy per-row and full-scan helpers, this deliberately resolves
    both open and claimed rows.  Claim metadata is retained so the projection
    still shows who had accepted the work before the condition disappeared.
    """
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


def resolve_absent_current_state_alerts(
    cursor: Any,
    *,
    alert_code: str,
    still_present_case_keys: set[str],
    reason: str,
    operator: str = "system",
) -> int:
    """Bulk counterpart reserved for explicit complete current-state projectors."""
    alert_code = _required_text(alert_code, "alert_code", 50)
    operator = _required_text(operator, "operator", 100)
    reason = _required_text(reason, "reason", 500)
    if not isinstance(still_present_case_keys, set) or not all(
        isinstance(case_key, str) for case_key in still_present_case_keys
    ):
        raise ValueError("still_present_case_keys must be a set of strings")
    cursor.execute(
        """SELECT id, case_key FROM system_alerts
           WHERE alert_code=%s AND status IN ('open', 'claimed')
           FOR UPDATE""",
        (alert_code,),
    )
    now = _now()
    resolved = 0
    for row in cursor.fetchall():
        if row["case_key"] in still_present_case_keys:
            continue
        cursor.execute(
            """UPDATE system_alerts
               SET status='resolved', resolved_by=%s, resolved_at=%s,
                   resolution_reason=%s
               WHERE id=%s""",
            (operator, now, reason, row["id"]),
        )
        resolved += 1
    return resolved


def delete_system_alert(cursor: Any, *, alert_code: str, case_key: str) -> bool:
    """Remove a fallback-keyed row once it's superseded by a real case_no."""
    cursor.execute(
        "DELETE FROM system_alerts WHERE alert_code=%s AND case_key=%s",
        (alert_code, case_key),
    )
    return cursor.rowcount > 0


def list_system_alerts(
    cursor: Any,
    *,
    status: str | None = None,
    alert_code: str | None = None,
    source_domain: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_LIST_LIMIT:
        raise ValueError("system alert list limit must be between 1 and 200")
    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or not 0 <= offset <= _MAX_LIST_OFFSET
    ):
        raise ValueError("system alert list offset must be between 0 and 1000000")
    clauses: list[str] = []
    params: list[Any] = []
    if status is not None:
        if status not in _STATUSES:
            raise ValueError("invalid system alert status")
        clauses.append("status=%s")
        params.append(status)
    if alert_code is not None:
        clauses.append("alert_code=%s")
        params.append(alert_code)
    if source_domain is not None:
        clauses.append("source_domain=%s")
        params.append(source_domain)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor.execute(
        f"""SELECT * FROM system_alerts{where}
            ORDER BY updated_at DESC, id DESC
            LIMIT %s OFFSET %s""",
        tuple(params + [limit, offset]),
    )
    return [_decode_row(row) for row in cursor.fetchall()]


def get_system_alert(cursor: Any, alert_id: int) -> dict[str, Any] | None:
    if isinstance(alert_id, bool) or not isinstance(alert_id, int) or alert_id < 1:
        raise ValueError("alert_id must be a positive integer")
    cursor.execute("SELECT * FROM system_alerts WHERE id=%s", (alert_id,))
    row = cursor.fetchone()
    return _decode_row(row) if row else None


def claim_system_alert(cursor: Any, *, alert_id: int, operator: str) -> dict[str, Any]:
    if isinstance(alert_id, bool) or not isinstance(alert_id, int) or alert_id < 1:
        raise ValueError("alert_id must be a positive integer")
    operator = _required_text(operator, "operator", 100)
    cursor.execute("SELECT * FROM system_alerts WHERE id=%s FOR UPDATE", (alert_id,))
    alert = cursor.fetchone()
    if alert is None:
        raise ValueError("alert_id does not exist")
    if alert["status"] == "resolved":
        return {"result": "conflict", "alert": _decode_row(alert)}
    if alert["status"] == "claimed" and alert["claimed_by"] != operator:
        return {"result": "conflict", "alert": _decode_row(alert)}
    if alert["status"] == "claimed":
        return {"result": "existing", "alert": _decode_row(alert)}
    cursor.execute(
        "UPDATE system_alerts SET status='claimed', claimed_by=%s, claimed_at=%s WHERE id=%s",
        (operator, _now(), alert_id),
    )
    return {"result": "claimed", "alert": get_system_alert(cursor, alert_id)}


def resolve_system_alert(
    cursor: Any, *, alert_id: int, operator: str, reason: str
) -> dict[str, Any]:
    if isinstance(alert_id, bool) or not isinstance(alert_id, int) or alert_id < 1:
        raise ValueError("alert_id must be a positive integer")
    operator = _required_text(operator, "operator", 100)
    reason = _required_text(reason, "reason", 500)
    cursor.execute("SELECT * FROM system_alerts WHERE id=%s FOR UPDATE", (alert_id,))
    alert = cursor.fetchone()
    if alert is None:
        raise ValueError("alert_id does not exist")
    if alert["status"] == "claimed" and alert["claimed_by"] != operator:
        return {"result": "conflict", "alert": _decode_row(alert)}
    if alert["status"] == "resolved":
        return {"result": "existing", "alert": _decode_row(alert)}
    cursor.execute(
        """UPDATE system_alerts
           SET status='resolved', resolved_by=%s, resolved_at=%s, resolution_reason=%s
           WHERE id=%s""",
        (operator, _now(), reason, alert_id),
    )
    return {"result": "resolved", "alert": get_system_alert(cursor, alert_id)}


