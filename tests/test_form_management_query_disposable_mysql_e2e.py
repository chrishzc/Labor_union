"""Disposable MySQL proof for Form Management read-only facts."""

from __future__ import annotations

from argparse import Namespace
from datetime import date
import os

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def _seed_orders(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO staff (name,status) VALUES (%s,'active')", ("Form Staff",))
        staff_id = cursor.lastrowid
        _insert_case(cursor, "FORM-001", "Regular Client", "\u4e00\u822c\u5e02\u6c11", "\u670d\u52d9\u4e2d", staff_id)
        _insert_case(cursor, "FORM-002", "Subsidy Client", "\u88dc\u52a9\u5e02\u6c11", "\u8a02\u55ae\u6210\u7acb", None)
    connection.commit()


def _insert_case(cursor, case_no, name, identity_status, status, staff_id) -> None:
    cursor.execute(
        "INSERT INTO clients (case_no,name,identity_status,service_time,service_type,delivery_type,residence_type,city) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (case_no, name, identity_status, "09:00-17:00", "postpartum", "hospital", "home", "Taipei"),
    )
    cursor.execute(
        "INSERT INTO orders (case_no,client_id,staff_id,status,lifecycle_version,start_date,end_date,"
        "service_days,service_hours_per_day,floor_fee,service_start_time,service_end_time,"
        "service_end_day_offset,staff_payment_due_date) VALUES (%s,%s,%s,%s,0,%s,%s,2,8,0,%s,%s,0,%s)",
        (case_no, cursor.lastrowid, staff_id, status, date(2026, 8, 1), date(2026, 8, 2),
         "09:00:00", "17:00:00", date(2026, 8, 15)),
    )


def test_form_management_statistics_and_context_use_canonical_mysql_reads():
    bootstrap(_arguments())
    from infrastructure.mysql.form_management_query_repository import MySqlFormManagementQueryRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.orders.form_management_query import FormManagementQueryService

    connection = get_connection()
    try:
        _seed_orders(connection)
        service = FormManagementQueryService(MySqlFormManagementQueryRepository(connection))
        statistics = service.statistics()
        context = service.case_context("FORM-001")
    finally:
        connection.close()

    assert statistics.global_active_orders_count == 2
    assert statistics.global_active_staff_count == 1
    assert statistics.global_subsidy_orders_count == 1
    assert statistics.global_total_receivable_sum == 16800
    assert statistics.global_govt_claim_count == 2
    assert context.service_type == "postpartum"
    assert context.city == "Taipei"
