"""Issue #336: preassignment Terms reads only the downstream integrity boundary."""

from infrastructure.mysql import order_terms_read_model
import pytest


def test_preassignment_terms_reader_omits_full_finance_and_payroll(monkeypatch):
    calls = []
    lifecycle = object()

    monkeypatch.setattr(order_terms_read_model, "_select_generation", lambda *_: None)
    monkeypatch.setattr(order_terms_read_model, "_select_assignments", lambda *_: ())
    monkeypatch.setattr(order_terms_read_model, "_select_schedules", lambda *_: ())
    monkeypatch.setattr(
        order_terms_read_model,
        "_select_confirmed_service_dates",
        lambda *_: (None, ()),
    )
    monkeypatch.setattr(
        order_terms_read_model,
        "_validate_preassignment_downstream_state",
        lambda *_, **_kwargs: calls.append("downstream_integrity"),
    )
    monkeypatch.setattr(order_terms_read_model, "_load_lifecycle", lambda *_: lifecycle)
    monkeypatch.setattr(
        order_terms_read_model,
        "_load_client_finance",
        lambda *_: (_ for _ in ()).throw(AssertionError("full Client Finance read")),
    )
    monkeypatch.setattr(
        order_terms_read_model,
        "_load_payroll",
        lambda *_: (_ for _ in ()).throw(AssertionError("full Payroll read")),
    )
    monkeypatch.setattr(
        order_terms_read_model,
        "_facts_from_rows",
        lambda *values: values,
    )

    result = order_terms_read_model._assemble_facts(
        object(),
        {"case_no": "CASE-336"},
        {"aggregate_version": 0},
        lock=False,
        omit_preassignment_downstream=True,
    )

    assert calls == ["downstream_integrity"]
    assert result[5] is None
    assert result[6] is None
    assert result[7] is lifecycle


@pytest.mark.parametrize("lock", [False, True])
@pytest.mark.parametrize("allow,finance_present,staff_obligation,expected_error", [
    (False, True, False, "preassignment_client_finance_obligation_conflict"),
    (True, False, False, "preassignment_client_finance_obligation_conflict"),
    (True, True, True, "preassignment_payroll_obligation_conflict"),
    (True, True, False, None),
])
def test_existing_client_obligations_are_readable_only_for_scoped_payment_recalculation(
    lock, allow, finance_present, staff_obligation, expected_error,
):
    presence = {
        "client_finance_accounts": finance_present,
        "client_payment_terms": finance_present,
        "client_obligations": True,
        "payroll_case_accounts": True,
        "case_payroll_rate_policy_snapshots": True,
        "staff_obligations": staff_obligation,
    }
    class Cursor:
        def execute(self, sql, parameters):
            assert sql.startswith("SELECT ")
            assert ("FOR UPDATE" in sql) is lock
            assert parameters == ("CASE-EXISTING",)
            self.exists = presence[next(table for table in presence if f"FROM {table} " in sql)]
        def fetchone(self):
            return {} if self.exists else None
    if expected_error:
        with pytest.raises(ValueError, match=expected_error):
            order_terms_read_model._validate_preassignment_downstream_state(
                Cursor(), "CASE-EXISTING", lock, allow_client_obligations=allow,
            )
    else:
        assert order_terms_read_model._validate_preassignment_downstream_state(
            Cursor(), "CASE-EXISTING", lock, allow_client_obligations=allow,
        ) is True


def test_assigned_terms_reader_keeps_full_downstream_facts(monkeypatch):
    finance = object()
    payroll = object()
    lifecycle = object()

    monkeypatch.setattr(order_terms_read_model, "_select_generation", lambda *_: object())
    monkeypatch.setattr(order_terms_read_model, "_select_assignments", lambda *_: ({"id": 1},))
    monkeypatch.setattr(order_terms_read_model, "_select_schedules", lambda *_: ())
    monkeypatch.setattr(
        order_terms_read_model,
        "_select_confirmed_service_dates",
        lambda *_: (None, ()),
    )
    monkeypatch.setattr(order_terms_read_model, "_load_client_finance", lambda *_: finance)
    monkeypatch.setattr(order_terms_read_model, "_load_payroll", lambda *_: payroll)
    monkeypatch.setattr(order_terms_read_model, "_load_lifecycle", lambda *_: lifecycle)
    monkeypatch.setattr(order_terms_read_model, "_facts_from_rows", lambda *values: values)

    result = order_terms_read_model._assemble_facts(
        object(),
        {"case_no": "CASE-336"},
        {"aggregate_version": 1},
        lock=False,
        omit_preassignment_downstream=True,
    )

    assert result[5] is finance
    assert result[6] is payroll
    assert result[7] is lifecycle
