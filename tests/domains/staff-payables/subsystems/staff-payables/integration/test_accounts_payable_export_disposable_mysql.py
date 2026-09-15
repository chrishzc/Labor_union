import os
import re
from datetime import date

import pymysql
import pytest

from infrastructure.mysql.accounts_payable_export_sources import (
    _STAFF_PAYABLES_SQL,
    MySqlStaffPayableExportSource,
)


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    re.fullmatch(r"lu_test_[A-Za-z0-9_]+", DATABASE or "") is None,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_formal_staff_payable_and_exact_historical_settlement_use_one_mysql_contract():
    _create_database()
    connection = _connection()
    try:
        _create_minimum_schema(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO staff(id,name,identity_card) VALUES (7,'月嫂甲','A123456789')"
            )
            cursor.execute(
                "INSERT INTO orders(case_no,staff_payment_due_date) VALUES ('CASE-1','2026-10-15')"
            )
            cursor.execute(
                "INSERT INTO staff_bank_accounts(id,staff_id,is_primary,bank_code,account_no) "
                "VALUES (1,7,1,'012','1234567890')"
            )
            cursor.execute(
                "INSERT INTO staff_obligations("
                "obligation_identity,case_no,staff_id,amount_due_ntd,due_date,direction,"
                "status,payroll_version) VALUES ("
                "'service:CASE-1:assignment:7','CASE-1',7,42000,'2026-10-15',"
                "'payable_to_staff','open',1)"
            )
            cursor.execute(_STAFF_PAYABLES_SQL, ("2026-10-15",))
            rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["export_amount_ntd"] == 42_000

            cursor.execute(
                "INSERT INTO historical_staff_payout_projections("
                "obligation_identity,amount_snapshot_ntd,obligation_payroll_version,"
                "confirmation_kind) VALUES ("
                "'service:CASE-1:assignment:7',42000,1,'settled')"
            )
            cursor.execute(_STAFF_PAYABLES_SQL, ("2026-10-15",))
            assert not cursor.fetchall()

        case_items = MySqlStaffPayableExportSource(connection).load_case(
            "CASE-1", date(2026, 11, 15)
        )
        assert len(case_items) == 1
        assert case_items[0].disposition == "paid_or_settled"
        assert case_items[0].balance.amount == 0
        assert case_items[0].effective_due_date == date(2026, 10, 15)

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE staff_obligations SET amount_due_ntd=43000,payroll_version=2 "
                "WHERE obligation_identity='service:CASE-1:assignment:7'"
            )
            cursor.execute(_STAFF_PAYABLES_SQL, ("2026-10-15",))
            rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["export_amount_ntd"] == 43_000
    finally:
        connection.close()
        _drop_database()


def _create_minimum_schema(connection):
    statements = (
        "CREATE TABLE staff(id BIGINT PRIMARY KEY,name VARCHAR(100),identity_card VARCHAR(20))",
        "CREATE TABLE orders(case_no VARCHAR(50) PRIMARY KEY,staff_payment_due_date DATE NULL)",
        "CREATE TABLE staff_obligations("
        "obligation_identity VARCHAR(191) PRIMARY KEY,case_no VARCHAR(50),staff_id BIGINT,"
        "amount_due_ntd INT,due_date DATE,direction VARCHAR(50),status VARCHAR(30),"
        "payroll_version INT)",
        "CREATE TABLE staff_payable_projections("
        "obligation_identity VARCHAR(191) PRIMARY KEY,balance_ntd INT,status VARCHAR(30))",
        "CREATE TABLE historical_staff_payout_projections("
        "id BIGINT AUTO_INCREMENT PRIMARY KEY,obligation_identity VARCHAR(191),"
        "amount_snapshot_ntd INT,obligation_payroll_version INT,"
        "confirmation_kind VARCHAR(30))",
        "CREATE TABLE staff_bank_accounts("
        "id BIGINT PRIMARY KEY,staff_id BIGINT,is_primary TINYINT,"
        "bank_code VARCHAR(10),account_no VARCHAR(50))",
    )
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


def _admin_connection():
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _create_database():
    _drop_database()
    connection = _admin_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()


def _drop_database():
    connection = _admin_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{DATABASE}`")
    finally:
        connection.close()


def _connection():
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
