import os
from pathlib import Path
import uuid

import pymysql
import pytest
from dotenv import load_dotenv

from scripts.init_db import load_schema_parts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    PROJECT_ROOT / "db" / "schema_parts" / "65_client_payment_finance_link.sql"
)


class RecordingCursor:
    def __init__(self):
        self.executed = []

    def execute(self, statement):
        self.executed.append(statement)


def _migration_sql():
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _migration_statements():
    return [
        statement.strip()
        for statement in _migration_sql().split(";")
        if statement.strip()
    ]


def _connection():
    load_dotenv(".env")
    try:
        return pymysql.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "1234"),
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=2,
        )
    except pymysql.MySQLError as exc:
        pytest.skip(f"MySQL migration integration test unavailable: {exc}")


def test_migration_adds_nullable_canonical_finance_row_link():
    sql = _migration_sql()

    assert "ADD COLUMN `finance_import_row_id` BIGINT NULL" in sql
    assert "ADD INDEX `idx_client_payment_tx_finance_import_row`" in sql
    assert (
        "ADD CONSTRAINT `fk_client_payment_tx_finance_import_row` "
        "FOREIGN KEY (`finance_import_row_id`) "
        "REFERENCES `finance_import_rows` (`id`) "
        "ON UPDATE RESTRICT ON DELETE RESTRICT"
    ) in sql


def test_migration_guards_each_schema_change_for_idempotent_replay():
    sql = _migration_sql()

    assert "INFORMATION_SCHEMA.COLUMNS" in sql
    assert "INFORMATION_SCHEMA.STATISTICS" in sql
    assert "INFORMATION_SCHEMA.TABLE_CONSTRAINTS" in sql
    assert sql.count("'SELECT 1'") == 3
    assert sql.count("PREPARE client_payment_finance_link_stmt") == 6
    assert sql.count("EXECUTE client_payment_finance_link_stmt") == 3
    assert sql.count("DEALLOCATE PREPARE client_payment_finance_link_stmt") == 3


def test_migration_never_rewrites_or_removes_existing_transactions():
    ddl = _migration_sql().upper()

    assert "UPDATE CLIENT_PAYMENT_TRANSACTIONS" not in ddl
    assert "DELETE FROM CLIENT_PAYMENT_TRANSACTIONS" not in ddl
    assert "DROP TABLE" not in ddl
    assert "DROP COLUMN" not in ddl


def test_schema_parts_loader_can_parse_and_replay_migration():
    parts_dir = MIGRATION_PATH.parent
    cursor = RecordingCursor()

    loaded_parts = load_schema_parts(cursor, parts_dir)
    assert MIGRATION_PATH.name in loaded_parts
    first_run_statements = list(cursor.executed)
    assert first_run_statements

    assert load_schema_parts(cursor, parts_dir) == loaded_parts
    assert cursor.executed == first_run_statements + first_run_statements


def test_mysql_migration_allows_shared_canonical_row_null_manual_rows_and_replay():
    connection = _connection()
    database = f"codex_client_finance_link_{uuid.uuid4().hex}"
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 "
                "COLLATE utf8mb4_unicode_ci"
            )
            cursor.execute(f"USE `{database}`")
            cursor.execute(
                "CREATE TABLE finance_import_rows ("
                "id BIGINT AUTO_INCREMENT PRIMARY KEY, "
                "dedup_fingerprint CHAR(64) NOT NULL, "
                "UNIQUE KEY uq_finance_import_row_fingerprint (dedup_fingerprint)"
                ") ENGINE=InnoDB"
            )
            cursor.execute(
                "CREATE TABLE client_payment_transactions ("
                "id BIGINT AUTO_INCREMENT PRIMARY KEY, "
                "external_reference VARCHAR(100) NULL, "
                "UNIQUE KEY uq_client_payment_tx_reference (external_reference)"
                ") ENGINE=InnoDB"
            )
            cursor.execute(
                "INSERT INTO client_payment_transactions (external_reference) "
                "VALUES ('fp:stage-deposit'), ('fp:stage-first'), (NULL)"
            )

            for statement in _migration_statements():
                cursor.execute(statement)

            cursor.execute(
                "SELECT IS_NULLABLE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='client_payment_transactions' "
                "AND COLUMN_NAME='finance_import_row_id'",
                (database,),
            )
            assert cursor.fetchone() == ("YES",)
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='client_payment_transactions' "
                "AND INDEX_NAME='idx_client_payment_tx_finance_import_row'",
                (database,),
            )
            assert cursor.fetchone() == (1,)
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA=%s "
                "AND CONSTRAINT_NAME='fk_client_payment_tx_finance_import_row'",
                (database,),
            )
            assert cursor.fetchone() == (1,)

            cursor.execute(
                "INSERT INTO finance_import_rows (dedup_fingerprint) VALUES (%s)",
                ("a" * 64,),
            )
            canonical_id = cursor.lastrowid
            cursor.execute(
                "UPDATE client_payment_transactions SET finance_import_row_id=%s "
                "WHERE external_reference IN ('fp:stage-deposit','fp:stage-first')",
                (canonical_id,),
            )
            assert cursor.rowcount == 2
            with pytest.raises(pymysql.IntegrityError):
                cursor.execute(
                    "UPDATE client_payment_transactions SET finance_import_row_id=%s "
                    "WHERE external_reference IS NULL",
                    (canonical_id + 999,),
                )

            for statement in _migration_statements():
                cursor.execute(statement)
            cursor.execute(
                "SELECT external_reference, finance_import_row_id "
                "FROM client_payment_transactions ORDER BY id"
            )
            assert cursor.fetchall() == (
                ("fp:stage-deposit", canonical_id),
                ("fp:stage-first", canonical_id),
                (None, None),
            )
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
        finally:
            connection.close()
