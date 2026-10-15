"""
File: test_government_subsidy_repository_guards.py
Description: 驗證政府溢撥 repository 的收款帳戶與 projection lineage fail-closed 邊界。
"""

from datetime import date, datetime, timezone

import pytest

from infrastructure.mysql.government_subsidy_repository import (
    _CLAIM_PLANNING_SOURCE_SELECT_SQL,
    MySqlGovernmentSubsidyRepository,
    _overpayment_outbox_lineage,
    _planning_source,
    _link_client_subsidy_return,
)
from shared_kernel.money import MoneyNTD
from shared_kernel.clock import FixedBusinessClock


class _Cursor:
    def __init__(self, rows=(), lineage=None):
        self.rows = rows
        self.lineage = lineage
        self.statement = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _params=()):
        self.statement = statement

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.lineage


class _Connection:
    def __init__(self, rows=(), lineage=None):
        self.cursor_value = _Cursor(rows, lineage)

    def cursor(self):
        return self.cursor_value








class _QueryCursor:
    def __init__(self, recipient_row):
        self.recipient_row = recipient_row
        self.result = None
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _params=()):
        self.statements.append(statement)
        if "FROM government_subsidy_overpayments" in statement:
            self.result = {
                "overpayment_identity": "over-1",
                "source_finance_import_row_id": 11,
                "source_transaction_id": 21,
                "payer_identity": "hccg",
                "remaining_amount_ntd": 700,
                "status": "pending_review",
                "projection_version": 3,
            }
        elif "FROM subsidy_claim_batch_items" in statement:
            self.result = []
        elif "FROM government_payer_receiving_accounts" in statement:
            self.result = [self.recipient_row]

    def fetchone(self):
        return self.result if isinstance(self.result, dict) else None

    def fetchall(self):
        return self.result if isinstance(self.result, list) else []


class _QueryConnection:
    def __init__(self, recipient_row):
        self.cursor_value = _QueryCursor(recipient_row)

    def cursor(self):
        return self.cursor_value






def test_overpayment_lineage_requires_projection_for_source_transaction():
    connection = _Connection(
        lineage={"claim_batch_id": 4, "transaction_id": 9, "projection_event_id": 11}
    )

    assert _overpayment_outbox_lineage(connection.cursor_value, "over-1") == (4, 9, 11)
    statement = " ".join(connection.cursor_value.statement.split()).lower()
    assert "event.transaction_id=transaction.id" in statement


def test_claim_planning_source_uses_assignment_frozen_rate_not_identity_price():
    source = _planning_source(
        {
            "assignment_id": 91,
            "case_no": "CASE-450",
            "staff_id": 7,
            "official_service_day_count": 5,
            "service_hours_per_day": 8,
            "identity_status": "一般市民",
            "subsidy_unit_price_ntd": 450,
            "assignment_effective": 1,
        }
    )

    assert source.assignment.official_service_hours == 40


def test_claim_planning_source_prefers_explicit_effective_birth_count_rate():
    source = _planning_source(
        {
            "assignment_id": 91,
            "case_no": "CASE-450",
            "staff_id": 7,
            "official_service_day_count": 4,
            "service_hours_per_day": 8,
            "identity_status": "一般市民",
            "subsidy_unit_price_ntd": 300,
            "assignment_effective": 1,
        },
        effective_unit_price_ntd=450,
    )

    assert source.assignment.official_service_hours == 32
    assert source.unit_price_ntd == MoneyNTD(450)
    assert "LEFT JOIN assignment_payroll_rate_snapshots rate" in _CLAIM_PLANNING_SOURCE_SELECT_SQL
    assert "rate.hourly_rate_ntd AS subsidy_unit_price_ntd" in _CLAIM_PLANNING_SOURCE_SELECT_SQL


class _EntitlementCursor:
    def __init__(self):
        self.statements = []
        self.current = None

    def execute(self, statement, parameters):
        self.statements.append((" ".join(statement.split()), parameters))
        if "FROM client_obligations" in statement:
            self.current = (
                {
                    "obligation_identity": "client-subsidy-return:CASE-450:terminal",
                    "amount_due_ntd": 14_400,
                },
            )
        else:
            self.current = ()

    def fetchall(self):
        return self.current


def test_claim_items_link_to_one_exact_client_subsidy_return_entitlement():
    cursor = _EntitlementCursor()
    first = type("Item", (), {"requested_amount_ntd": MoneyNTD(9_000)})()
    second = type("Item", (), {"requested_amount_ntd": MoneyNTD(5_400)})()

    _link_client_subsidy_return(
        cursor,
        "CASE-450",
        ((101, first), (102, second)),
    )

    links = [
        values
        for statement, values in cursor.statements
        if "INSERT INTO client_subsidy_return_claim_item_links" in statement
    ]
    assert links == [
        ("client-subsidy-return:CASE-450:terminal", 101, 9_000),
        ("client-subsidy-return:CASE-450:terminal", 102, 5_400),
    ]


def test_claim_planning_source_rejects_missing_assignment_frozen_rate():
    with pytest.raises(ValueError, match="government_subsidy_claim_facts_invalid"):
        _planning_source(
            {
                "assignment_id": 91,
                "case_no": "CASE-450",
                "staff_id": 7,
                "official_service_day_count": 5,
                "service_hours_per_day": 8,
                "identity_status": "一般市民",
                "subsidy_unit_price_ntd": None,
                "assignment_effective": 1,
            }
        )
