from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from infrastructure.mysql.order_terms_read_model import (
    _historical_precision_restarted,
    lock_staff_mutexes,
    _select_payroll_assignment_ancestry,
)


def test_empty_impacted_staff_set_requires_no_mutex_query():
    cursor = SimpleNamespace(execute=lambda *_args: pytest.fail("unexpected SQL"))

    lock_staff_mutexes(cursor, ())


class _RestartCursor:
    def __init__(self, row):
        self.row = row
        self.statement = None
        self.parameters = None

    def execute(self, statement, parameters):
        self.statement = " ".join(statement.split())
        self.parameters = parameters

    def fetchone(self):
        return self.row


def test_historical_precision_restart_provenance_uses_the_immutable_lifecycle_event():
    cursor = _RestartCursor({"id": 17})

    assert _historical_precision_restarted(cursor, "CASE-HISTORY", lock=True) is True
    assert "trigger_event='orders_historical_precision_restart'" in cursor.statement
    assert "ORDER BY id DESC LIMIT 1 FOR UPDATE" in cursor.statement
    assert cursor.parameters == ("CASE-HISTORY", "訂單成立")


def test_missing_historical_precision_restart_event_does_not_enable_the_exception():
    cursor = _RestartCursor(None)

    assert _historical_precision_restarted(cursor, "CASE-NORMAL", lock=False) is False


def test_payment_family_ancestry_stops_at_a_different_caregiver_so_returning_staff_do_not_inherit_old_adjustments():
    class Cursor:
        def execute(self, _sql, _params):
            pass

        def fetchall(self):
            return (
                {"new_assignment_id": 2, "old_assignment_identity": "assignment:1", "old_staff_id": 7},
                {"new_assignment_id": 3, "old_assignment_identity": "assignment:2", "old_staff_id": 7},
                {"new_assignment_id": 4, "old_assignment_identity": "assignment:2", "old_staff_id": 7},
                {"new_assignment_id": 5, "old_assignment_identity": "assignment:4", "old_staff_id": 8},
            )

    result = _select_payroll_assignment_ancestry(Cursor(), "CASE", (
        {"id": 3, "staff_id": 7}, {"id": 4, "staff_id": 8}, {"id": 5, "staff_id": 7}), False)
    assert result == {3: (1, 2), 4: (), 5: ()}


def test_payment_family_rejects_cycles_without_treating_database_identity_order_as_business_history():
    class Cursor:
        def execute(self, _sql, _params):
            pass

        def fetchall(self):
            return self.rows

    cursor = Cursor()
    cursor.rows = ({"new_assignment_id": 3, "old_assignment_identity": "assignment:20", "old_staff_id": 7},)
    assert _select_payroll_assignment_ancestry(cursor, "CASE", ({"id": 3, "staff_id": 7},), False) == {3: (20,)}
    cursor.rows += ({"new_assignment_id": 20, "old_assignment_identity": "assignment:3", "old_staff_id": 7},)
    with pytest.raises(ValueError, match="payroll_assignment_lineage_invalid"):
        _select_payroll_assignment_ancestry(cursor, "CASE", ({"id": 3, "staff_id": 7},), False)


def test_payment_history_uses_canonical_links_even_when_cached_flag_is_not_set_or_net_payment_was_fully_returned():
    from infrastructure.mysql.order_terms_read_model import _STAFF_OBLIGATIONS_SQL
    from infrastructure.mysql.payroll_rebuild_repository import _EXISTING_OBLIGATION_SELECT_SQL

    for query in (_STAFF_OBLIGATIONS_SQL, _EXISTING_OBLIGATION_SELECT_SQL):
        assert "OR EXISTS(SELECT 1 FROM staff_payout_obligation_links history" in query
        assert ")) AS payout_history_exists" in query


@pytest.fixture
def calculable_finance_reader(monkeypatch):
    from domains.client_finance.obligation_planning import (
        ClientFinanceTermsSourceFacts, ClientPaymentTerms,
    )
    from infrastructure.mysql import order_terms_read_model as reader
    from shared_kernel.money import MoneyNTD

    cursor = SimpleNamespace(execute=lambda *_: pytest.fail("unexpected SQL"))
    order = {
        "case_no": "SYNTH-INCOMPLETE", "start_date": date(2026, 10, 1),
        "service_days": 10, "service_hours_per_day": 8, "floor_fee": 500,
    }
    source = ClientFinanceTermsSourceFacts(
        case_no=order["case_no"], account_version=4,
        payment_terms=ClientPaymentTerms(
            5, MoneyNTD(300), date(2026, 9, 20), date(2026, 10, 1), None,
        ),
        double_pay_dates=(), existing_obligations=(),
    )
    monkeypatch.setattr(reader, "select_scheduling_aggregate", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(reader, "_select_generation", lambda *_: None)
    monkeypatch.setattr(reader, "_select_schedules", lambda *_: ())
    monkeypatch.setattr(reader, "_committed_charge_days", lambda *_: ())
    monkeypatch.setattr(reader, "_select_confirmed_service_dates", lambda *_: (None, ()))
    monkeypatch.setattr(reader, "_load_client_finance", lambda *_: source)
    return reader, cursor, order, source


@pytest.mark.parametrize("start,days,code", [
    (None, 10, "order_terms_start_date_required"),
    (date(2026, 10, 1), None, "order_terms_service_days_required"),
    (None, None, "order_terms_start_date_required"),
])
def test_calculable_finance_missing_planned_inputs_remain_not_ready(
    calculable_finance_reader, monkeypatch, start, days, code,
):
    reader, cursor, order, _ = calculable_finance_reader
    order.update(start_date=start, service_days=days)
    saved = dict(order)
    monkeypatch.setattr(reader, "_load_client_finance", lambda *_: pytest.fail("incomplete facts must not be priced"))

    with pytest.raises(ValueError, match=f"^{code}$"):
        reader.load_calculable_client_finance_facts(cursor, order, lock=False)

    assert order == saved


@pytest.mark.parametrize("origin,allow_planned", [
    ("schedule", True), ("schedule", False), ("commitment", True), ("confirmed", True),
])
def test_calculable_finance_official_days_precede_missing_planned_inputs(
    calculable_finance_reader, monkeypatch, origin, allow_planned,
):
    from domains.client_finance.obligation_planning import ClientChargeDay

    reader, cursor, order, source = calculable_finance_reader
    order.update(start_date=None, service_days=None)
    actual_day = date(2026, 10, 3)
    if origin == "schedule":
        monkeypatch.setattr(reader, "_select_schedules", lambda *_: (
            {"work_date": actual_day, "is_work_day": True, "is_double_pay": True},
        ))
        monkeypatch.setattr(reader, "_committed_charge_days", lambda *_: pytest.fail("schedule must take priority"))
    elif origin == "commitment":
        monkeypatch.setattr(reader, "_committed_charge_days", lambda *_: (ClientChargeDay(actual_day, False),))
    else:
        monkeypatch.setattr(reader, "_select_confirmed_service_dates", lambda *_: (3, (actual_day,)))
    if origin != "confirmed":
        monkeypatch.setattr(reader, "_select_confirmed_service_dates", lambda *_: pytest.fail("official days must take priority"))

    facts, returned_source = reader.load_calculable_client_finance_facts(
        cursor, order, lock=False, allow_planned=allow_planned,
    )

    assert facts.charge_days == (ClientChargeDay(actual_day, origin == "schedule"),)
    assert facts.payment_terms is source.payment_terms
    assert returned_source is source


def test_calculable_finance_valid_planned_days_keep_owner_pricing(calculable_finance_reader):
    from domains.client_finance.obligation_planning import build_client_finance_terms_candidate

    reader, cursor, order, source = calculable_finance_reader

    facts, returned_source = reader.load_calculable_client_finance_facts(cursor, order, lock=False)
    candidate = build_client_finance_terms_candidate(facts, "synthetic-read-only")

    assert tuple(day.service_date for day in facts.charge_days) == tuple(
        date(2026, 10, 1) + timedelta(days=offset) for offset in range(10)
    )
    assert sum(stage.amount.amount for stage in candidate.stage_plans) == 24500
    assert returned_source is source


@pytest.mark.parametrize("planned_available", [True, False])
def test_calculable_finance_disallowed_planned_fallback_still_returns_no_facts(
    calculable_finance_reader, monkeypatch, planned_available,
):
    reader, cursor, order, _ = calculable_finance_reader
    if not planned_available:
        order.update(start_date=None, service_days=None)
    for name in ("_committed_charge_days", "_select_confirmed_service_dates", "_load_client_finance"):
        monkeypatch.setattr(reader, name, lambda *_: pytest.fail("planned fallback is disabled"))

    assert reader.load_calculable_client_finance_facts(cursor, order, lock=False, allow_planned=False) == (None, None)


@pytest.mark.parametrize("field,value,error", [
    ("service_days", "not-a-count", ValueError),
    ("start_date", "not-a-date", TypeError),
])
def test_calculable_finance_invalid_nonmissing_inputs_are_not_hidden(
    calculable_finance_reader, field, value, error,
):
    reader, cursor, order, _ = calculable_finance_reader
    order[field] = value

    with pytest.raises(error):
        reader.load_calculable_client_finance_facts(cursor, order, lock=False)
