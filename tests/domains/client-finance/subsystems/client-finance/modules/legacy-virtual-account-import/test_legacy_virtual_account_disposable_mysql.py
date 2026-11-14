from argparse import Namespace
import os

import pandas as pd
import pymysql
import pytest

import scripts.migrate_preserved_database_additive_schema as migration
from infrastructure.mysql.legacy_virtual_account_repository import MySqlLegacyVirtualAccountRepository
from infrastructure.mysql.nas_mutations import ensure_nas_procedures
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from subsystems.client_finance.case_virtual_account import CaseVirtualAccountApplication, CaseVirtualAccountError
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
                "result": "resolved", "case_no": "114000018", "reason": None,
            }
        # A second imported mapping, not a lower-precedence generated account,
        # makes the owner ambiguous and must stay pending.
        duplicate = tmp_path / "duplicate-accounts.xlsx"
        pd.DataFrame([["99781699114033", "114000033"]], columns=["虛擬帳號", "市府訂單號碼"]).to_excel(duplicate, index=False)
        duplicate_preview = service.preview(str(duplicate))
        service.apply(str(duplicate), "legacy-va-e2e-duplicate", duplicate_preview.preview_fingerprint, "test")
        with connection.cursor() as cursor:
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


def test_historical_non_citizen_single_edit_and_mixed_workbook(tmp_path):
    bootstrap(_arguments())
    connection = _connection()
    try:
        ensure_nas_procedures(connection)
        with connection.cursor() as cursor:
            for case_no, status in (
                ("A115001", "洽談中"), ("A115002", "洽談中"), ("A115003", "洽談中"),
                ("A116001", "洽談中"), ("115000001", "訂單取消"), ("115000002", "洽談中"),
                ("115000003", "訂單取消"),
            ):
                cursor.execute("INSERT INTO clients(case_no,name) VALUES (%s,'Synthetic')", (case_no,))
                cursor.execute("INSERT INTO orders(case_no,client_id,status) VALUES (%s,%s,%s)",
                               (case_no, cursor.lastrowid, status))
                if status == "訂單取消":
                    cursor.execute(
                        "INSERT INTO order_lifecycle_control_events "
                        "(case_no,control_type,control_key,scope,action,actor,reason,expected_version,idempotency_key,payload_hash,payload_snapshot) "
                        "VALUES (%s,'cancellation','order_cancelled','order','activate','test','fixture',0,'fixture',%s,'{}')",
                        (case_no, "0" * 64),
                    )
                    cursor.execute(
                        "INSERT INTO order_lifecycle_control_state "
                        "(case_no,control_type,control_key,scope,state,current_event_id,reason,changed_by) "
                        "VALUES (%s,'cancellation','order_cancelled','order','active',%s,'fixture','test')",
                        (case_no, cursor.lastrowid),
                    )
            cursor.executemany(
                "INSERT INTO client_legacy_virtual_accounts "
                "(case_no,virtual_account,source_content_digest,source_row,created_by) VALUES (%s,%s,%s,2,'test')",
                [(case, account, "0" * 64) for case, account in (
                    ("115000001", "99781699115040"), ("115000001", "99781699115043"),
                    ("115000002", "99781699115041"), ("115000003", "99781699115042"),
                )],
            )
        connection.commit()

        repository = MySqlLegacyVirtualAccountRepository(connection)
        unit_of_work = lambda: MySqlUnitOfWork(connection)
        single = CaseVirtualAccountApplication(repository, unit_of_work)
        workbook_service = LegacyVirtualAccountWorkbookService(repository, unit_of_work)

        before = single.query("A115001")
        assert before.effective_virtual_account == "99781699115501"
        receipt = single.apply("A115001", "99781699115040", before.mapping_ids, "single-transfer", "test")
        assert receipt.transferred_from_case_nos == ("115000001",)
        updated = single.query("A115001")
        assert updated.effective_virtual_account == "99781699115040"
        assert updated.built_in_virtual_account == "99781699115501"
        assert single.query("115000001").imported_virtual_accounts == ("99781699115043",)
        assert single.apply("A115001", "99781699115040", before.mapping_ids, "single-transfer", "test") == receipt
        with pytest.raises(CaseVirtualAccountError, match="115000002"):
            single.apply("A115001", "99781699115041", updated.mapping_ids, "single-conflict", "test")
        assert not single.query("A116001").editable
        with pytest.raises(CaseVirtualAccountError):
            single.apply("A116001", "99781699115044", (), "single-year", "test")

        workbook = tmp_path / "historical-non-citizen.xlsx"
        pd.DataFrame([
            ["99781699115042", "A115002"],
            ["99781699115041", "A115003"],
            ["99781699115044", "A116001"],
            ["99781699115045", "115000002"],
        ], columns=["虛擬帳號", "市府訂單號碼"]).to_excel(workbook, index=False)
        preview = workbook_service.preview(str(workbook))
        assert [(row.source_row, row.case_no, row.status, row.related_case_nos) for row in preview.non_citizen_rows] == [
            (2, "A115002", "transfer", ("115000003",)),
            (3, "A115003", "conflict", ("115000002",)),
            (4, "A116001", "ineligible_year", ()),
        ]
        receipt = workbook_service.apply(str(workbook), "mixed-workbook", preview.preview_fingerprint, "test")
        assert receipt.inserted_count == 2
        assert workbook_service.apply(str(workbook), "mixed-workbook", preview.preview_fingerprint, "test").replayed_workbook
        assert single.query("A115002").effective_virtual_account == "99781699115042"
        assert single.query("115000003").imported_virtual_accounts == ()
        assert single.query("A115003").imported_virtual_accounts == ()
        assert single.query("115000002").imported_virtual_accounts == ("99781699115041", "99781699115045")
        with connection.cursor() as cursor:
            assert resolve_client_virtual_account(cursor, "99781699115040")["case_no"] == "A115001"
            assert resolve_client_virtual_account(cursor, "99781699115501")["result"] == "pending"
            assert resolve_client_virtual_account(cursor, "99781699115042")["case_no"] == "A115002"
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
