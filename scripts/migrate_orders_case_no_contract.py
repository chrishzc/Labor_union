"""Remove orders.id and child order_id columns after the case_no cutover.

Run with ``--check`` first.  ``--apply`` is idempotent and refuses to contract
the schema while any case_no relation is missing or inconsistent.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "1234"),
    "database": os.getenv("DB_DATABASE", "union_db"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}
LOCK_NAME = "orders_case_no_contract"


def scalar(cursor, query: str, params: tuple = ()) -> int:
    cursor.execute(query, params)
    return int(next(iter(cursor.fetchone().values())))


def column_exists(cursor, table: str, column: str) -> bool:
    return bool(scalar(cursor, """
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s
    """, (table, column)))


def index_exists(cursor, table: str, index: str) -> bool:
    return bool(scalar(cursor, """
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s
    """, (table, index)))


def foreign_keys_for_column(cursor, table: str, column: str) -> list[str]:
    cursor.execute("""
        SELECT DISTINCT constraint_name AS fk_name
        FROM information_schema.key_column_usage
        WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s
          AND referenced_table_name IS NOT NULL
    """, (table, column))
    return [row["fk_name"] for row in cursor.fetchall()]


def snapshot(cursor) -> tuple[dict[str, int], str]:
    counts = {}
    digest = hashlib.sha256()
    queries = {
        "orders": "SELECT case_no, client_id, COALESCE(staff_id, '') staff_id FROM orders ORDER BY case_no",
        "matching_records": "SELECT id, case_no, staff_id FROM matching_records ORDER BY id",
        "staff_schedule": "SELECT id, case_no, staff_id, work_date FROM staff_schedule ORDER BY id",
    }
    for table, query in queries.items():
        cursor.execute(query)
        rows = cursor.fetchall()
        counts[table] = len(rows)
        for row in rows:
            digest.update((table + "|" + "|".join(str(value) for value in row.values()) + "\n").encode())
    return counts, digest.hexdigest()


def blockers(cursor) -> list[str]:
    issues = []
    for table in ("orders", "matching_records", "staff_schedule"):
        if not column_exists(cursor, table, "case_no"):
            issues.append(f"{table}.case_no is missing")
    if issues:
        return issues

    checks = (
        ("orders with empty case_no", "SELECT COUNT(*) FROM orders WHERE case_no IS NULL OR TRIM(case_no) = ''"),
        ("duplicate orders.case_no", "SELECT COUNT(*) FROM (SELECT case_no FROM orders GROUP BY case_no HAVING COUNT(*) > 1) d"),
        ("orders whose case_no differs from clients", """
            SELECT COUNT(*) FROM orders o JOIN clients c ON c.id = o.client_id
            WHERE o.case_no <> c.case_no
        """),
        ("matching rows without an order", """
            SELECT COUNT(*) FROM matching_records m LEFT JOIN orders o ON o.case_no = m.case_no
            WHERE m.case_no IS NULL OR o.case_no IS NULL
        """),
        ("schedule rows without an order", """
            SELECT COUNT(*) FROM staff_schedule s LEFT JOIN orders o ON o.case_no = s.case_no
            WHERE s.case_no IS NULL OR o.case_no IS NULL
        """),
    )
    for label, query in checks:
        count = scalar(cursor, query)
        if count:
            issues.append(f"{count} {label}")
    return issues


def extract_view_statement() -> str:
    schema = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    marker = "CREATE OR REPLACE VIEW v_order_details AS"
    start = schema.index(marker)
    end = schema.index(";", start) + 1
    return schema[start:end]


def drop_transition_triggers(cursor) -> None:
    names = (
        "trg_clients_case_no_bu", "trg_clients_case_no_au",
        "trg_orders_case_no_bi", "trg_orders_case_no_bu",
        "trg_matching_case_no_bi", "trg_matching_case_no_bu",
        "trg_schedule_case_no_bi", "trg_schedule_case_no_bu",
        "trg_orders_matching_case_no_au", "trg_orders_schedule_case_no_au",
    )
    for name in names:
        cursor.execute(f"DROP TRIGGER IF EXISTS `{name}`")


def drop_legacy_child_column(cursor, table: str) -> None:
    if not column_exists(cursor, table, "order_id"):
        cursor.execute(f"ALTER TABLE `{table}` MODIFY `case_no` VARCHAR(50) NOT NULL")
        return
    for constraint in foreign_keys_for_column(cursor, table, "order_id"):
        cursor.execute(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{constraint}`")
    cursor.execute(
        f"ALTER TABLE `{table}` DROP COLUMN `order_id`, MODIFY `case_no` VARCHAR(50) NOT NULL"
    )


def contract_orders(cursor) -> None:
    if not column_exists(cursor, "orders", "id"):
        cursor.execute("ALTER TABLE orders MODIFY case_no VARCHAR(50) NOT NULL")
        return
    # AUTO_INCREMENT must be removed before its primary-key index can be dropped.
    cursor.execute("ALTER TABLE orders MODIFY id INT NOT NULL")
    cursor.execute("ALTER TABLE orders DROP PRIMARY KEY")
    cursor.execute("ALTER TABLE orders DROP COLUMN id, MODIFY case_no VARCHAR(50) NOT NULL, ADD PRIMARY KEY (case_no)")
    if index_exists(cursor, "orders", "uq_orders_case_no"):
        cursor.execute("ALTER TABLE orders DROP INDEX uq_orders_case_no")


def apply_contract(connection) -> tuple[tuple[dict[str, int], str], tuple[dict[str, int], str]]:
    with connection.cursor() as cursor:
        if scalar(cursor, "SELECT GET_LOCK(%s, 10)", (LOCK_NAME,)) != 1:
            raise RuntimeError("could not acquire migration lock")
        try:
            issues = blockers(cursor)
            if issues:
                raise RuntimeError("; ".join(issues))
            before = snapshot(cursor)
            cursor.execute("DROP VIEW IF EXISTS v_order_details")
            drop_transition_triggers(cursor)
            drop_legacy_child_column(cursor, "matching_records")
            drop_legacy_child_column(cursor, "staff_schedule")
            contract_orders(cursor)
            cursor.execute(extract_view_statement())
            connection.commit()
            after = snapshot(cursor)
            if before != after:
                raise RuntimeError(f"data snapshot changed: before={before}, after={after}")
            return before, after
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))


def contract_complete(cursor) -> bool:
    return not any(
        column_exists(cursor, table, column)
        for table, column in (
            ("orders", "id"),
            ("matching_records", "order_id"),
            ("staff_schedule", "order_id"),
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    connection = pymysql.connect(**DB_CONFIG)
    try:
        with connection.cursor() as cursor:
            issues = blockers(cursor)
            counts, checksum = snapshot(cursor)
            complete = contract_complete(cursor)
        print(f"rows: {counts}")
        print(f"case_no snapshot sha256: {checksum}")
        if issues:
            print("BLOCKED: " + "; ".join(issues), file=sys.stderr)
            return 1
        if args.check:
            print("CONTRACT COMPLETE" if complete else "READY TO DROP LEGACY ORDER COLUMNS")
            return 0
        before, after = apply_contract(connection)
        print(f"DONE: legacy order columns removed; snapshot preserved ({before} == {after}).")
        return 0
    except Exception as exc:
        connection.rollback()
        print(f"Migration failed: {exc}", file=sys.stderr)
        print("MySQL DDL may be partially applied; inspect and rerun.", file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
