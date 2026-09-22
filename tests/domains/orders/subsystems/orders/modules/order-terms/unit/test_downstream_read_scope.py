"""Issue #336: preassignment Terms reads only the downstream integrity boundary."""

from infrastructure.mysql import order_terms_read_model


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
        lambda *_: calls.append("downstream_integrity"),
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
