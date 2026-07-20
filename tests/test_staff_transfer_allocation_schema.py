import os
from pathlib import Path
import uuid

from dotenv import load_dotenv
import pymysql
import pytest

from scripts.init_db import load_schema_parts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    PROJECT_ROOT / "db" / "schema_parts" / "50_staff_transfer_allocations.sql"
)


class RecordingCursor:
    def __init__(self):
        self.executed = []

    def execute(self, statement):
        self.executed.append(statement)


def _schema_sql():
    return SCHEMA_PATH.read_text(encoding="utf-8")


def _schema_statements():
    return [
        statement.strip()
        for statement in _schema_sql().split(";")
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


def test_unique_target_includes_component_type():
    compact = "".join(_schema_sql().split())

    assert (
        "UNIQUEKEYuq_staff_transfer_allocation_target("
        "transfer_id,settlement_detail_id,component_type)"
    ) in compact


def test_existing_two_column_index_is_migrated_without_data_rewrite():
    sql = _schema_sql()
    upper_sql = sql.upper()

    assert "INFORMATION_SCHEMA.STATISTICS" in sql
    assert "GROUP_CONCAT(" in sql
    assert "ORDER BY SEQ_IN_INDEX" in sql
    assert "'transfer_id,settlement_detail_id'" in sql
    assert (
        "DROP INDEX `uq_staff_transfer_allocation_target`, "
        "ADD UNIQUE KEY `uq_staff_transfer_allocation_target` "
        "(`transfer_id`, `settlement_detail_id`, `component_type`)"
    ) in sql
    assert "UPDATE STAFF_TRANSFER_ALLOCATIONS" not in upper_sql
    assert "DELETE FROM STAFF_TRANSFER_ALLOCATIONS" not in upper_sql
    assert "DROP TABLE" not in upper_sql


def test_index_migration_is_idempotent_and_recovers_a_missing_index():
    sql = _schema_sql()

    assert "WHEN @staff_transfer_allocation_target_columns IS NULL" in sql
    assert "ELSE 'SELECT 1'" in sql
    assert "PREPARE staff_transfer_allocation_index_stmt" in sql
    assert "EXECUTE staff_transfer_allocation_index_stmt" in sql
    assert "DEALLOCATE PREPARE staff_transfer_allocation_index_stmt" in sql


def test_schema_parts_loader_can_parse_and_replay_index_migration():
    cursor = RecordingCursor()

    loaded_parts = load_schema_parts(cursor, SCHEMA_PATH.parent)
    assert SCHEMA_PATH.name in loaded_parts
    first_run_statements = list(cursor.executed)
    assert first_run_statements

    assert load_schema_parts(cursor, SCHEMA_PATH.parent) == loaded_parts
    assert cursor.executed == first_run_statements + first_run_statements


def test_mysql_migrates_old_index_preserves_rows_and_is_replayable():
    connection = _connection()
    database = f"codex_staff_allocation_{uuid.uuid4().hex}"
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 "
                "COLLATE utf8mb4_unicode_ci"
            )
            cursor.execute(f"USE `{database}`")
            cursor.execute(
                "CREATE TABLE staff_actual_transfers ("
                "id BIGINT AUTO_INCREMENT PRIMARY KEY"
                ") ENGINE=InnoDB"
            )
            cursor.execute(
                "CREATE TABLE staff_monthly_settlement_details ("
                "id BIGINT AUTO_INCREMENT PRIMARY KEY"
                ") ENGINE=InnoDB"
            )
            cursor.execute(
                "CREATE TABLE staff_transfer_allocations ("
                "id BIGINT AUTO_INCREMENT PRIMARY KEY, "
                "transfer_id BIGINT NOT NULL, "
                "settlement_detail_id BIGINT NOT NULL, "
                "allocated_amount DECIMAL(12, 2) NOT NULL, "
                "component_type ENUM('regular_salary','legacy_subsidy',"
                "'floor_fee','adjustment','unknown') NOT NULL DEFAULT 'unknown', "
                "allocation_method ENUM('explicit','inferred') "
                "NOT NULL DEFAULT 'explicit', "
                "review_status ENUM('approved','review_required','rejected') "
                "NOT NULL DEFAULT 'review_required', "
                "reversal_of_allocation_id BIGINT NULL, "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP "
                "ON UPDATE CURRENT_TIMESTAMP, "
                "UNIQUE KEY uq_staff_transfer_allocation_target "
                "(transfer_id, settlement_detail_id)"
                ") ENGINE=InnoDB"
            )
            cursor.execute(
                "INSERT INTO staff_transfer_allocations "
                "(transfer_id, settlement_detail_id, allocated_amount, "
                "component_type, review_status) "
                "VALUES (1, 10, 500.00, 'regular_salary', 'approved')"
            )

            for statement in _schema_statements():
                cursor.execute(statement)
            for statement in _schema_statements():
                cursor.execute(statement)

            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=%s "
                "AND TABLE_NAME='staff_transfer_allocations' "
                "AND INDEX_NAME='uq_staff_transfer_allocation_target' "
                "ORDER BY SEQ_IN_INDEX",
                (database,),
            )
            assert cursor.fetchall() == (
                ("transfer_id",),
                ("settlement_detail_id",),
                ("component_type",),
            )
            cursor.execute(
                "SELECT transfer_id, settlement_detail_id, allocated_amount, "
                "component_type, review_status "
                "FROM staff_transfer_allocations"
            )
            assert cursor.fetchall() == (
                (1, 10, 500.00, "regular_salary", "approved"),
            )
            cursor.execute(
                "INSERT INTO staff_transfer_allocations "
                "(transfer_id, settlement_detail_id, allocated_amount, "
                "component_type, review_status) "
                "VALUES (1, 10, 100.00, 'floor_fee', 'approved')"
            )
            with pytest.raises(pymysql.IntegrityError):
                cursor.execute(
                    "INSERT INTO staff_transfer_allocations "
                    "(transfer_id, settlement_detail_id, allocated_amount, "
                    "component_type, review_status) "
                    "VALUES (1, 10, 50.00, 'floor_fee', 'approved')"
                )
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
        finally:
            connection.close()
