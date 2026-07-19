from datetime import date
from decimal import Decimal

import pytest

from services.staff_actual_transfers import reconcile_staff_actual_transfer


FINGERPRINT = "a" * 64
EXTERNAL_REFERENCE = f"fp:{FINGERPRINT}"


class Cursor:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.current = None
        self.executed = []
        self.lastrowid = 501
        self.rowcount = 1

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.executed.append((compact, params))
        if compact.startswith("SELECT"):
            self.current = next(self.responses)

    def fetchone(self):
        return self.current

    def fetchall(self):
        return list(self.current or [])


def staged(**changes):
    value = {
        "finance_import_row_id": 8,
        "dedup_fingerprint": FINGERPRINT,
        "format_id": "taishin",
        "source_bank_account": "UNION-001",
        "transaction_date": date(2026, 7, 15),
        "direction": "outgoing",
        "debit": Decimal("900"),
        "credit": None,
        "counterparty_account": "STAFF-009",
        "resolved_counterparty_account": "STAFF-009",
        "classification_type": "staff_salary",
        "reconciliation_status": "pending",
        "reconciliation_reference": None,
        "matched_identity_ids": [9],
        "settlement_id": 20,
        "staff_id": 9,
        "settlement_month": date(2026, 7, 1),
        "total_payable": Decimal("1000"),
        "total_paid": Decimal("0"),
        "settlement_status": "finalized",
    }
    value.update(changes)
    return value


def owner(staff_id=9, account="STAFF-009"):
    return {"id": 3, "staff_id": staff_id, "account_no": account}


def details():
    return [
        {
            "id": 11,
            "settlement_id": 20,
            "staff_id": 9,
            "service_salary": Decimal("400"),
            "legacy_subsidy_payable": Decimal("100"),
            "floor_fee_amount": Decimal("0"),
            "adjustment_amount": Decimal("0"),
            "payable_amount": Decimal("500"),
            "legacy_subsidy_status": "confirmed",
            "review_required": False,
        },
        {
            "id": 12,
            "settlement_id": 20,
            "staff_id": 9,
            "service_salary": Decimal("500"),
            "legacy_subsidy_payable": Decimal("0"),
            "floor_fee_amount": Decimal("0"),
            "adjustment_amount": Decimal("0"),
            "payable_amount": Decimal("500"),
            "legacy_subsidy_status": "not_applicable",
            "review_required": False,
        },
    ]


def salary_allocations(amount_1="400", amount_2="500"):
    return [
        {
            "settlement_detail_id": 11,
            "component_type": "regular_salary",
            "allocated_amount": Decimal(amount_1),
            "allocation_method": "explicit",
        },
        {
            "settlement_detail_id": 12,
            "component_type": "regular_salary",
            "allocated_amount": Decimal(amount_2),
            "allocation_method": "explicit",
        },
    ]


def existing_transfer(**changes):
    value = {
        "id": 501,
        "settlement_id": 20,
        "staff_id": 9,
        "payment_phase": "normal",
        "transaction_type": "transfer",
        "transaction_status": "succeeded",
        "amount": Decimal("900"),
        "occurred_at": date(2026, 7, 15),
        "source_bank": "taishin",
        "source_account": "UNION-001",
        "counterparty_account": "STAFF-009",
        "external_reference": EXTERNAL_REFERENCE,
        "reversal_of_transfer_id": None,
        "raw_import_reference": "finance_import_row:8",
        "review_status": "confirmed",
    }
    value.update(changes)
    return value


def existing_allocation(detail_id, amount):
    return {
        "settlement_detail_id": detail_id,
        "component_type": "regular_salary",
        "allocated_amount": Decimal(str(amount)),
        "allocation_method": "explicit",
        "review_status": "approved",
        "reversal_of_allocation_id": None,
    }


def writes(cursor):
    return [(sql, params) for sql, params in cursor.executed if sql.startswith(("INSERT", "UPDATE"))]


def test_explicit_multi_detail_salary_transfer_is_one_bank_event_and_partially_settles():
    cursor = Cursor([staged(), [owner()], [], details(), []])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", salary_allocations())

    assert result["result"] == "reconciled"
    assert result["transfer_id"] == 501
    assert result["settlement"]["total_paid"] == Decimal("900")
    assert result["settlement"]["status"] == "partially_paid"
    transfer_inserts = [
        (sql, params) for sql, params in cursor.executed
        if sql.startswith("INSERT INTO staff_actual_transfers")
    ]
    assert len(transfer_inserts) == 1
    transfer_sql, transfer_params = transfer_inserts[0]
    assert "case_no" not in transfer_sql
    assert "staff_payment_id" not in transfer_sql
    assert EXTERNAL_REFERENCE in transfer_params
    assert "finance_import_row:8" in transfer_params
    allocation_inserts = [
        params for sql, params in cursor.executed
        if sql.startswith("INSERT INTO staff_transfer_allocations")
    ]
    assert allocation_inserts == [
        (501, 11, Decimal("400"), "regular_salary"),
        (501, 12, Decimal("500"), "regular_salary"),
    ]
    assert any(
        sql.startswith("UPDATE staff_monthly_settlements")
        and params == (Decimal("900"), "partially_paid", 20)
        for sql, params in cursor.executed
    )
    assert any(
        sql.startswith("UPDATE finance_import_rows")
        and params == (EXTERNAL_REFERENCE, 8)
        for sql, params in cursor.executed
    )


def test_confirmed_second_subsidy_completes_monthly_settlement():
    row = staged(
        debit=Decimal("100"),
        classification_type="staff_legacy_subsidy",
        total_paid=Decimal("900"),
        settlement_status="partially_paid",
    )
    prior_ledger = [
        {
            "settlement_detail_id": 11,
            "component_type": "regular_salary",
            "allocated_amount": Decimal("400"),
            "transaction_type": "transfer",
        },
        {
            "settlement_detail_id": 12,
            "component_type": "regular_salary",
            "allocated_amount": Decimal("500"),
            "transaction_type": "transfer",
        },
    ]
    allocations = [{
        "settlement_detail_id": 11,
        "component_type": "legacy_subsidy",
        "allocated_amount": Decimal("100"),
        "allocation_method": "explicit",
    }]
    cursor = Cursor([row, [owner()], [], details(), prior_ledger])

    result = reconcile_staff_actual_transfer(
        cursor, 8, 20, "second_subsidy", allocations
    )

    assert result["result"] == "reconciled"
    assert result["settlement"]["total_paid"] == Decimal("1000")
    assert result["settlement"]["status"] == "paid"


def test_same_detail_can_allocate_multiple_distinct_components():
    multi_component_detail = {
        **details()[0],
        "floor_fee_amount": Decimal("50"),
        "payable_amount": Decimal("550"),
    }
    allocations = [
        {
            "settlement_detail_id": 11,
            "component_type": "regular_salary",
            "allocated_amount": Decimal("400"),
            "allocation_method": "explicit",
        },
        {
            "settlement_detail_id": 11,
            "component_type": "floor_fee",
            "allocated_amount": Decimal("50"),
            "allocation_method": "explicit",
        },
    ]
    cursor = Cursor([
        staged(debit=Decimal("450")),
        [owner()],
        [],
        [multi_component_detail],
        [],
    ])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", allocations)

    assert result["result"] == "reconciled"
    allocation_inserts = [
        params for sql, params in cursor.executed
        if sql.startswith("INSERT INTO staff_transfer_allocations")
    ]
    assert allocation_inserts == [
        (501, 11, Decimal("400"), "regular_salary"),
        (501, 11, Decimal("50"), "floor_fee"),
    ]


@pytest.mark.parametrize(
    ("phase", "classification", "component"),
    [
        ("normal", "staff_salary", "legacy_subsidy"),
        ("first_salary", "staff_salary", "legacy_subsidy"),
        ("second_subsidy", "staff_legacy_subsidy", "regular_salary"),
    ],
)
def test_phase_component_mismatch_stays_pending_without_writes(
    phase, classification, component
):
    allocation = [{
        "settlement_detail_id": 11,
        "component_type": component,
        "allocated_amount": Decimal("100"),
        "allocation_method": "explicit",
    }]
    cursor = Cursor([staged(debit=Decimal("100"), classification_type=classification)])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, phase, allocation)

    assert result["result"] == "pending"
    assert writes(cursor) == []


@pytest.mark.parametrize("amount", ["399.99", "400.01", "200"])
def test_component_must_pay_its_full_remaining_balance(amount):
    allocation = [salary_allocations(amount_1=amount)[0]]
    cursor = Cursor([
        staged(debit=Decimal(amount)), [owner()], [], details(), []
    ])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", allocation)

    assert result["result"] == "pending"
    assert result["reason"] == "component_balance_not_paid_exactly"
    assert writes(cursor) == []


def test_cross_settlement_or_staff_detail_stays_pending():
    foreign_detail = {**details()[0], "settlement_id": 99}
    allocation = [salary_allocations()[0]]
    cursor = Cursor([staged(debit=Decimal("400")), [owner()], [], [foreign_detail], []])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", allocation)

    assert result["result"] == "pending"
    assert result["reason"] == "allocation_crosses_settlement_or_staff"
    assert writes(cursor) == []


def test_ambiguous_bank_account_owner_stays_pending():
    cursor = Cursor([staged(), [owner(), {**owner(), "id": 4}]])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", salary_allocations())

    assert result["reason"] == "counterparty_account_owner_not_unique"
    assert writes(cursor) == []


def test_raw_counterparty_account_never_falls_back_when_resolved_account_is_missing():
    cursor = Cursor([staged(resolved_counterparty_account=None)])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", salary_allocations())

    assert result["result"] == "pending"
    assert result["reason"] == "resolved_counterparty_account_missing"
    assert writes(cursor) == []


def test_transfer_persists_resolved_account_not_raw_audit_account():
    cursor = Cursor([
        staged(
            counterparty_account="RAW-AUDIT-VALUE",
            resolved_counterparty_account="STAFF-009",
        ),
        [owner()],
        [],
        details(),
        [],
    ])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", salary_allocations())

    assert result["result"] == "reconciled"
    transfer_params = next(
        params for sql, params in cursor.executed
        if sql.startswith("INSERT INTO staff_actual_transfers")
    )
    assert "STAFF-009" in transfer_params
    assert "RAW-AUDIT-VALUE" not in transfer_params


def test_allocation_total_must_equal_bank_debit():
    cursor = Cursor([staged(debit=Decimal("901")), [owner()]])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", salary_allocations())

    assert result["reason"] == "allocation_total_must_equal_bank_debit"
    assert writes(cursor) == []


def test_inferred_allocation_is_never_formalized():
    allocations = salary_allocations()
    allocations[0]["allocation_method"] = "inferred"
    cursor = Cursor([staged()])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", allocations)

    assert result["reason"] == "allocation_method_must_be_explicit"
    assert writes(cursor) == []


def test_exact_retry_returns_existing_without_mutation():
    row = staged(
        reconciliation_status="reconciled",
        reconciliation_reference=EXTERNAL_REFERENCE,
        total_paid=Decimal("900"),
        settlement_status="partially_paid",
    )
    cursor = Cursor([
        row,
        [owner()],
        [existing_transfer()],
        [existing_allocation(11, 400), existing_allocation(12, 500)],
    ])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", salary_allocations())

    assert result["result"] == "existing"
    assert result["transfer_id"] == 501
    assert writes(cursor) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": Decimal("899")},
        {"settlement_id": 21},
        {"payment_phase": "first_salary"},
        {"raw_import_reference": "finance_import_row:99"},
    ],
)
def test_different_existing_transfer_requires_review_without_mutation(changes):
    cursor = Cursor([
        staged(), [owner()], [{**existing_transfer(), **changes}]
    ])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", salary_allocations())

    assert result["result"] == "pending"
    assert result["review_required"] is True
    assert result["reason"] == "existing_transfer_differs"
    assert writes(cursor) == []


def test_different_existing_allocations_require_review_without_mutation():
    row = staged(
        reconciliation_status="reconciled",
        reconciliation_reference=EXTERNAL_REFERENCE,
    )
    cursor = Cursor([
        row, [owner()], [existing_transfer()], [existing_allocation(11, 400)]
    ])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", salary_allocations())

    assert result["result"] == "pending"
    assert result["review_required"] is True
    assert writes(cursor) == []


def test_stored_paid_projection_must_match_locked_allocation_ledger():
    cursor = Cursor([
        staged(total_paid=Decimal("1"), settlement_status="partially_paid"),
        [owner()], [], details(), [],
    ])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", salary_allocations())

    assert result["reason"] == "settlement_paid_projection_mismatch"
    assert result["review_required"] is True
    assert writes(cursor) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"direction": "incoming"},
        {"debit": Decimal("0")},
        {"classification_type": "client_subsidy_return"},
        {"matched_identity_ids": []},
        {"dedup_fingerprint": "A" * 64},
    ],
)
def test_ineligible_staging_content_never_writes(changes):
    cursor = Cursor([staged(**changes)])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", salary_allocations())

    assert result["result"] == "pending"
    assert writes(cursor) == []


def test_duplicate_detail_component_allocation_is_rejected_before_database_writes():
    allocations = [salary_allocations()[0], {**salary_allocations()[0]}]
    cursor = Cursor([staged()])

    result = reconcile_staff_actual_transfer(cursor, 8, 20, "normal", allocations)

    assert result["reason"] == "duplicate_settlement_detail_component_allocation"
    assert writes(cursor) == []
