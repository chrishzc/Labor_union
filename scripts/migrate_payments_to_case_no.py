"""Migrate payments from the legacy orders.id link to clients.case_no.

Run ``python scripts/migrate_payments_to_case_no.py --check`` first.  It only
reports blockers.  Use ``--apply`` to run the transactional schema migration.
The migration refuses to discard payments that cannot be mapped to exactly one
client case number.
"""

import argparse
import os
import sys

import pymysql
from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "1234"),
    "database": os.getenv("DB_DATABASE", "union_db"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


def scalar(cursor, query: str) -> int:
    cursor.execute(query)
    return next(iter(cursor.fetchone().values()))


def has_legacy_order_id(cursor) -> bool:
    return bool(scalar(cursor, """
        SELECT COUNT(*) AS count
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'payments' AND column_name = 'order_id'
    """))


def migration_blockers(cursor) -> list[str]:
    blockers = []
    missing_case = scalar(cursor, """
        SELECT COUNT(*) AS count
        FROM payments p
        LEFT JOIN orders o ON p.order_id = o.id
        LEFT JOIN clients c ON o.client_id = c.id
        WHERE (p.case_no IS NULL OR p.case_no = '')
          AND (c.case_no IS NULL OR c.case_no = '')
    """)
    if missing_case:
        blockers.append(f"{missing_case} payment rows cannot be mapped to a clients.case_no")

    cursor.execute("""
        SELECT COALESCE(NULLIF(p.case_no, ''), c.case_no) AS resolved_case_no
        FROM payments p
        LEFT JOIN orders o ON p.order_id = o.id
        LEFT JOIN clients c ON o.client_id = c.id
        GROUP BY resolved_case_no
        HAVING resolved_case_no IS NULL OR COUNT(*) > 1
    """)
    ambiguous = cursor.fetchall()
    if ambiguous:
        blockers.append("payments contain missing or duplicate case_no values; resolve them before migration")

    orphaned_case = scalar(cursor, """
        SELECT COUNT(*) AS count
        FROM payments p
        LEFT JOIN clients c ON p.case_no = c.case_no
        WHERE p.case_no IS NOT NULL AND p.case_no <> '' AND c.id IS NULL
    """)
    if orphaned_case:
        blockers.append(f"{orphaned_case} payment rows reference a case_no absent from clients")
    return blockers


def print_status(cursor) -> list[str]:
    total = scalar(cursor, "SELECT COUNT(*) AS count FROM payments")
    legacy = has_legacy_order_id(cursor)
    print(f"payments rows: {total}")
    print(f"legacy order_id column present: {'yes' if legacy else 'no'}")
    return migration_blockers(cursor) if legacy else []


def drop_foreign_keys_for_column(cursor, column: str) -> None:
    cursor.execute("""
        SELECT constraint_name
        FROM information_schema.key_column_usage
        WHERE table_schema = DATABASE()
          AND table_name = 'payments'
          AND column_name = %s
          AND referenced_table_name IS NOT NULL
    """, (column,))
    for row in cursor.fetchall():
        constraint_name = next(iter(row.values()))
        cursor.execute(f"ALTER TABLE payments DROP FOREIGN KEY `{constraint_name}`")


def apply_migration(connection) -> None:
    with connection.cursor() as cursor:
        if not has_legacy_order_id(cursor):
            return
        blockers = migration_blockers(cursor)
        if blockers:
            raise RuntimeError("; ".join(blockers))

        cursor.execute("""
            UPDATE payments p
            JOIN orders o ON p.order_id = o.id
            JOIN clients c ON o.client_id = c.id
            SET p.case_no = c.case_no
            WHERE p.case_no IS NULL OR p.case_no = ''
        """)
        drop_foreign_keys_for_column(cursor, "order_id")
        cursor.execute("ALTER TABLE payments DROP COLUMN order_id")

        cursor.execute("""
            SELECT index_name
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = 'payments'
              AND column_name = 'case_no'
              AND non_unique = 0
            GROUP BY index_name
        """)
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE payments ADD CONSTRAINT uq_payments_case_no UNIQUE (case_no)")

        cursor.execute("ALTER TABLE payments MODIFY case_no VARCHAR(50) NOT NULL")
        drop_foreign_keys_for_column(cursor, "case_no")
        cursor.execute("""
            ALTER TABLE payments
            ADD CONSTRAINT fk_payments_case_no
            FOREIGN KEY (case_no) REFERENCES clients(case_no)
            ON UPDATE CASCADE ON DELETE RESTRICT
        """)
    connection.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report migration blockers without changing data")
    mode.add_argument("--apply", action="store_true", help="apply the transactional migration")
    args = parser.parse_args()

    connection = pymysql.connect(**DB_CONFIG)
    try:
        with connection.cursor() as cursor:
            blockers = print_status(cursor)
            legacy_order_id = has_legacy_order_id(cursor)
        if args.check:
            if blockers:
                print("BLOCKED: " + "; ".join(blockers), file=sys.stderr)
                return 1
            print("READY: payments can be migrated to case_no." if legacy_order_id else "ALREADY MIGRATED: payments uses case_no only.")
            return 0

        apply_migration(connection)
        print("DONE: payments.order_id was removed; payments.case_no is now the unique foreign key.")
        return 0
    except Exception as exc:
        connection.rollback()
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
