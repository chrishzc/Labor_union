from decimal import Decimal

import pytest

from services import client_receipt_reconciliation as service


FINGERPRINT = "a" * 64
VIRTUAL_ACCOUNT = "99781699115001"
CASE_NO = "115000001"


def staged(**changes):
    value = {
        "id": 31,
        "format_id": "sinopac",
        "dedup_fingerprint": FINGERPRINT,
        "direction": "incoming",
        "credit": Decimal("1500"),
        "classification_type": "client_receipt",
        "reconciliation_status": "pending",
        "reconciliation_reference": None,
        "transaction_date": "2026-07-14",
        "bank_references": {"銷帳編號": VIRTUAL_ACCOUNT, "更正註記": "WRONG"},
    }
    value.update(changes)
    return value


def order(**changes):
    value = {
        "case_no": CASE_NO,
        "status": "洽談中",
        "service_days": 20,
        "service_hours_per_day": 9,
        "subsidy_eligibility": "一般市民",
        "floor_fee": Decimal("0"),
        "deposit_date": "2026-07-01",
        "deposit_service_days": 5,
        "start_date": "2026-07-15",
        "actual_start_date": None,
        "actual_end_date": None,
    }
    value.update(changes)
    return value


def payment(**changes):
    value = {
        "id": 9,
        "case_no": CASE_NO,
        "deposit_receivable": Decimal("1000"),
        "deposit_received": Decimal("0"),
        "first_payment_receivable": Decimal("1000"),
        "first_payment_received": Decimal("0"),
        "second_payment_receivable": Decimal("500"),
        "second_payment_received": Decimal("0"),
    }
    value.update(changes)
    return value


class Cursor:
    def __init__(self, *, staging=None, order_row=None, existing=None, payment_row=None):
        self.staging = staging if staging is not None else staged()
        self.order_row = order_row if order_row is not None else order()
        self.existing = list(existing or [])
        self.payment_row = payment_row if payment_row is not None else payment()
        self.current = None
        self.executed = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.executed.append((compact, params))
        if "FROM finance_import_rows WHERE id" in compact:
            self.current = self.staging
        elif "FROM orders WHERE case_no" in compact and "SELECT case_no, status" in compact:
            self.current = self.order_row
        elif "WHERE finance_import_row_id = %s" in compact:
            self.current = self.existing
        elif "FROM client_payments WHERE id" in compact:
            self.current = self.payment_row
        else:
            self.current = None

    def fetchone(self):
        return self.current

    def fetchall(self):
        return list(self.current or [])


def dependencies(monkeypatch, *, snapshot_result=None, resolver_result=None):
    calls = {"resolver": [], "snapshot": [], "writer": []}

    def resolver(cursor, cancellation_code):
        calls["resolver"].append(cancellation_code)
        return resolver_result or {"result": "resolved", "case_no": CASE_NO, "reason": None}

    def snapshot(cursor, order_terms, schedule):
        calls["snapshot"].append((order_terms, schedule))
        return snapshot_result or {"result": "existing", "payment_id": 9, "plan": {}}

    def writer(cursor, payment_id, transaction):
        calls["writer"].append((payment_id, transaction))
        return {"transaction_id": 700 + len(calls["writer"])}

    monkeypatch.setattr(service, "resolve_client_virtual_account", resolver)
    monkeypatch.setattr(service, "create_client_payment_snapshot", snapshot)
    monkeypatch.setattr(service, "record_client_payment_transaction_with_cursor", writer)
    return calls


def test_reconciles_cross_stage_receipt_with_fixed_references_and_shared_bank_row(monkeypatch):
    cursor = Cursor()
    calls = dependencies(monkeypatch)

    result = service.reconcile_client_receipt(cursor, 31)

    assert result == {
        "result": "reconciled",
        "transaction_ids": [701, 702],
        "client_payment_id": 9,
        "case_no": CASE_NO,
    }
    assert calls["resolver"] == [VIRTUAL_ACCOUNT]
    assert [item[1]["stage"] for item in calls["writer"]] == ["deposit", "first_payment"]
    assert [item[1]["amount"] for item in calls["writer"]] == [Decimal("1000"), Decimal("500")]
    assert [item[1]["external_reference"] for item in calls["writer"]] == [
        f"fp:{FINGERPRINT}:deposit",
        f"fp:{FINGERPRINT}:first_payment",
    ]
    assert all(item[1]["finance_import_row_id"] == 31 for item in calls["writer"])
    assert any(sql.startswith("UPDATE finance_import_rows") for sql, _ in cursor.executed)


def test_only_original_cancellation_code_is_passed_to_resolver(monkeypatch):
    cursor = Cursor(staging=staged(bank_references='{"銷帳編號":"99781699115001","更正註記":"99781699115999"}'))
    calls = dependencies(monkeypatch)

    service.reconcile_client_receipt(cursor, 31)

    assert calls["resolver"] == [VIRTUAL_ACCOUNT]


def test_overpayment_rolls_back_new_snapshot_and_creates_no_formal_transaction(monkeypatch):
    cursor = Cursor(staging=staged(credit=Decimal("2501")))
    calls = dependencies(monkeypatch, snapshot_result={"result": "created", "payment_id": 9, "plan": {}})

    result = service.reconcile_client_receipt(cursor, 31)

    assert result["result"] == "pending"
    assert result["reason"] == "receipt_exceeds_remaining_receivable"
    assert calls["writer"] == []
    assert any(sql.startswith("ROLLBACK TO SAVEPOINT") for sql, _ in cursor.executed)
    assert not any(sql.startswith("UPDATE finance_import_rows") for sql, _ in cursor.executed)


def test_missing_snapshot_terms_remain_pending_without_formal_transaction(monkeypatch):
    cursor = Cursor(order_row=order(deposit_service_days=None))
    calls = dependencies(
        monkeypatch,
        snapshot_result={
            "result": "review_required",
            "payment_id": None,
            "plan": None,
            "reason": "deposit_service_days_missing",
        },
    )

    result = service.reconcile_client_receipt(cursor, 31)

    assert result["result"] == "pending"
    assert result["reason"] == "deposit_service_days_missing"
    assert calls["writer"] == []
    assert any(sql.startswith("ROLLBACK TO SAVEPOINT") for sql, _ in cursor.executed)
    assert not any(sql.startswith("UPDATE finance_import_rows") for sql, _ in cursor.executed)


def existing_row(**changes):
    value = {
        "id": 701,
        "client_payment_id": 9,
        "case_no": CASE_NO,
        "stage": "deposit",
        "transaction_type": "receipt",
        "transaction_status": "succeeded",
        "amount": Decimal("1000"),
        "occurred_at": "2026-07-14",
        "external_reference": f"fp:{FINGERPRINT}:deposit",
        "finance_import_row_id": 31,
    }
    value.update(changes)
    return value


def test_exact_retry_returns_existing_without_snapshot_writer_or_updates(monkeypatch):
    rows = [
        existing_row(),
        existing_row(
            id=702,
            stage="first_payment",
            amount=Decimal("500"),
            external_reference=f"fp:{FINGERPRINT}:first_payment",
        ),
    ]
    cursor = Cursor(
        staging=staged(reconciliation_status="reconciled", reconciliation_reference=f"fp:{FINGERPRINT}"),
        existing=rows,
        payment_row=payment(deposit_received=Decimal("1000"), first_payment_received=Decimal("500")),
    )
    calls = dependencies(monkeypatch)

    result = service.reconcile_client_receipt(cursor, 31)

    assert result["result"] == "existing"
    assert result["transaction_ids"] == [701, 702]
    assert calls["snapshot"] == [] and calls["writer"] == []
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in cursor.executed)


def test_partial_retry_is_rejected_without_writes(monkeypatch):
    cursor = Cursor(
        staging=staged(reconciliation_status="reconciled"),
        existing=[existing_row()],
        payment_row=payment(deposit_received=Decimal("1000")),
    )
    calls = dependencies(monkeypatch)

    with pytest.raises(ValueError, match="incomplete or conflicting"):
        service.reconcile_client_receipt(cursor, 31)

    assert calls["snapshot"] == [] and calls["writer"] == []
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in cursor.executed)


@pytest.mark.parametrize(
    "changes",
    [
        {"format_id": "taishin"},
        {"direction": "outgoing"},
        {"classification_type": "government_subsidy"},
        {"credit": Decimal("0")},
    ],
)
def test_ineligible_staging_row_remains_pending_before_dependencies(monkeypatch, changes):
    cursor = Cursor(staging=staged(**changes))
    calls = dependencies(monkeypatch)

    result = service.reconcile_client_receipt(cursor, 31)

    assert result["result"] == "pending"
    assert calls == {"resolver": [], "snapshot": [], "writer": []}
    assert len(cursor.executed) == 1


def test_unresolved_virtual_account_remains_pending_without_snapshot_or_writer(monkeypatch):
    cursor = Cursor()
    calls = dependencies(
        monkeypatch,
        resolver_result={"result": "pending", "case_no": None, "reason": "case_not_found"},
    )

    result = service.reconcile_client_receipt(cursor, 31)

    assert result["result"] == "pending"
    assert result["reason"] == "case_not_found"
    assert calls["snapshot"] == [] and calls["writer"] == []


def test_source_does_not_open_or_finish_transactions():
    source = service.__file__
    text = open(source, encoding="utf-8").read()

    assert "get_connection" not in text
    assert ".commit(" not in text
    assert ".close(" not in text
    assert "record_client_payment_transaction(" not in text
    assert "record_client_payment_transaction_with_cursor" in text
