"""B6 integration coverage for append-only formal finance alert events."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime

import pytest

from services.finance_alert_events import append_finance_alert_event


OCCURRED_AT = datetime(2026, 7, 18, 9, 30, 0)


class TransactionConnection:
    def get_autocommit(self):
        return False


class FormalEventCursor:
    """Stateful cursor boundary for the event service and fixed source tables."""

    def __init__(self, state):
        self.state = state
        self.connection = TransactionConnection()
        self.current = None
        self.lastrowid = None
        self.savepoints = {}

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        params = params or ()
        self.current = None

        if compact.startswith("SAVEPOINT "):
            self.savepoints[compact.split()[-1]] = deepcopy(self.state["events"])
        elif compact.startswith("ROLLBACK TO SAVEPOINT "):
            self.state["events"] = deepcopy(self.savepoints[compact.split()[-1]])
        elif compact.startswith("RELEASE SAVEPOINT "):
            self.savepoints.pop(compact.split()[-1], None)
        elif "FROM finance_alerts" in compact:
            self.current = self.state["alerts"].get(params[0])
        elif "FROM finance_alert_events" in compact:
            self.current = self.state["events"].get(params[0])
        elif compact.startswith("SELECT"):
            table = next(
                table
                for table in self.state["formal_tables"]
                if f"FROM {table}" in compact
            )
            self.current = self.state["formal_tables"][table].get(params[0])
        elif compact.startswith("INSERT INTO finance_alert_events"):
            event_id = max(
                (event["id"] for event in self.state["events"].values()),
                default=900,
            ) + 1
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
        else:
            raise AssertionError(f"unexpected SQL: {compact}")

    def fetchone(self):
        return self.current


def _formal(*, identifier, transaction_type, status, reference):
    return {
        "id": identifier,
        "transaction_type": transaction_type,
        "transaction_status": status,
        "external_reference": reference,
    }


def _state():
    return {
        "alerts": {
            41: {
                "id": 41,
                "status": "open",
                "claimed_by": None,
                "claimed_at": None,
                "resolved_by": None,
                "resolved_at": None,
                "resolution_reason": None,
            }
        },
        "events": {},
        "formal_tables": {
            "client_payment_transactions": {
                201: _formal(
                    identifier=201,
                    transaction_type="refund",
                    status="succeeded",
                    reference="client-return-201",
                )
            },
            "staff_payment_transactions": {},
            "staff_actual_transfers": {
                101: _formal(
                    identifier=101,
                    transaction_type="transfer",
                    status="failed",
                    reference="staff-failed-101",
                ),
                102: _formal(
                    identifier=102,
                    transaction_type="transfer",
                    status="failed",
                    reference="staff-original-102",
                ),
                103: _formal(
                    identifier=103,
                    transaction_type="transfer",
                    status="succeeded",
                    reference="staff-retransfer-103",
                ),
            },
            "government_subsidy_transactions": {
                301: _formal(
                    identifier=301,
                    transaction_type="reversal",
                    status="succeeded",
                    reference="government-reversal-301",
                )
            },
        },
        "allocations": [{"id": 601, "amount": "1000.00"}],
        "receivables": {"client": "1250.00", "government": "1000.00"},
        "payables": {"staff": "32000.00"},
        "paid_projection": {"client": "0.00", "government": "0.00", "staff": "0.00"},
        "staging": {"id": 71, "reconciliation_status": "pending"},
    }


def _protected_snapshot(state):
    return deepcopy(
        {
            "formal_tables": state["formal_tables"],
            "allocations": state["allocations"],
            "receivables": state["receivables"],
            "payables": state["payables"],
            "paid_projection": state["paid_projection"],
            "staging": state["staging"],
        }
    )


FORMAL_EVENT_FIXTURES = (
    {
        "event_type": "failed",
        "event_key": "staff:101:failed",
        "source_domain": "staff_actual_transfer",
        "source_type": "staff_actual_transfer",
        "source_id": 101,
        "event_snapshot": {"status": "failed", "amount": "1000.00"},
    },
    {
        "event_type": "returned",
        "event_key": "client:201:returned",
        "source_domain": "client_subsidy_return",
        "source_type": "client_payment_transaction",
        "source_id": 201,
        "event_snapshot": {"status": "returned", "amount": "1250.00"},
    },
    {
        "event_type": "retransferred",
        "event_key": "staff:103:retransferred",
        "source_domain": "staff_actual_transfer",
        "source_type": "staff_actual_transfer",
        "source_id": 103,
        "original_source_id": 102,
        "event_snapshot": {"status": "retransferred", "amount": "1000.00"},
    },
    {
        "event_type": "reversed",
        "event_key": "government:301:reversed",
        "source_domain": "government_subsidy",
        "source_type": "government_subsidy_transaction",
        "source_id": 301,
        "event_snapshot": {"status": "reversed", "amount": "1000.00"},
    },
)


def _append(cursor, fixture, **changes):
    values = {
        "alert_id": 41,
        "occurred_at": OCCURRED_AT,
        **fixture,
    }
    values.update(changes)
    return append_finance_alert_event(cursor, **values)


@pytest.mark.parametrize("fixture", FORMAL_EVENT_FIXTURES)
def test_formal_events_reference_existing_finance_only_and_rerun_idempotently(fixture):
    state = _state()
    cursor = FormalEventCursor(state)
    protected = _protected_snapshot(state)

    created = _append(cursor, fixture)
    rerun = _append(cursor, fixture)

    assert created["result"] == "created"
    assert rerun["result"] == "existing"
    assert len(state["events"]) == 1
    event = state["events"][fixture["event_key"]]
    assert event["event_type"] == fixture["event_type"]
    assert event["source_type"] == fixture["source_type"]
    assert event["source_id"] == str(fixture["source_id"])
    assert _protected_snapshot(state) == protected


@pytest.mark.parametrize(
    ("fixture", "mutation", "message"),
    (
        (
            FORMAL_EVENT_FIXTURES[0],
            {"source_id": 999},
            "does not exist",
        ),
        (
            FORMAL_EVENT_FIXTURES[1],
            {"source_id": 101, "source_type": "staff_actual_transfer"},
            "succeeded return or refund",
        ),
        (
            FORMAL_EVENT_FIXTURES[2],
            {"original_source_id": 103},
            "must differ",
        ),
        (
            FORMAL_EVENT_FIXTURES[3],
            {"source_id": 201, "source_type": "client_payment_transaction"},
            "reversal row or reversed status",
        ),
    ),
)
def test_invalid_formal_source_fails_fast_without_changing_finance(fixture, mutation, message):
    state = _state()
    cursor = FormalEventCursor(state)
    protected = _protected_snapshot(state)

    with pytest.raises(ValueError, match=message):
        _append(cursor, fixture, **mutation)

    assert state["events"] == {}
    assert _protected_snapshot(state) == protected


def test_conflicting_event_key_preserves_existing_event_and_formal_finance():
    state = _state()
    cursor = FormalEventCursor(state)
    fixture = FORMAL_EVENT_FIXTURES[0]
    created = _append(cursor, fixture)
    protected = _protected_snapshot(state)
    event_before = deepcopy(created["event"])

    with pytest.raises(ValueError, match="immutable event data"):
        _append(cursor, fixture, event_snapshot={"status": "failed", "amount": "999.00"})

    assert state["events"][fixture["event_key"]] == event_before
    assert _protected_snapshot(state) == protected
