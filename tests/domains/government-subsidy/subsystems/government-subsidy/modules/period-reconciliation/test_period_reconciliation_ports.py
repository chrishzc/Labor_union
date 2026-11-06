"""Original bank-based period contract via real API/application; never execute SQL."""
from dataclasses import replace
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies.admin_auth import require_system_admin
import api.routes.government_subsidy_periods as routes
from domains.government_subsidy.period_reconciliation import PeriodReconciliationConflict, SubsidyPeriod, SubsidyPeriodLine
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.government_subsidy.period_reconciliation import PeriodCoverage, PeriodReconciliationApplication, SubsidyPeriodView


class NoSqlConnection:
    def __init__(self): self.events = []
    def cursor(self): raise AssertionError("Project SQL, including fake SQL, is forbidden")
    def begin(self): self.events.append("begin")
    def commit(self): self.events.append("commit")
    def rollback(self): self.events.append("rollback")


class PeriodPort:
    """Only persistence is substituted; application and domain guards execute."""
    def __init__(self, period, failure=None):
        self.period, self.failure = period, failure
        self.events = []
        self.saved = []
        self.receipts = {}
        line = SubsidyPeriodLine("CASE-1", date(2026, 1, 15), None if failure == "incomplete" else 1000, None)
        self.view = SubsidyPeriodView(period, 2, (line,), line.amount_ntd, (), (), (), (), True)
        if failure == "overlap": self.view = replace(self.view, coverage=(PeriodCoverage(99, SubsidyPeriod("year", 2026, 1), 1000, 0),))
        if failure == "case_overlap": self.view = replace(self.view, blocked_cases=("CASE-1",))

    def query(self, period, *, lock=False):
        assert period == self.period
        self.events.append("lock_query" if lock else "query")
        return self.view

    def find_replay(self, key, command):
        self.events.append("find_replay")
        prior = self.receipts.get(key)
        if prior is None: return None
        if prior[0] != command: raise PeriodReconciliationConflict("subsidy_period_idempotency_conflict")
        return prior[1]

    def bank_amount(self, bank_row_id, *, reversal=False):
        assert (bank_row_id, reversal) == (7, False)
        self.events.append("bank_lock")
        if self.failure in {"bank_invalid", "bank_already_used"}:
            raise PeriodReconciliationConflict("subsidy_period_" + self.failure)
        return 999 if self.failure == "amount" else 1000

    def save(self, view, bank_row_id, key, actor):
        assert view is self.view and bank_row_id == 7 and actor == "admin:1"
        self.events.append("save")
        self.saved.append((view.period, bank_row_id, key, actor))
        self.receipts[key] = ((view.period.unit, view.period.year, view.period.index, bank_row_id, None), 42)
        self.view = replace(view, version=3, coverage=(PeriodCoverage(42, view.period, 1000, 0),), recorded_lines=view.lines)
        return 42

    def bank_rows(self):
        # A real bank date does not decide the selected service/receipt period.
        return ({"id": 7, "paid_on": date(2027, 11, 6), "amount_ntd": 1000},)


def client_for(period, failure=None):
    connection = NoSqlConnection()
    port = PeriodPort(period, failure)
    application = PeriodReconciliationApplication(port, lambda: MySqlUnitOfWork(connection))
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(1, "synthetic", "Synthetic", "system_admin")
    app.dependency_overrides[routes.get_application] = lambda: application
    return TestClient(app), connection, port


def command(period, version=2):
    return {"unit": period.unit, "year": period.year, "index": period.index,
            "bank_row_id": 7, "expected_version": version, "idempotency_key": "original-key"}


@pytest.mark.parametrize("unit", ["month", "quarter", "year"])
def test_original_period_api_uses_explicit_period_and_replays_same_receipt_before_mutable_coverage(unit):
    period = SubsidyPeriod(unit, 2026, 1)
    client, connection, port = client_for(period)
    with client:
        bank = client.get("/api/v1/government-subsidy/periods/bank-rows")
        assert bank.json()["data"]["items"][0]["paid_on"] == "2027-11-06"
        response = client.post("/api/v1/government-subsidy/periods/reconcile", json=command(period))
        assert response.status_code == 200 and response.json()["data"] == {"receipt_id": 42}
        assert port.saved == [(period, 7, "original-key", "admin:1")]
        assert connection.events == ["begin", "commit"]
        assert port.events == ["find_replay", "lock_query", "bank_lock", "save"]
        port.events.clear(); connection.events.clear()
        replay = client.post("/api/v1/government-subsidy/periods/reconcile", json=command(period))
        assert replay.status_code == 200 and replay.json() == response.json()
        assert port.events == ["find_replay"] and len(port.saved) == 1
        assert connection.events == ["begin", "commit"]
        readback = client.get("/api/v1/government-subsidy/periods", params={"unit": unit, "year": 2026, "index": 1})
        assert readback.status_code == 200
        view = readback.json()["data"]
        assert view["coverage"][0]["receipt_id"] == 42 and view["coverage"][0]["period"] == view["period"]
        assert len(view["recorded_lines"]) == 1 and view["recorded_lines"][0]["case_no"] == "CASE-1"


@pytest.mark.parametrize("failure,code", [
    ("stale", "subsidy_period_stale"), ("overlap", "subsidy_period_already_covered"),
    ("case_overlap", "subsidy_case_already_covered"), ("incomplete", "subsidy_period_incomplete"),
    ("amount", "subsidy_period_amount_mismatch"), ("bank_invalid", "subsidy_period_bank_invalid"),
    ("bank_already_used", "subsidy_period_bank_already_used"),
])
def test_original_period_guard_returns_typed_conflict_without_saving_or_committing(failure, code):
    period = SubsidyPeriod("quarter", 2026, 1)
    client, connection, port = client_for(period, failure)
    with client:
        response = client.post("/api/v1/government-subsidy/periods/reconcile", json=command(period, 1 if failure == "stale" else 2))
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == code
    assert port.saved == [] and port.receipts == {}
    assert connection.events == ["begin", "rollback"]


def test_current_public_period_body_does_not_accept_an_invented_manual_bank_source():
    period = SubsidyPeriod("quarter", 2026, 1)
    client, connection, port = client_for(period)
    body = command(period)
    del body["bank_row_id"]
    body.update(amount_ntd=1000, transaction_date="2026-11-06", source_kind="manual_supplement")
    with client:
        response = client.post("/api/v1/government-subsidy/periods/reconcile", json=body)
    assert response.status_code == 422 and connection.events == [] and port.events == []
