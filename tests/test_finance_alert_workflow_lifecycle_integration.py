"""B6 integration coverage for pending/review finance alert lifecycles."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import json

import pytest

from services.finance_alert_detection import create_or_get_finance_alert
from services.finance_alert_workflow import (
    claim_finance_alert,
    get_finance_alert,
    resolve_finance_alert,
)


DETECTED_AT = datetime(2026, 7, 16, 9, 0, 0)
CLAIMED_AT = datetime(2026, 7, 16, 10, 0, 0)
RESOLVED_AT = datetime(2026, 7, 16, 11, 0, 0)


class TransactionConnection:
    def get_autocommit(self):
        return False


class AlertStoreCursor:
    """Stateful MySQL-shaped boundary used to integrate the real B6 services."""

    def __init__(self, state):
        self.state = state
        self.connection = TransactionConnection()
        self.current = None
        self.lastrowid = None
        self.rowcount = 0
        self.savepoints = {}

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        params = params or ()
        self.current = None
        self.rowcount = 0

        if compact.startswith("SAVEPOINT "):
            name = compact.split()[-1]
            self.savepoints[name] = deepcopy(
                (self.state["alerts"], self.state["events"])
            )
        elif compact.startswith("ROLLBACK TO SAVEPOINT "):
            name = compact.split()[-1]
            alerts, events = deepcopy(self.savepoints[name])
            self.state["alerts"] = alerts
            self.state["events"] = events
        elif compact.startswith("RELEASE SAVEPOINT "):
            self.savepoints.pop(compact.split()[-1], None)
        elif compact.startswith("SELECT r.id FROM finance_import_rows"):
            batch_id, row_id, canonical_batch_id = params
            row = self.state["staging_rows"].get(row_id)
            occurrence = (row_id, batch_id) in self.state["occurrences"]
            self.current = (
                {"id": row_id}
                if row
                and (row["batch_id"] == canonical_batch_id or occurrence)
                else None
            )
        elif compact.startswith("SELECT id FROM finance_import_rows"):
            self.current = (
                {"id": params[0]}
                if params[0] in self.state["staging_rows"]
                else None
            )
        elif compact.startswith("SELECT id FROM finance_import_batches"):
            self.current = (
                {"id": params[0]}
                if params[0] in self.state["batches"]
                else None
            )
        elif compact.startswith("SELECT") and "FROM finance_alerts" in compact:
            if "WHERE alert_key=%s" in compact:
                self.current = self._alert_by_key(params[0])
            elif "WHERE id=%s" in compact:
                self.current = self.state["alerts"].get(params[0])
            else:
                raise AssertionError(f"unexpected alert query: {compact}")
        elif compact.startswith("SELECT") and "FROM finance_alert_events" in compact:
            if "WHERE event_key=%s" in compact:
                self.current = self.state["events"].get(params[0])
            elif "WHERE alert_id=%s" in compact:
                self.current = sorted(
                    (
                        event
                        for event in self.state["events"].values()
                        if event["alert_id"] == params[0]
                    ),
                    key=lambda event: (event["occurred_at"], event["id"]),
                )
            else:
                raise AssertionError(f"unexpected event query: {compact}")
        elif compact.startswith("INSERT INTO finance_alerts"):
            alert_id = max(self.state["alerts"], default=40) + 1
            keys = (
                "alert_key",
                "alert_code",
                "source_domain",
                "source_type",
                "source_id",
                "finance_import_row_id",
                "finance_import_batch_id",
                "reason",
                "expected_amount",
                "actual_amount",
                "difference_amount",
                "candidate_snapshot",
            )
            alert = dict(zip(keys, params, strict=True))
            alert.update(
                {
                    "id": alert_id,
                    "status": "open",
                    "claimed_by": None,
                    "claimed_at": None,
                    "resolved_by": None,
                    "resolved_at": None,
                    "resolution_reason": None,
                    "created_at": DETECTED_AT,
                    "updated_at": DETECTED_AT,
                }
            )
            self.state["alerts"][alert_id] = alert
            self.lastrowid = alert_id
            self.rowcount = 1
        elif compact.startswith("INSERT INTO finance_alert_events"):
            event_id = max(
                (event["id"] for event in self.state["events"].values()),
                default=90,
            ) + 1
            if "'detected'" in compact:
                (
                    alert_id,
                    event_key,
                    source_domain,
                    source_type,
                    source_id,
                    reason,
                    event_snapshot,
                    occurred_at,
                ) = params
                event_type = "detected"
                actor = None
            else:
                (
                    alert_id,
                    event_key,
                    event_type,
                    source_domain,
                    source_type,
                    source_id,
                    actor,
                    reason,
                    event_snapshot,
                    occurred_at,
                ) = params
            event = {
                "id": event_id,
                "alert_id": alert_id,
                "event_key": event_key,
                "event_type": event_type,
                "source_domain": source_domain,
                "source_type": source_type,
                "source_id": source_id,
                "actor": actor,
                "reason": reason,
                "event_snapshot": event_snapshot,
                "occurred_at": occurred_at,
                "created_at": occurred_at,
            }
            self.state["events"][event_key] = event
            self.lastrowid = event_id
            self.rowcount = 1
        elif compact.startswith(
            "UPDATE finance_alerts SET status='claimed'"
        ):
            operator, occurred_at, alert_id = params
            alert = self.state["alerts"][alert_id]
            if alert["status"] == "open":
                alert.update(
                    {
                        "status": "claimed",
                        "claimed_by": operator,
                        "claimed_at": occurred_at,
                        "updated_at": occurred_at,
                    }
                )
                self.rowcount = 1
        elif compact.startswith(
            "UPDATE finance_alerts SET status='resolved'"
        ):
            operator, occurred_at, reason, alert_id, prior_status = params
            alert = self.state["alerts"][alert_id]
            if alert["status"] == prior_status:
                alert.update(
                    {
                        "status": "resolved",
                        "resolved_by": operator,
                        "resolved_at": occurred_at,
                        "resolution_reason": reason,
                        "updated_at": occurred_at,
                    }
                )
                self.rowcount = 1
        else:
            raise AssertionError(f"unexpected SQL: {compact}")

    def fetchone(self):
        return self.current

    def fetchall(self):
        return list(self.current or [])

    def _alert_by_key(self, alert_key):
        return next(
            (
                alert
                for alert in self.state["alerts"].values()
                if alert["alert_key"] == alert_key
            ),
            None,
        )


def _state():
    staging_rows = {
        row_id: {
            "id": row_id,
            "batch_id": 7,
            "reconciliation_status": "pending",
            "raw_payload": {"source_row": row_id, "memo": f"pending-{row_id}"},
        }
        for row_id in range(11, 16)
    }
    return {
        "batches": {7: {"id": 7, "status": "staged"}},
        "staging_rows": staging_rows,
        "occurrences": set(),
        "alerts": {},
        "events": {},
        "formal_finance": {
            "transactions": [{"id": 501, "amount": Decimal("900.00")}],
            "allocations": [{"id": 701, "amount": Decimal("900.00")}],
            "paid_projection": Decimal("900.00"),
        },
    }


BOUNDARY_FIXTURES = (
    {
        "alert_code": "client_payment_pending",
        "source_domain": "client_payment",
        "row_id": 11,
        "reason": "客戶入帳金額不足，保留人工覆核",
        "expected": Decimal("1000.00"),
        "actual": Decimal("999.99"),
        "difference": Decimal("-0.01"),
        "candidates": {"client_payment_ids": [101]},
    },
    {
        "alert_code": "client_subsidy_return_review",
        "source_domain": "client_subsidy_return",
        "row_id": 12,
        "reason": "退款候選不唯一",
        "expected": Decimal("1250.00"),
        "actual": Decimal("1250.00"),
        "difference": Decimal("0.00"),
        "candidates": {"client_payment_ids": [102, 103]},
    },
    {
        "alert_code": "government_subsidy_pending",
        "source_domain": "government_subsidy",
        "row_id": 13,
        "reason": "補助款找不到唯一核准批次",
        "expected": Decimal("5000.00"),
        "actual": Decimal("5000.00"),
        "difference": Decimal("0.00"),
        "candidates": {"approval_batch_ids": [201, 202]},
    },
    {
        "alert_code": "staff_transfer_review",
        "source_domain": "staff_actual_transfer",
        "row_id": 14,
        "reason": "薪資匯款與應付額不一致",
        "expected": Decimal("32000.00"),
        "actual": Decimal("31999.00"),
        "difference": Decimal("-1.00"),
        "candidates": {"staff_ids": [301]},
    },
    {
        "alert_code": "common_non_business_review",
        "source_domain": "common",
        "row_id": 15,
        "reason": "非業務流水需人工判讀",
        "expected": None,
        "actual": Decimal("88.00"),
        "difference": None,
        "candidates": {"classification": "non_business_review"},
    },
)


def _detection_kwargs(fixture):
    row_id = fixture["row_id"]
    return {
        "alert_code": fixture["alert_code"],
        "source_domain": fixture["source_domain"],
        "source_type": "finance_import_row",
        "source_id": str(row_id),
        "finance_import_row_id": row_id,
        "finance_import_batch_id": 7,
        "reason": fixture["reason"],
        "expected_amount": fixture["expected"],
        "actual_amount": fixture["actual"],
        "difference_amount": fixture["difference"],
        "candidate_snapshot": fixture["candidates"],
        "detected_at": DETECTED_AT,
    }


def _protected_snapshot(state):
    return deepcopy(
        {
            "batches": state["batches"],
            "staging_rows": state["staging_rows"],
            "occurrences": state["occurrences"],
            "formal_finance": state["formal_finance"],
        }
    )


@pytest.mark.parametrize("fixture", BOUNDARY_FIXTURES)
def test_pending_and_review_boundaries_persist_complete_audit_without_finance_writes(
    fixture,
):
    state = _state()
    cursor = AlertStoreCursor(state)
    protected = _protected_snapshot(state)

    result = create_or_get_finance_alert(cursor, **_detection_kwargs(fixture))

    alert = result["alert"]
    assert result["result"] == "created"
    assert alert["status"] == "open"
    assert alert["alert_code"] == fixture["alert_code"]
    assert alert["source_domain"] == fixture["source_domain"]
    assert alert["finance_import_row_id"] == fixture["row_id"]
    assert alert["finance_import_batch_id"] == 7
    assert alert["reason"] == fixture["reason"]
    assert alert["expected_amount"] == fixture["expected"]
    assert alert["actual_amount"] == fixture["actual"]
    assert alert["difference_amount"] == fixture["difference"]
    assert json.loads(alert["candidate_snapshot"]) == fixture["candidates"]
    assert [event["event_type"] for event in state["events"].values()] == [
        "detected"
    ]
    assert _protected_snapshot(state) == protected


def test_full_lifecycle_is_deterministic_and_preserves_manual_resolution():
    state = _state()
    cursor = AlertStoreCursor(state)
    fixture = BOUNDARY_FIXTURES[2]
    kwargs = _detection_kwargs(fixture)
    protected = _protected_snapshot(state)

    created = create_or_get_finance_alert(cursor, **kwargs)
    alert_id = created["alert"]["id"]
    detected_rerun = create_or_get_finance_alert(cursor, **kwargs)
    claimed = claim_finance_alert(
        cursor,
        alert_id=alert_id,
        operator="finance-owner",
        occurred_at=CLAIMED_AT,
    )
    claim_rerun = claim_finance_alert(
        cursor,
        alert_id=alert_id,
        operator="finance-owner",
        occurred_at=datetime(2026, 7, 17, 10, 0, 0),
    )
    competing_claim = claim_finance_alert(
        cursor,
        alert_id=alert_id,
        operator="other-owner",
    )
    resolved = resolve_finance_alert(
        cursor,
        alert_id=alert_id,
        operator="finance-owner",
        reason="已核對原始憑證，無須建立正式交易",
        occurred_at=RESOLVED_AT,
    )
    resolved_rerun = resolve_finance_alert(
        cursor,
        alert_id=alert_id,
        operator="finance-owner",
        reason="已核對原始憑證，無須建立正式交易",
        occurred_at=datetime(2026, 7, 18, 11, 0, 0),
    )
    post_resolution_detection = create_or_get_finance_alert(cursor, **kwargs)
    detail = get_finance_alert(cursor, alert_id)

    assert detected_rerun["result"] == "existing"
    assert claimed["result"] == "claimed"
    assert claim_rerun["result"] == "existing"
    assert competing_claim["result"] == "conflict"
    assert competing_claim["alert"]["claimed_by"] == "finance-owner"
    assert resolved["result"] == "resolved"
    assert resolved_rerun["result"] == "existing"
    assert post_resolution_detection["result"] == "existing"
    assert post_resolution_detection["alert"]["status"] == "resolved"
    assert detail is not None
    assert detail["claimed_by"] == "finance-owner"
    assert detail["claimed_at"] == CLAIMED_AT
    assert detail["resolved_by"] == "finance-owner"
    assert detail["resolved_at"] == RESOLVED_AT
    assert detail["resolution_reason"] == "已核對原始憑證，無須建立正式交易"
    assert [event["event_type"] for event in detail["events"]] == [
        "detected",
        "claimed",
        "resolved",
    ]
    assert len(state["alerts"]) == 1
    assert len(state["events"]) == 3
    assert _protected_snapshot(state) == protected


def test_conflicting_detection_and_partial_residue_fail_fast_without_repair():
    state = _state()
    cursor = AlertStoreCursor(state)
    kwargs = _detection_kwargs(BOUNDARY_FIXTURES[0])
    created = create_or_get_finance_alert(cursor, **kwargs)
    protected = _protected_snapshot(state)
    alert_before = deepcopy(created["alert"])

    with pytest.raises(ValueError, match="immutable detection data"):
        create_or_get_finance_alert(
            cursor,
            **{
                **kwargs,
                "candidate_snapshot": {"client_payment_ids": [999]},
            },
        )

    detected_key = next(
        key
        for key, event in state["events"].items()
        if event["event_type"] == "detected"
    )
    del state["events"][detected_key]

    with pytest.raises(RuntimeError, match="missing its detected event"):
        create_or_get_finance_alert(cursor, **kwargs)

    assert state["alerts"][alert_before["id"]] == alert_before
    assert state["events"] == {}
    assert _protected_snapshot(state) == protected


def test_workflow_projection_residue_fails_fast_and_keeps_staging_pending():
    state = _state()
    cursor = AlertStoreCursor(state)
    created = create_or_get_finance_alert(
        cursor,
        **_detection_kwargs(BOUNDARY_FIXTURES[3]),
    )
    alert_id = created["alert"]["id"]
    alert = state["alerts"][alert_id]
    alert.update(
        {
            "status": "claimed",
            "claimed_by": "finance-owner",
            "claimed_at": CLAIMED_AT,
            "updated_at": CLAIMED_AT,
        }
    )
    protected = _protected_snapshot(state)

    with pytest.raises(RuntimeError, match="missing its claimed event"):
        claim_finance_alert(
            cursor,
            alert_id=alert_id,
            operator="finance-owner",
        )

    assert alert["status"] == "claimed"
    assert alert["claimed_by"] == "finance-owner"
    assert [event["event_type"] for event in state["events"].values()] == [
        "detected"
    ]
    assert _protected_snapshot(state) == protected
