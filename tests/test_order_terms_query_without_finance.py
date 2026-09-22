"""Issue #336 Query boundary; the strict mutation readers are unchanged."""
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from infrastructure.mysql import order_terms_read_model as reader
from api.schemas.order_terms import OrderTermsQueryView


TERMS = {
    "planned_start_date": "2026-09-22", "service_days": 2,
    "service_hours_per_day": 4.5, "requires_cooking": None,
    "floor_fee_ntd": 0,
    "service_time": {"start_time": None, "end_time": None, "end_day_offset": None},
}


class VersionCursor:
    def __init__(self, finance=None, payroll=None):
        self.row = {"client_finance_version": finance, "payroll_version": payroll}
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        # This test cursor serves only the two account-version scalar reads.
        assert sql == (
            "SELECT (SELECT aggregate_version FROM client_finance_accounts "
            "WHERE case_no=%s) AS client_finance_version,"
            "(SELECT aggregate_version FROM payroll_case_accounts "
            "WHERE case_no=%s) AS payroll_version"
        )
        assert params == ("case-336", "case-336")

    def fetchone(self):
        return self.row


@pytest.fixture
def query_roots(monkeypatch):
    calls = []
    order_row = {"case_no": "case-336"}
    order = SimpleNamespace(
        case_no="case-336", version=3, service_data_locked=False,
        terms=SimpleNamespace(canonical_payload=lambda: dict(TERMS)),
    )
    aggregate = {"aggregate_version": 0}

    def order_read(cursor, case_no, *, lock):
        assert case_no == "case-336" and lock is False
        calls.append("orders")
        return order_row

    def scheduling_read(cursor, case_no, *, lock):
        assert case_no == "case-336" and lock is False
        calls.append("scheduling")
        return aggregate

    monkeypatch.setattr(reader, "select_order", order_read)
    monkeypatch.setattr(reader, "_order_facts", lambda row: order)
    monkeypatch.setattr(reader, "select_scheduling_aggregate", scheduling_read)
    monkeypatch.setattr(reader, "_select_generation", lambda cursor, agg, lock: None)
    monkeypatch.setattr(reader, "_select_assignments", lambda cursor, gen, lock: ())
    monkeypatch.setattr(reader, "_select_schedules", lambda cursor, gen, lock: ())
    monkeypatch.setattr(reader, "_service_dates_by_assignment", lambda rows: {})
    monkeypatch.setattr(reader, "_segments", lambda rows, dates: ())
    monkeypatch.setattr(reader, "_select_confirmed_service_dates", lambda cursor, case, lock: (None, ()))

    def forbidden(*args, **kwargs):
        pytest.fail("Query must not load impact or lifecycle facts")

    for name in ("_load_client_finance", "_load_payroll", "_load_lifecycle", "_assemble_facts"):
        monkeypatch.setattr(reader, name, forbidden)
    return order, aggregate, calls


@pytest.mark.parametrize("finance,payroll", [(None, None), (0, None), (None, 0), (7, 11)])
def test_query_preserves_absent_and_existing_account_versions(query_roots, finance, payroll):
    cursor = VersionCursor(finance, payroll)
    result = reader.load_query_facts(cursor, "case-336")
    decoded = OrderTermsQueryView.model_validate(result)
    assert decoded.client_finance_version == finance
    assert decoded.payroll_version == payroll
    assert decoded.terms.service_time.start_time is None
    assert decoded.terms.service_hours_per_day == 4.5
    assert decoded.terms.requires_cooking is None
    assert decoded.assignments == []
    assert decoded.confirmed_service_dates == []
    assert query_roots[2] == ["orders", "scheduling"]
    assert len(cursor.calls) == 1


def test_existing_assignment_and_confirmed_dates_are_retained(query_roots, monkeypatch):
    query_roots[1]["aggregate_version"] = 6
    monkeypatch.setattr(reader, "_select_generation", lambda *args: {"generation_number": 4})
    monkeypatch.setattr(reader, "_segments", lambda *args: (
        SimpleNamespace(assignment_id=12, staff_id=9, service_day_count=2),
    ))
    dates = (date(2026, 9, 22), date(2026, 9, 24))
    monkeypatch.setattr(reader, "_select_confirmed_service_dates", lambda *args: (8, dates))
    result = reader.load_query_facts(VersionCursor(5, 9), "case-336")
    assert result["scheduling_version"] == 6
    assert result["scheduling_generation"] == 4
    assert result["confirmed_service_date_version"] == 8
    assert result["confirmed_service_dates"] == list(dates)
    assert result["assignments"] == [{"assignment_id": 12, "staff_id": 9, "service_days": 2}]


@pytest.mark.parametrize("helper,code", [
    ("select_order", "order_not_found"),
    ("_select_generation", "scheduling_effective_generation_invalid"),
    ("_segments", "assignment_service_days_required"),
])
def test_root_errors_are_not_converted_to_empty_results(query_roots, monkeypatch, helper, code):
    def fail(*args, **kwargs):
        raise ValueError(code)
    monkeypatch.setattr(reader, helper, fail)
    cursor = VersionCursor()
    with pytest.raises(ValueError, match=code):
        reader.load_query_facts(cursor, "case-336")
    assert cursor.calls == []


def test_version_read_error_is_not_converted_to_no_account(query_roots):
    class FailedCursor(VersionCursor):
        def execute(self, *args):
            raise RuntimeError("connection_failed")
    with pytest.raises(RuntimeError, match="connection_failed"):
        reader.load_query_facts(FailedCursor(), "case-336")


@pytest.mark.parametrize("field", ["client_finance_version", "payroll_version"])
def test_query_contract_requires_explicit_version_or_null(query_roots, field):
    result = reader.load_query_facts(VersionCursor(), "case-336")
    del result[field]
    with pytest.raises(ValidationError):
        OrderTermsQueryView.model_validate(result)


@pytest.mark.parametrize("field", ["client_finance_version", "payroll_version"])
def test_query_contract_rejects_negative_versions(query_roots, field):
    result = reader.load_query_facts(VersionCursor(), "case-336")
    result[field] = -1
    with pytest.raises(ValidationError):
        OrderTermsQueryView.model_validate(result)


def test_query_reports_existing_service_lock_without_financial_roots(query_roots):
    query_roots[0].service_data_locked = True
    result = reader.load_query_facts(VersionCursor(), "case-336")
    assert result["service_data_locked"] is True
