import os
from pathlib import Path
import uuid

import pymysql
import pytest
from dotenv import load_dotenv


SCHEMA_PATH = Path("db/schema_parts/60_finance_import_staging.sql")


def _statements():
    source = SCHEMA_PATH.read_text(encoding="utf-8")
    return [statement.strip() for statement in source.split(";") if statement.strip()]


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
        pytest.skip(f"MySQL DDL integration test unavailable: {exc}")


def test_mysql_executes_staging_ddl_and_enforces_canonical_occurrence_keys():
    connection = _connection()
    database = f"codex_staging_schema_{uuid.uuid4().hex}"
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cursor.execute(f"USE `{database}`")
            for statement in _statements():
                cursor.execute(statement)

            cursor.execute(
                "SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=%s",
                (database,),
            )
            columns = {}
            for table, column in cursor.fetchall():
                columns.setdefault(table, set()).add(column)

            assert {"format_id", "source_file", "sheet_name", "header_row", "row_count", "status"} <= columns["finance_import_batches"]
            assert {
                "dedup_fingerprint",
                "matched_identity_ids",
                "resolved_counterparty_account",
                "classification_type",
                "reconciliation_status",
            } <= columns["finance_import_rows"]
            assert {"batch_id", "finance_import_row_id", "sheet_name", "source_row"} <= columns["finance_import_occurrences"]

            cursor.execute(
                "SELECT IS_NULLABLE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='finance_import_rows' "
                "AND COLUMN_NAME='dedup_fingerprint'",
                (database,),
            )
            assert cursor.fetchone() == ("NO",)

            cursor.execute(
                "SELECT IS_NULLABLE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='finance_import_rows' "
                "AND COLUMN_NAME='resolved_counterparty_account'",
                (database,),
            )
            assert cursor.fetchone() == ("YES",)

            cursor.execute(
                "INSERT INTO finance_import_batches "
                "(format_id,source_file,sheet_name,header_row,row_count,status) "
                "VALUES ('legacy','history.xlsx','statement',3,2,'staged')"
            )
            batch_id = cursor.lastrowid
            row_sql = (
                "INSERT INTO finance_import_rows "
                "(dedup_fingerprint,batch_id,format_id,direction,bank_references,warnings,raw_payload) "
                "VALUES (%s,%s,'legacy','unknown',JSON_OBJECT(),JSON_ARRAY('direction_missing'),JSON_OBJECT())"
            )
            fingerprint = "a" * 64
            cursor.execute(row_sql, (fingerprint, batch_id))
            canonical_row_id = cursor.lastrowid
            cursor.execute(
                "SELECT resolved_counterparty_account FROM finance_import_rows WHERE id=%s",
                (canonical_row_id,),
            )
            assert cursor.fetchone() == (None,)
            with pytest.raises(pymysql.IntegrityError):
                cursor.execute(row_sql, (fingerprint, batch_id))
            with pytest.raises(pymysql.IntegrityError):
                cursor.execute(row_sql, (None, batch_id))

            occurrence_sql = (
                "INSERT INTO finance_import_occurrences "
                "(batch_id,finance_import_row_id,source_file,sheet_name,source_row,warnings) "
                "VALUES (%s,%s,'history.xlsx','statement',4,JSON_ARRAY())"
            )
            cursor.execute(occurrence_sql, (batch_id, canonical_row_id))
            with pytest.raises(pymysql.IntegrityError):
                cursor.execute(occurrence_sql, (batch_id, canonical_row_id))

            for statement in _statements():
                cursor.execute(statement)
            cursor.execute(
                "SELECT IS_NULLABLE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='finance_import_rows' "
                "AND COLUMN_NAME='dedup_fingerprint'",
                (database,),
            )
            assert cursor.fetchone() == ("NO",)
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
        finally:
            connection.close()


def test_mysql_upgrade_rejects_existing_null_fingerprint_without_rewriting_it():
    connection = _connection()
    database = f"codex_staging_upgrade_{uuid.uuid4().hex}"
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cursor.execute(f"USE `{database}`")
            cursor.execute(
                "CREATE TABLE finance_import_rows ("
                "id BIGINT AUTO_INCREMENT PRIMARY KEY, "
                "dedup_fingerprint CHAR(64) NULL)"
            )
            cursor.execute("INSERT INTO finance_import_rows (dedup_fingerprint) VALUES (NULL)")

            statements = _statements()
            alter = next(
                statement for statement in statements
                if "ALTER TABLE finance_import_rows" in statement
            )
            with pytest.raises(pymysql.MySQLError):
                cursor.execute(alter)

            cursor.execute("SELECT dedup_fingerprint FROM finance_import_rows")
            assert cursor.fetchone() == (None,)
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
        finally:
            connection.close()


def test_mysql_resolved_account_upgrade_is_additive_replayable_and_does_not_backfill():
    connection = _connection()
    database = f"codex_staging_resolved_account_{uuid.uuid4().hex}"
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cursor.execute(f"USE `{database}`")
            cursor.execute(
                "CREATE TABLE finance_import_rows ("
                "id BIGINT AUTO_INCREMENT PRIMARY KEY, "
                "counterparty_account VARCHAR(191) NULL)"
            )
            cursor.execute(
                "INSERT INTO finance_import_rows (counterparty_account) VALUES ('012345678901')"
            )

            statements = _statements()
            start = next(
                index
                for index, statement in enumerate(statements)
                if "SET @resolved_counterparty_account_exists" in statement
            )
            upgrade = statements[start : start + 5]
            for statement in upgrade:
                cursor.execute(statement)
            for statement in upgrade:
                cursor.execute(statement)

            cursor.execute(
                "SELECT counterparty_account, resolved_counterparty_account "
                "FROM finance_import_rows"
            )
            assert cursor.fetchone() == ("012345678901", None)
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
        finally:
            connection.close()


def test_schema_declares_replayable_not_null_upgrade_without_fabricating_values():
    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    assert "dedup_fingerprint CHAR(64) NOT NULL" in sql
    assert "MODIFY COLUMN dedup_fingerprint CHAR(64) NOT NULL" in sql
    assert "dedup_fingerprint IS NULL" not in sql
    assert "UPDATE finance_import_rows" not in sql


def test_schema_declares_nullable_replayable_resolved_account_upgrade():
    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    assert "resolved_counterparty_account VARCHAR(191) NULL" in sql
    assert "PREPARE add_resolved_counterparty_account" in sql
    assert "information_schema.COLUMNS" in sql
    assert "UPDATE finance_import_rows SET resolved_counterparty_account" not in sql
