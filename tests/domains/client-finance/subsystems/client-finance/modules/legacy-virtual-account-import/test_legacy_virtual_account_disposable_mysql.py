from argparse import Namespace
import os

import pandas as pd
import pymysql
import pytest

import scripts.migrate_preserved_database_additive_schema as migration
from infrastructure.mysql.legacy_virtual_account_repository import MySqlLegacyVirtualAccountRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from subsystems.client_finance.legacy_virtual_account_workbook import LegacyVirtualAccountWorkbookService
from subsystems.client_finance.virtual_account_resolution import resolve_client_virtual_account


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE or not DATABASE.startswith("lu_test_"),
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_imported_legacy_account_is_durable_and_reuse_stays_pending(tmp_path):
    bootstrap(_arguments())
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES ('114000018','Legacy'),('114000033','Current')")
            cursor.execute("SELECT id,case_no FROM clients WHERE case_no IN ('114000018','114000033')")
            clients = {row["case_no"]: row["id"] for row in cursor.fetchall()}
            cursor.execute("INSERT INTO orders(case_no,client_id,status) VALUES ('114000018',%s,'歷史訂單－帳務完成'),('114000033',%s,'洽談中')", (clients["114000018"], clients["114000033"]))
        connection.commit()

        workbook = tmp_path / "legacy-accounts.xlsx"
        pd.DataFrame([
            ["99781699114033", "114000018"],
            ["99781699114999", "114009999"],
        ], columns=["虛擬帳號", "市府訂單號碼"]).to_excel(workbook, index=False)
        service = LegacyVirtualAccountWorkbookService(
            MySqlLegacyVirtualAccountRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
        preview = service.preview(str(workbook))
        receipt = service.apply(str(workbook), "legacy-va-e2e", preview.preview_fingerprint, "test")

        assert receipt.inserted_count == 1
        assert receipt.skipped_count == 1
        with connection.cursor() as cursor:
            cursor.execute("SELECT case_no,virtual_account FROM client_legacy_virtual_accounts")
            assert cursor.fetchall() == [{"case_no": "114000018", "virtual_account": "99781699114033"}]
            assert resolve_client_virtual_account(cursor, "99781699114033") == {
                "result": "pending", "case_no": None, "reason": "case_not_unique",
            }
    finally:
        connection.close()
        _drop_database()


def test_preserve_part_keeps_existing_orders_and_adds_an_empty_mapping_table():
    admin = _admin_connection()
    try:
        with admin.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    finally:
        admin.close()
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE orders (case_no VARCHAR(50) NOT NULL PRIMARY KEY) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
            cursor.execute("INSERT INTO orders(case_no) VALUES ('114000018')")
            sql = (migration.ROOT / "db/schema_parts/1042_client_legacy_virtual_accounts.sql").read_text(encoding="utf-8")
            for statement in migration.split_sql(sql):
                cursor.execute(statement)
            cursor.execute("SELECT case_no FROM orders")
            assert cursor.fetchall() == [{"case_no": "114000018"}]
            cursor.execute("SELECT COUNT(*) AS count FROM client_legacy_virtual_accounts")
            assert cursor.fetchone()["count"] == 0
    finally:
        connection.close()
        _drop_database()


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


def _drop_database():
    admin = _admin_connection()
    try:
        with admin.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{DATABASE}`")
    finally:
        admin.close()


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def _connection():
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
