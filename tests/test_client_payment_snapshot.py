from datetime import date, datetime

import pytest

from subsystems.client_finance.payment_snapshot import create_client_payment_snapshot


def _plan(deposit_due_date="2026-08-03"):
    return {
        "client_ledger_plan": {
            "amount_receivable": 300,
            "stages": [
                {"stage": "deposit", "receivable": 100, "due_date": deposit_due_date},
                {"stage": "first_payment", "receivable": 100, "due_date": "2026-08-10"},
                {"stage": "second_payment", "receivable": 100, "due_date": None},
            ],
        },
    }


def _order():
    return {"case_no": "114000001", "start_date": "2026-08-01"}


def _schedule():
    return {"deposit_service_days": 5, "deposit_due_date": "2026-08-03"}


class _Cursor:
    def __init__(self, existing=None, lastrowid=12):
        self.existing = existing
        self.lastrowid = lastrowid
        self.executions = []

    def execute(self, statement, parameters):
        self.executions.append((statement, parameters))

    def fetchone(self):
        return self.existing


def test_missing_contract_terms_require_review_without_calculation():
    result = create_client_payment_snapshot(_Cursor(), _order(), {"deposit_due_date": "2026-08-03"})

    assert result == {"payment_id": None, "plan": None, "result": "review_required", "reason": "deposit_service_days_missing"}


def test_creates_canonical_snapshot_using_plan_stage_order():
    cursor = _Cursor()
    result = create_client_payment_snapshot(cursor, _order(), _schedule(), calculator=lambda *_: _plan())

    assert result["result"] == "created"
    assert result["payment_id"] == 12
    assert "INSERT INTO client_payments" in cursor.executions[1][0]
    assert cursor.executions[1][1] == ("114000001", 100, "2026-08-03", 100, "2026-08-10", 100, None, 300)


def test_matching_existing_snapshot_is_idempotent_when_dates_have_different_runtime_types():
    existing = {
        "id": 12,
        "deposit_receivable": 100,
        "deposit_due_date": datetime(2026, 8, 3, 9),
        "first_payment_receivable": 100,
        "first_payment_due_date": date(2026, 8, 10),
        "second_payment_receivable": 100,
        "second_payment_due_date": None,
        "amount_receivable": 300,
    }
    result = create_client_payment_snapshot(_Cursor(existing), _order(), _schedule(), calculator=lambda *_: _plan())

    assert result["result"] == "existing"
    assert result["payment_id"] == 12


def test_changed_existing_snapshot_requires_manual_review():
    existing = {
        "id": 12,
        "deposit_receivable": 90,
        "deposit_due_date": "2026-08-03",
        "first_payment_receivable": 100,
        "first_payment_due_date": "2026-08-10",
        "second_payment_receivable": 100,
        "second_payment_due_date": None,
        "amount_receivable": 290,
    }
    assert create_client_payment_snapshot(_Cursor(existing), _order(), _schedule(), calculator=lambda *_: _plan())["result"] == "review_required"


def test_snapshot_rejects_noncanonical_stage_set():
    malformed = _plan()
    malformed["client_ledger_plan"]["stages"].pop()
    with pytest.raises(ValueError, match="all three"):
        create_client_payment_snapshot(_Cursor(), _order(), _schedule(), calculator=lambda *_: malformed)
