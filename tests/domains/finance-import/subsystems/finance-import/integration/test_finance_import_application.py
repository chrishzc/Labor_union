from decimal import Decimal

import pytest

from subsystems.finance_import import application


def test_allocate_receipt_uses_ordered_payment_stages() -> None:
    allocations = application.allocate_receipt(
        {"deposit": 100, "first_payment": 200, "second_payment": 300},
        {"deposit_received": 50, "first_payment_received": 200, "second_payment_received": 0},
        "350",
    )

    assert allocations == [("deposit", Decimal("50")), ("second_payment", Decimal("300"))]


def test_allocate_receipt_rejects_excess_amount() -> None:
    with pytest.raises(ValueError, match="receipt exceeds"):
        application.allocate_receipt(
            {"deposit": 10, "first_payment": 0, "second_payment": 0},
            {"deposit_received": 0, "first_payment_received": 0, "second_payment_received": 0},
            11,
        )


def test_snapshot_plan_prefers_actual_start_and_requires_deposit_terms(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        application,
        "calculate_order_amounts",
        lambda terms, *, collection_schedule: captured.update(
            terms=terms, collection_schedule=collection_schedule
        )
        or {"planned": True},
    )

    result = application.build_snapshot_plan(
        {
            "case_no": "CASE-1",
            "deposit_service_days": 3,
            "deposit_date": "2026-08-01",
            "start_date": "2026-08-03",
            "actual_start_date": "2026-08-04",
            "service_days": 26,
            "service_hours_per_day": 8,
            "identity_status": "local",
            "floor_fee": 100,
        }
    )

    assert result == {"planned": True}
    assert captured["terms"]["service_start_date"] == "2026-08-04"
    assert captured["collection_schedule"] == {
        "deposit_service_days": 3,
        "deposit_due_date": "2026-08-01",
    }
    assert application.build_snapshot_plan({"deposit_service_days": None}) is None


def test_diagnostic_apply_is_rejected() -> None:
    with pytest.raises(ValueError, match="finance_import_diagnostic_is_dry_run_only"):
        application.import_finance_workbook(
            "input.xlsx", connection_factory=lambda: None,
            normalizer=lambda _path: {},
        )


def test_dry_run_rolls_back_and_keeps_batch_id_private(monkeypatch) -> None:
    class Cursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args):
            return None

    class Connection:
        def __init__(self):
            self.rollbacks = 0
            self.closed = False

        def cursor(self):
            return Cursor()

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(application, "load_finance_identity_maps", lambda _cursor: {})
    monkeypatch.setattr(
        application,
        "stage_finance_rows",
        lambda *_args: {"batch_id": 7, "staged_rows": [{"row_id": 4, "classification_type": "client_receipt", "result": "inserted"}]},
    )
    monkeypatch.setattr(
        application,
        "dispatch_finance_import_row",
        lambda *_args: {"result": "reconciled"},
    )
    manifest = application.import_finance_workbook(
        "input.xlsx", dry_run=True, connection_factory=lambda: connection,
        normalizer=lambda _path: {
            "format_id": "sinopac",
            "sheet_name": "sheet",
            "header_row": 1,
            "normalized_rows": [{}],
        },
    )

    assert manifest["batch_id"] is None
    assert manifest["transaction_outcome"] == "rolled_back"
    assert manifest["reconciled_counts"] == {"client_receipt": 1}
    assert connection.rollbacks == 1
    assert connection.closed
