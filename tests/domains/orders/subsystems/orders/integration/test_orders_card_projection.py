"""
File: test_orders_card_projection.py
Description: 驗證內部 Orders 卡片完整聯絡資料、缺件與 bounded read 契約。
"""

from datetime import date, datetime
from decimal import Decimal
import re

import pytest

from api.routes.orders_card_projection import _materialize
from api.schemas.orders_card_projection import OrdersCardProjectionView
from infrastructure.mysql.orders_card_projection_repository import (
    MySqlOrdersCardProjectionRepository,
)
from subsystems.orders.card_projection_query import (
    OrdersCardProjectionContractError,
    OrdersCardProjectionQueryService,
)


def _row(**overrides):
    row = {
        "case_no": "C-100",
        "client_id": 7,
        "client_source_version": datetime(2026, 8, 21, 9, 0),
        "phone": "0912345678",
        "address": "新竹市測試路 1 號",
        "lifecycle_version": 4,
        "requires_cooking": 1,
        "floor_fee": Decimal("1200.00"),
        "actual_start_date": date(2026, 9, 1),
        "actual_end_date": date(2026, 9, 30),
        "deposit_obligation_count": 1,
        "deposit_amount_ntd": 12000,
        "deposit_obligation_identity": "deposit:C-100",
        "deposit_obligation_status": "settled",
        "deposit_projection_state": "settled",
        "deposit_allocated_ntd": 12000,
        "deposit_source_version": 3,
        "deposit_settled_on": date(2026, 8, 20),
        "scheduling_version": 2,
        "assignment_id": 19,
        "assignment_staff_id": 31,
        "assignment_sequence": 1,
        "assigned_start_date": date(2026, 9, 1),
        "assigned_end_date": date(2026, 9, 30),
        "assignment_status": "planned",
        "staff_name": "王小明",
        "staff_source_version": datetime(2026, 8, 21, 8, 0),
    }
    row.update(overrides)
    return row


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        self.executions.append((sql, params))

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)

    def cursor(self):
        return self.cursor_instance


def test_card_projection_keeps_full_contact_for_internal_admin_and_nested_typed_fields():
    projection = OrdersCardProjectionQueryService(
        _Repository((_row(),))
    ).query("C-100")

    assert projection.contact_phone.value == "0912345678"
    assert projection.contact_address.value == "新竹市測試路 1 號"
    assert projection.requires_cooking.value is True
    assert projection.floor_fee_ntd.value == 1200
    assert projection.deposit_amount_ntd.value == 12000
    assert projection.assignment_segments.value[0].staff_name.value == "王小明"
    assert projection.assignment_segments.value[0].assigned_start_date.value == date(
        2026, 9, 1
    )
    view = OrdersCardProjectionView.model_validate(
        _materialize(projection), from_attributes=True
    )
    assert view.assignment_segments.value[0].status.value == "planned"


def test_card_projection_normalizes_blank_optional_address_to_unavailable():
    projection = OrdersCardProjectionQueryService(
        _Repository((_row(address="  \t"),))
    ).query("C-100")

    assert projection.contact_address.value is None
    assert projection.contact_address.availability == "unavailable"
    assert projection.contact_address.availability_reason == "client_address_not_provided"
    view = OrdersCardProjectionView.model_validate(
        _materialize(projection), from_attributes=True
    )
    assert view.contact_address.value is None
    assert view.contact_address.availability == "unavailable"


def test_card_projection_keeps_unknown_cooking_and_missing_assignment_as_unavailable():
    projection = OrdersCardProjectionQueryService(
        _Repository(
            (
                _row(
                    requires_cooking=None,
                    assignment_id=None,
                    assignment_staff_id=None,
                    assignment_sequence=None,
                    assigned_start_date=None,
                    assigned_end_date=None,
                    assignment_status=None,
                    staff_name=None,
                ),
            )
        )
    ).query("C-100")

    assert projection.requires_cooking.value is None
    assert projection.requires_cooking.availability == "unavailable"
    assert projection.requires_cooking.availability_reason == (
        "orders_requires_cooking_unknown"
    )
    assert projection.assignment_segments.value is None
    assert projection.assignment_segments.availability_reason == (
        "formal_assignment_segments_missing"
    )


def test_card_projection_rejects_duplicate_assignment_identity():
    duplicate = _row()
    with pytest.raises(OrdersCardProjectionContractError, match="duplicate"):
        OrdersCardProjectionQueryService(
            _Repository((duplicate, dict(duplicate)))
        ).query("C-100")


def test_repository_uses_one_bounded_read_without_commit_or_n_plus_one():
    connection = _Connection((_row(),))
    repository = MySqlOrdersCardProjectionRepository(connection)

    repository.fetch_by_case_no("C-100")

    assert len(connection.cursor_instance.executions) == 1
    sql, params = connection.cursor_instance.executions[0]
    assert sql.lstrip().startswith("SELECT")
    assert "LIMIT %s" in sql
    assert "deposit_projection.contracted_amount_ntd AS deposit_amount_ntd" in sql
    assert "deposit.amount_due_ntd AS deposit_amount_ntd" not in sql
    assert (
        "assignment.generation_id = scheduling.effective_generation_id" in sql
    )
    assert re.search(r"\b(?:INSERT|UPDATE|DELETE)\b", sql, re.IGNORECASE) is None
    assert params == ("C-100", 33)


class _Repository:
    def __init__(self, rows):
        self.rows = rows

    def fetch_by_case_no(self, case_no):
        assert case_no == "C-100"
        return self.rows
