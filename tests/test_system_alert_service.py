from __future__ import annotations

import copy
from datetime import datetime

import pytest

from subsystems.anomalies.system_alert_projection import (
    get_system_alert,
    list_system_alerts,
    upsert_system_alert,
)


class Cursor:
    def __init__(self) -> None:
        self.rows: dict[int, dict] = {}
        self.lastrowid = 0
        self.rowcount = 0
        self._one = None
        self._many: list[dict] = []
        self.operations: list[tuple[str, tuple]] = []

    def seed(self, **overrides) -> int:
        self.lastrowid += 1
        row = {
            "id": self.lastrowid,
            "alert_code": "IMPORT-006",
            "source_domain": "IMPORT",
            "case_key": f"batch:{self.lastrowid}",
            "reason": "needs review",
            "details": '{"count":1}',
            "status": "open",
            "claimed_by": None,
            "claimed_at": None,
            "resolved_by": None,
            "resolved_at": None,
            "resolution_reason": None,
            "created_at": datetime(2026, 7, 31, 8, 0),
            "updated_at": datetime(2026, 7, 31, 8, 0),
        }
        row.update(overrides)
        self.rows[row["id"]] = row
        return row["id"]

    def execute(self, sql: str, params=()) -> None:
        normalized = " ".join(sql.split())
        params = tuple(params)
        self.operations.append((normalized, params))
        self.rowcount = 0
        self._one = None
        self._many = []

        if normalized.startswith(
            "SELECT id, source_domain, reason, details, status FROM system_alerts"
        ):
            code, case_key = params
            self._one = self._find(code, case_key)
        elif normalized.startswith("INSERT INTO system_alerts"):
            code, domain, case_key, reason, details = params
            self.seed(
                alert_code=code,
                source_domain=domain,
                case_key=case_key,
                reason=reason,
                details=details,
            )
            self.rowcount = 1
        elif "SET source_domain=%s, reason=%s, details=%s, status='open'" in normalized:
            domain, reason, details, updated_at, alert_id = params
            self.rows[alert_id].update(
                source_domain=domain,
                reason=reason,
                details=details,
                status="open",
                claimed_by=None,
                claimed_at=None,
                resolved_by=None,
                resolved_at=None,
                resolution_reason=None,
                updated_at=updated_at,
            )
            self.rowcount = 1
        elif "SET source_domain=%s, reason=%s, details=%s, updated_at=%s" in normalized:
            domain, reason, details, updated_at, alert_id = params
            self.rows[alert_id].update(
                source_domain=domain,
                reason=reason,
                details=details,
                updated_at=updated_at,
            )
            self.rowcount = 1
        elif normalized == "SELECT * FROM system_alerts WHERE id=%s":
            self._one = self._by_id(params[0])
        elif normalized.startswith(
            "SELECT * FROM system_alerts WHERE alert_code=%s AND case_key=%s FOR UPDATE"
        ):
            self._one = self._find(params[0], params[1])
        elif normalized.startswith(
            "SELECT id, case_key FROM system_alerts WHERE alert_code=%s AND status='open'"
        ):
            code = params[0]
            self._many = [
                {"id": row["id"], "case_key": row["case_key"]}
                for row in self.rows.values()
                if row["alert_code"] == code and row["status"] == "open"
            ]
        elif normalized.startswith(
            "SELECT id, case_key FROM system_alerts WHERE alert_code=%s AND status IN"
        ):
            code = params[0]
            self._many = [
                {"id": row["id"], "case_key": row["case_key"]}
                for row in self.rows.values()
                if row["alert_code"] == code and row["status"] in {"open", "claimed"}
            ]
        elif normalized.startswith(
            "SELECT id FROM system_alerts WHERE alert_code=%s AND case_key=%s AND status='open'"
        ):
            row = self._find(params[0], params[1])
            self._one = {"id": row["id"]} if row and row["status"] == "open" else None
        elif normalized.startswith("SELECT * FROM system_alerts WHERE id=%s FOR UPDATE"):
            self._one = self._by_id(params[0])
        elif normalized.startswith("UPDATE system_alerts SET status='claimed'"):
            operator, claimed_at, alert_id = params
            self.rows[alert_id].update(
                status="claimed", claimed_by=operator, claimed_at=claimed_at
            )
            self.rowcount = 1
        elif normalized.startswith("UPDATE system_alerts SET status='resolved'"):
            operator, resolved_at, reason, alert_id = params
            self.rows[alert_id].update(
                status="resolved",
                resolved_by=operator,
                resolved_at=resolved_at,
                resolution_reason=reason,
            )
            self.rowcount = 1
        elif normalized.startswith("SELECT * FROM system_alerts"):
            self._many = self._list_query(normalized, params)
        else:
            raise AssertionError(f"unexpected SQL: {normalized}")

    def fetchone(self):
        return copy.deepcopy(self._one)

    def fetchall(self):
        return copy.deepcopy(self._many)

    def _find(self, code: str, case_key: str):
        return next(
            (
                copy.deepcopy(row)
                for row in self.rows.values()
                if row["alert_code"] == code and row["case_key"] == case_key
            ),
            None,
        )

    def _by_id(self, alert_id: int):
        row = self.rows.get(alert_id)
        return copy.deepcopy(row) if row else None

    def _list_query(self, sql: str, params: tuple):
        filters = params[:-2]
        position = 0
        rows = list(self.rows.values())
        for field in ("status", "alert_code", "source_domain"):
            if f"{field}=%s" in sql:
                value = filters[position]
                position += 1
                rows = [row for row in rows if row[field] == value]
        rows.sort(key=lambda row: (row["updated_at"], row["id"]), reverse=True)
        limit, offset = params[-2:]
        return [copy.deepcopy(row) for row in rows[offset : offset + limit]]


def _upsert(cursor: Cursor, **overrides):
    values = {
        "alert_code": "IMPORT-006",
        "source_domain": "IMPORT",
        "case_key": "batch:1",
        "reason": "needs review",
        "details": {"count": 2},
    }
    values.update(overrides)
    return upsert_system_alert(cursor, **values)


def test_upsert_create_and_identical_retry_are_deterministic():
    cursor = Cursor()

    created = _upsert(cursor)
    existing = _upsert(cursor)

    assert created["result"] == "created"
    assert existing["result"] == "existing"
    assert len(cursor.rows) == 1
    assert existing["alert"]["details"] == {"count": 2}


def test_upsert_refreshes_claimed_projection_without_losing_claim():
    cursor = Cursor()
    alert_id = cursor.seed(
        case_key="batch:1", status="claimed", claimed_by="amy", claimed_at=datetime.now()
    )

    result = _upsert(cursor, reason="still blocked", details={"count": 3})

    assert result["result"] == "updated"
    assert cursor.rows[alert_id]["status"] == "claimed"
    assert cursor.rows[alert_id]["claimed_by"] == "amy"
    assert result["alert"]["details"] == {"count": 3}


def test_upsert_reopens_and_clears_old_workflow_metadata():
    cursor = Cursor()
    alert_id = cursor.seed(
        case_key="batch:1",
        status="resolved",
        claimed_by="amy",
        claimed_at=datetime.now(),
        resolved_by="amy",
        resolved_at=datetime.now(),
        resolution_reason="fixed",
    )

    result = _upsert(cursor)

    assert result["result"] == "reopened"
    assert cursor.rows[alert_id]["status"] == "open"
    assert cursor.rows[alert_id]["claimed_by"] is None
    assert cursor.rows[alert_id]["resolved_by"] is None


@pytest.mark.parametrize(
    "details",
    [
        {"password": "secret"},
        {"raw_payload": {"anything": "value"}},
        {"payload": {"anything": "value"}},
        {"rawPayload": {"anything": "value"}},
        {"raw-row": {"anything": "value"}},
        {"raw row": {"anything": "value"}},
        {"accountNumber": "1234567890"},
        {"bank-account-number": "1234567890"},
        {"client bank account": "1234567890"},
        {"客戶帳號": "1234567890"},
        {"完整-帳號": "1234567890"},
        {"masked_bank_account_last4": "1234567890"},
        {"maskedBankAccount": "1234567890"},
        {"銀行帳號末四碼": "12345"},
        {"nested": {"rowPayload": {"anything": "value"}}},
        {"row_ids": list(range(201))},
        {"value": float("nan")},
    ],
)
def test_details_reject_sensitive_unbounded_or_non_json_values(details):
    with pytest.raises(ValueError):
        _upsert(Cursor(), details=details)


@pytest.mark.parametrize(
    "details",
    [
        {"masked_bank_account_last4": "1234"},
        {"bankAccountLast4": 1234},
        {"masked-bank-account": "******1234"},
        {"銀行帳號末四碼": "5678"},
        {"遮罩銀行帳號": "••••4321"},
        {"nested": {"maskedAccountNumber": "####A123"}},
    ],
)
def test_details_allow_explicit_safe_partial_account_references(details):
    result = _upsert(Cursor(), details=details)

    assert result["result"] == "created"
    assert result["alert"]["details"] == details


def test_list_and_detail_are_bounded_read_only_projections():
    cursor = Cursor()
    first = cursor.seed(alert_code="ORDER-001", source_domain="ORDER")
    cursor.seed(alert_code="IMPORT-006", source_domain="IMPORT")
    before = copy.deepcopy(cursor.rows)

    rows = list_system_alerts(cursor, source_domain="ORDER", limit=1, offset=0)
    detail = get_system_alert(cursor, first)

    assert len(rows) == 1
    assert rows[0]["source_id"] == rows[0]["case_key"]
    assert detail["details"] == {"count": 1}
    assert cursor.rows == before
    assert all(not sql.startswith(("UPDATE", "INSERT", "DELETE")) for sql, _ in cursor.operations)


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (201, 0), (True, 0), (1, -1), (1, 1_000_001), (1, False)],
)
def test_list_rejects_unbounded_pagination(limit, offset):
    with pytest.raises(ValueError):
        list_system_alerts(Cursor(), limit=limit, offset=offset)
