from decimal import Decimal

import pytest

from services import finance_import_application as importer
from subsystems.finance_import import reconciliation_dispatch as dispatcher


class Cursor:
    rowcount = 1

    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))


class Connection:
    def __init__(self, cursor=None):
        self._cursor = cursor or Cursor()
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


def test_pipeline_dispatches_only_inserted_rows_and_completes_batch(monkeypatch):
    connection = Connection()
    dispatched = []
    normalized = {"format_id": "sinopac", "normalized_rows": [{}]}
    staged = {
        "batch_id": 41,
        "staged_rows": [
            {
                "row_id": 10,
                "classification_type": "client_receipt",
                "result": "inserted",
            },
            {
                "row_id": 11,
                "classification_type": "client_receipt",
                "result": "skipped_existing",
            },
            {
                "row_id": 12,
                "classification_type": "non_business_review",
                "result": "inserted",
            },
        ],
    }
    monkeypatch.setattr(importer, "normalize_workbook", lambda path: normalized)
    monkeypatch.setattr(importer, "get_connection", lambda: connection)
    monkeypatch.setattr(importer, "load_finance_identity_maps", lambda cursor: {"staff_accounts": {}})
    monkeypatch.setattr(importer, "stage_finance_rows", lambda cursor, result, maps: staged)

    def dispatch(cursor, row_id, batch_id):
        assert batch_id == 41
        dispatched.append(row_id)
        return {
            "classification_type": (
                "client_receipt" if row_id == 10 else "non_business_review"
            ),
            "result": "reconciled" if row_id == 10 else "pending",
            "reason": None,
            "formal_references": {},
            "finance_alert_action": None,
        }

    monkeypatch.setattr(importer, "dispatch_finance_import_row", dispatch)
    monkeypatch.setattr(
        importer,
        "project_finance_import_review_alert",
        lambda cursor, batch_id: None,
    )

    result = importer.import_finance_workbook("renamed.xlsx")

    assert dispatched == [10, 12]
    assert result == {
        "mode": "apply",
        "source_path": str(importer.os.path.abspath("renamed.xlsx")),
        "format_manifest": {
            "format_id": "sinopac",
            "sheet_name": None,
            "header_row": None,
            "normalized_row_count": 1,
        },
        "batch_id": 41,
        "inserted_rows": 2,
        "skipped_existing": 1,
        "reconciled_counts": {"client_receipt": 1},
        "pending_rows": [12],
        "row_results": [
            {
                "dedup_fingerprint": None,
                "classification_type": "client_receipt",
                "staging_result": "inserted",
                "dispatch_result": "reconciled",
                "reason": None,
                "finance_alert_action": None,
            },
            {
                "dedup_fingerprint": None,
                "classification_type": "client_receipt",
                "staging_result": "skipped_existing",
                "dispatch_result": None,
                "reason": None,
                "finance_alert_action": None,
            },
            {
                "dedup_fingerprint": None,
                "classification_type": "non_business_review",
                "staging_result": "inserted",
                "dispatch_result": "pending",
                "reason": None,
                "finance_alert_action": None,
            },
        ],
        "alert_action": None,
        "transaction_outcome": "committed",
    }
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.closes == 1
    assert any("SET status='completed'" in sql for sql, _ in connection._cursor.executed)


def test_downstream_error_rolls_back_entire_batch(monkeypatch):
    connection = Connection()
    monkeypatch.setattr(importer, "normalize_workbook", lambda path: {"normalized_rows": []})
    monkeypatch.setattr(importer, "get_connection", lambda: connection)
    monkeypatch.setattr(importer, "load_finance_identity_maps", lambda cursor: {})
    monkeypatch.setattr(
        importer,
        "stage_finance_rows",
        lambda cursor, result, maps: {
            "batch_id": 42,
            "staged_rows": [
                {"row_id": 20, "classification_type": "government_subsidy", "result": "inserted"}
            ],
        },
    )
    monkeypatch.setattr(
        importer,
        "dispatch_finance_import_row",
        lambda cursor, row_id, batch_id: (_ for _ in ()).throw(
            RuntimeError("downstream failed")
        ),
    )

    with pytest.raises(RuntimeError, match="downstream failed"):
        importer.import_finance_workbook("input.xlsx")

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closes == 1
    assert not any("status='completed'" in sql for sql, _ in connection._cursor.executed)


class ResultCursor(Cursor):
    def __init__(self, results):
        super().__init__()
        self.results = iter(results)

    def fetchall(self):
        return next(self.results)


def _detail(detail_id, **changes):
    row = {
        "settlement_detail_id": detail_id,
        "service_salary": Decimal("1000"),
        "legacy_subsidy_payable": Decimal("0"),
        "floor_fee_amount": Decimal("200"),
        "adjustment_amount": Decimal("0"),
        "legacy_subsidy_status": "not_applicable",
        "review_required": 0,
    }
    row.update(changes)
    return row


def test_staff_plan_requires_one_complete_exact_settlement():
    cursor = ResultCursor(
        [
            [{"id": 7, "staff_id": 3}],
            [_detail(71), _detail(72, service_salary=Decimal("500"), floor_fee_amount=0)],
            [
                {
                    "settlement_detail_id": 71,
                    "component_type": "regular_salary",
                    "allocated_amount": Decimal("300"),
                    "transaction_type": "transfer",
                }
            ],
        ]
    )

    plans = dispatcher._staff_transfer_candidates(
        cursor,
        {
            "classification_type": "staff_salary",
            "matched_identity_ids": "[3]",
            "debit": Decimal("1400"),
        },
    )

    assert len(plans) == 1
    assert plans[0]["settlement_id"] == 7
    assert plans[0]["payment_phase"] == "normal"
    assert sum(
        (item["allocated_amount"] for item in plans[0]["allocations"]),
        Decimal("0"),
    ) == Decimal("1400")
    assert all(item["allocation_method"] == "explicit" for item in plans[0]["allocations"])


def test_staff_plan_keeps_ambiguous_same_amount_settlements_pending(monkeypatch):
    cursor = ResultCursor(
        [
            [{"id": 7, "staff_id": 3}, {"id": 8, "staff_id": 3}],
            [_detail(71, floor_fee_amount=0)],
            [],
            [_detail(81, floor_fee_amount=0)],
            [],
        ]
    )
    row = {
        "id": 30,
        "classification_type": "staff_salary",
        "matched_identity_ids": [3],
        "debit": Decimal("1000"),
    }
    monkeypatch.setattr(dispatcher, "_dispatch_row", lambda cursor, row_id: row)
    called = []
    monkeypatch.setattr(
        dispatcher,
        "reconcile_staff_actual_transfer",
        lambda *args: called.append(args),
    )
    monkeypatch.setattr(dispatcher, "maybe_alert_pending", lambda *args, **kwargs: None)

    result = dispatcher.dispatch_finance_import_row(cursor, 30, 41)

    assert result == {
        "classification_type": "staff_salary",
        "result": "pending",
        "reason": "staff_transfer_plan_not_unique",
        "formal_references": {},
        "finance_alert_action": None,
    }
    assert called == []


def test_non_business_dispatch_preserves_classifier_reason(monkeypatch):
    monkeypatch.setattr(
        dispatcher,
        "_dispatch_row",
        lambda cursor, row_id: {
            "id": row_id,
            "classification_type": "non_business_review",
            "classification_reason": "sinopac_staff_account_no_match",
        },
    )

    result = dispatcher.dispatch_finance_import_row(Cursor(), 31, 41)

    assert result == {
        "classification_type": "non_business_review",
        "result": "pending",
        "reason": "sinopac_staff_account_no_match",
        "formal_references": {},
        "finance_alert_action": None,
    }


def test_second_subsidy_requires_confirmed_full_legacy_component():
    cursor = ResultCursor(
        [
            [{"id": 9, "staff_id": 4}],
            [
                _detail(
                    91,
                    service_salary=0,
                    floor_fee_amount=0,
                    legacy_subsidy_payable=Decimal("600"),
                    legacy_subsidy_status="confirmed",
                )
            ],
            [],
        ]
    )

    plans = dispatcher._staff_transfer_candidates(
        cursor,
        {
            "classification_type": "staff_legacy_subsidy",
            "matched_identity_ids": [4],
            "debit": Decimal("600"),
        },
    )

    assert plans == [
        {
            "settlement_id": 9,
            "payment_phase": "second_subsidy",
            "allocations": [
                {
                    "settlement_detail_id": 91,
                    "component_type": "legacy_subsidy",
                    "allocated_amount": Decimal("600"),
                    "allocation_method": "explicit",
                }
            ],
        }
    ]
