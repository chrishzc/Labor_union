"""Phase 2: add and backfill case_no relations without dropping legacy IDs.

Run ``python scripts/migrate_orders_case_no_expand.py --check`` first, then
``--apply``.  This is an expand-only, idempotent migration: ``orders.id`` and
the child ``order_id`` columns remain available until the application cutover.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from collections.abc import Iterable

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

LOCK_NAME = "orders_case_no_expand_v2"


def scalar(cursor, query: str, params: tuple = ()) -> int:
    cursor.execute(query, params)
    return int(next(iter(cursor.fetchone().values())))


def column_exists(cursor, table: str, column: str) -> bool:
    return bool(
        scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = %s
              AND column_name = %s
            """,
            (table, column),
        )
    )


def index_exists(cursor, table: str, index: str) -> bool:
    return bool(
        scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = %s
              AND index_name = %s
            """,
            (table, index),
        )
    )


def foreign_key_exists(cursor, table: str, constraint: str) -> bool:
    return bool(
        scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM information_schema.table_constraints
            WHERE constraint_schema = DATABASE()
              AND table_name = %s
              AND constraint_name = %s
              AND constraint_type = 'FOREIGN KEY'
            """,
            (table, constraint),
        )
    )


def trigger_exists(cursor, trigger: str) -> bool:
    return bool(
        scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM information_schema.triggers
            WHERE trigger_schema = DATABASE() AND trigger_name = %s
            """,
            (trigger,),
        )
    )


def trigger_signature(cursor, trigger: str) -> tuple[str, str, str, str] | None:
    cursor.execute(
        """
        SELECT event_object_table AS target_table,
               action_timing AS trigger_timing,
               event_manipulation AS trigger_event,
               action_statement AS trigger_action
        FROM information_schema.triggers
        WHERE trigger_schema = DATABASE() AND trigger_name = %s
        """,
        (trigger,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    action = " ".join(row["trigger_action"].split()).lower()
    return row["target_table"], row["trigger_timing"], row["trigger_event"], action


def index_signature(cursor, table: str, index: str) -> tuple[bool, tuple[str, ...]] | None:
    cursor.execute(
        """
        SELECT non_unique AS is_non_unique, column_name AS indexed_column
        FROM information_schema.statistics
        WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s
        ORDER BY seq_in_index
        """,
        (table, index),
    )
    rows = cursor.fetchall()
    if not rows:
        return None
    return not bool(rows[0]["is_non_unique"]), tuple(row["indexed_column"] for row in rows)


def foreign_key_signature(cursor, table: str, constraint: str) -> tuple[str, str, str, str] | None:
    cursor.execute(
        """
        SELECT k.column_name AS local_column,
               k.referenced_table_name AS referenced_table,
               k.referenced_column_name AS referenced_column,
               r.update_rule AS update_action,
               r.delete_rule AS delete_action
        FROM information_schema.key_column_usage k
        JOIN information_schema.referential_constraints r
          ON r.constraint_schema = k.constraint_schema
         AND r.table_name = k.table_name
         AND r.constraint_name = k.constraint_name
        WHERE k.constraint_schema = DATABASE()
          AND k.table_name = %s AND k.constraint_name = %s
        """,
        (table, constraint),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return (
        row["local_column"],
        f"{row['referenced_table']}.{row['referenced_column']}",
        row["update_action"],
        row["delete_action"],
    )


def schema_object_blockers(cursor) -> list[str]:
    required_columns = (
        ("orders", "case_no"),
        ("matching_records", "case_no"),
        ("staff_schedule", "case_no"),
    )
    if not all(column_exists(cursor, table, column) for table, column in required_columns):
        return []

    blockers = []
    expected_indexes = {
        ("orders", "uq_orders_case_no"): (True, ("case_no",)),
        ("matching_records", "uq_matching_case_staff"): (True, ("case_no", "staff_id")),
        ("staff_schedule", "idx_schedule_case_no"): (False, ("case_no",)),
    }
    for (table, name), expected in expected_indexes.items():
        if index_signature(cursor, table, name) != expected:
            blockers.append(f"index {table}.{name} is missing or has the wrong definition")

    expected_fks = {
        ("orders", "fk_orders_case_no"): ("case_no", "clients.case_no", "CASCADE", "RESTRICT"),
        ("matching_records", "fk_matching_case_no"): ("case_no", "orders.case_no", "CASCADE", "CASCADE"),
        ("staff_schedule", "fk_schedule_case_no"): ("case_no", "orders.case_no", "CASCADE", "CASCADE"),
    }
    for (table, name), expected in expected_fks.items():
        if foreign_key_signature(cursor, table, name) != expected:
            blockers.append(f"foreign key {table}.{name} is missing or has the wrong definition")

    expected_triggers = {
        "trg_clients_case_no_bu": ("clients", "BEFORE", "UPDATE", "old.case_no"),
        "trg_clients_case_no_au": ("clients", "AFTER", "UPDATE", "update orders"),
        "trg_orders_case_no_bi": ("orders", "BEFORE", "INSERT", "c.id = new.client_id"),
        "trg_orders_case_no_bu": ("orders", "BEFORE", "UPDATE", "c.id = new.client_id"),
        "trg_matching_case_no_bi": ("matching_records", "BEFORE", "INSERT", "o.id = new.order_id"),
        "trg_matching_case_no_bu": ("matching_records", "BEFORE", "UPDATE", "o.id = new.order_id"),
        "trg_schedule_case_no_bi": ("staff_schedule", "BEFORE", "INSERT", "o.id = new.order_id"),
        "trg_schedule_case_no_bu": ("staff_schedule", "BEFORE", "UPDATE", "o.id = new.order_id"),
        "trg_orders_matching_case_no_au": ("orders", "AFTER", "UPDATE", "update matching_records"),
        "trg_orders_schedule_case_no_au": ("orders", "AFTER", "UPDATE", "update staff_schedule"),
    }
    for name, expected in expected_triggers.items():
        actual = trigger_signature(cursor, name)
        if not actual or actual[:3] != expected[:3] or expected[3] not in actual[3]:
            blockers.append(f"trigger {name} is missing or has the wrong definition")
    return blockers


def mapping_checksum(cursor) -> str:
    cursor.execute(
        """
        SELECT o.id, o.client_id, c.case_no
        FROM orders o
        LEFT JOIN clients c ON c.id = o.client_id
        ORDER BY o.id
        """
    )
    digest = hashlib.sha256()
    for row in cursor.fetchall():
        digest.update(
            f"{row['id']}|{row['client_id']}|{row['case_no'] or ''}\n".encode()
        )
    return digest.hexdigest()


def source_blockers(cursor) -> list[str]:
    """Validate the legacy mapping before any DDL is attempted."""
    checks = (
        (
            "orders without a usable clients.case_no",
            """
            SELECT COUNT(*)
            FROM orders o
            LEFT JOIN clients c ON c.id = o.client_id
            WHERE c.id IS NULL OR c.case_no IS NULL OR TRIM(c.case_no) = ''
            """,
        ),
        (
            "clients.case_no values used by more than one order",
            """
            SELECT COUNT(*) FROM (
                SELECT c.case_no
                FROM orders o
                JOIN clients c ON c.id = o.client_id
                GROUP BY c.case_no
                HAVING COUNT(*) > 1
            ) duplicates
            """,
        ),
        (
            "orders whose clients.case_no is not a trimmed 9-digit number",
            """
            SELECT COUNT(*)
            FROM orders o
            JOIN clients c ON c.id = o.client_id
            WHERE c.case_no <> TRIM(c.case_no)
               OR c.case_no NOT REGEXP '^[0-9]{9}$'
            """,
        ),
        (
            "duplicate matching rows for the same case_no and staff",
            """
            SELECT COUNT(*) FROM (
                SELECT c.case_no, mr.staff_id
                FROM matching_records mr
                JOIN orders o ON o.id = mr.order_id
                JOIN clients c ON c.id = o.client_id
                GROUP BY c.case_no, mr.staff_id
                HAVING COUNT(*) > 1
            ) duplicates
            """,
        ),
        (
            "matching rows whose order_id has no order",
            """
            SELECT COUNT(*)
            FROM matching_records mr
            LEFT JOIN orders o ON o.id = mr.order_id
            WHERE o.id IS NULL
            """,
        ),
        (
            "schedule rows whose order_id has no order",
            """
            SELECT COUNT(*)
            FROM staff_schedule ss
            LEFT JOIN orders o ON o.id = ss.order_id
            WHERE o.id IS NULL
            """,
        ),
        (
            "schedule rows whose staff_id differs from the assigned order staff",
            """
            SELECT COUNT(*)
            FROM staff_schedule ss
            JOIN orders o ON o.id = ss.order_id
            WHERE o.staff_id IS NOT NULL AND ss.staff_id <> o.staff_id
            """,
        ),
        (
            "payment rows whose case_no has no client",
            """
            SELECT COUNT(*)
            FROM payments p
            LEFT JOIN clients c ON c.case_no = p.case_no
            WHERE c.id IS NULL
            """,
        ),
    )
    blockers = []
    for label, query in checks:
        count = scalar(cursor, query)
        if count:
            blockers.append(f"{count} {label}")
    return blockers


def expanded_blockers(cursor) -> list[str]:
    """Validate populated case_no columns when they already exist."""
    checks: list[tuple[str, str]] = []
    if column_exists(cursor, "orders", "case_no"):
        checks.append(
            (
                "orders.case_no values are missing or differ from clients.case_no",
                """
                SELECT COUNT(*)
                FROM orders o
                JOIN clients c ON c.id = o.client_id
                WHERE o.case_no IS NULL OR o.case_no = '' OR o.case_no <> c.case_no
                """,
            )
        )
    if column_exists(cursor, "matching_records", "case_no"):
        checks.append(
            (
                "matching_records.case_no values are missing or differ from orders.case_no",
                """
                SELECT COUNT(*)
                FROM matching_records mr
                JOIN orders o ON o.id = mr.order_id
                WHERE mr.case_no IS NULL OR mr.case_no = '' OR mr.case_no <> o.case_no
                """,
            )
        )
    if column_exists(cursor, "staff_schedule", "case_no"):
        checks.append(
            (
                "staff_schedule.case_no values are missing or differ from orders.case_no",
                """
                SELECT COUNT(*)
                FROM staff_schedule ss
                JOIN orders o ON o.id = ss.order_id
                WHERE ss.case_no IS NULL OR ss.case_no = '' OR ss.case_no <> o.case_no
                """,
            )
        )
    blockers = []
    for label, query in checks:
        count = scalar(cursor, query)
        if count:
            blockers.append(f"{count} {label}")
    return blockers


def ensure_column(cursor, table: str, definition: str, column: str) -> None:
    if not column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN {definition}")


def ensure_index(cursor, table: str, index: str, definition: str) -> None:
    if not index_exists(cursor, table, index):
        cursor.execute(f"ALTER TABLE `{table}` ADD {definition}")


def ensure_foreign_key(cursor, table: str, constraint: str, definition: str) -> None:
    if not foreign_key_exists(cursor, table, constraint):
        cursor.execute(f"ALTER TABLE `{table}` ADD CONSTRAINT `{constraint}` {definition}")


def install_transition_triggers(cursor, selected: set[str] | None = None) -> None:
    """Keep case_no populated while legacy writers still submit only IDs."""
    triggers = {
        "trg_clients_case_no_bu": """
            CREATE TRIGGER trg_clients_case_no_bu
            BEFORE UPDATE ON clients FOR EACH ROW
            SET NEW.case_no = IF(
                EXISTS(SELECT 1 FROM orders o WHERE o.client_id = OLD.id)
                    AND OLD.case_no IS NOT NULL AND OLD.case_no <> ''
                    AND (NEW.case_no IS NULL OR NEW.case_no = ''),
                OLD.case_no,
                NEW.case_no
            )
        """,
        "trg_orders_case_no_bi": """
            CREATE TRIGGER trg_orders_case_no_bi
            BEFORE INSERT ON orders FOR EACH ROW
            SET NEW.case_no = (SELECT c.case_no FROM clients c WHERE c.id = NEW.client_id)
        """,
        "trg_orders_case_no_bu": """
            CREATE TRIGGER trg_orders_case_no_bu
            BEFORE UPDATE ON orders FOR EACH ROW
            SET NEW.case_no = (SELECT c.case_no FROM clients c WHERE c.id = NEW.client_id)
        """,
        "trg_matching_case_no_bi": """
            CREATE TRIGGER trg_matching_case_no_bi
            BEFORE INSERT ON matching_records FOR EACH ROW
            SET NEW.case_no = (SELECT o.case_no FROM orders o WHERE o.id = NEW.order_id)
        """,
        "trg_matching_case_no_bu": """
            CREATE TRIGGER trg_matching_case_no_bu
            BEFORE UPDATE ON matching_records FOR EACH ROW
            SET NEW.case_no = (SELECT o.case_no FROM orders o WHERE o.id = NEW.order_id)
        """,
        "trg_schedule_case_no_bi": """
            CREATE TRIGGER trg_schedule_case_no_bi
            BEFORE INSERT ON staff_schedule FOR EACH ROW
            SET NEW.case_no = (SELECT o.case_no FROM orders o WHERE o.id = NEW.order_id)
        """,
        "trg_schedule_case_no_bu": """
            CREATE TRIGGER trg_schedule_case_no_bu
            BEFORE UPDATE ON staff_schedule FOR EACH ROW
            SET NEW.case_no = (SELECT o.case_no FROM orders o WHERE o.id = NEW.order_id)
        """,
        "trg_clients_case_no_au": """
            CREATE TRIGGER trg_clients_case_no_au
            AFTER UPDATE ON clients FOR EACH ROW
            UPDATE orders
            SET case_no = NEW.case_no
            WHERE client_id = NEW.id
              AND NEW.case_no IS NOT NULL AND NEW.case_no <> ''
              AND (case_no IS NULL OR case_no = '')
        """,
        "trg_orders_matching_case_no_au": """
            CREATE TRIGGER trg_orders_matching_case_no_au
            AFTER UPDATE ON orders FOR EACH ROW
            UPDATE matching_records
            SET case_no = NEW.case_no
            WHERE order_id = NEW.id
              AND NEW.case_no IS NOT NULL AND NEW.case_no <> ''
              AND (case_no IS NULL OR case_no = '')
        """,
        "trg_orders_schedule_case_no_au": """
            CREATE TRIGGER trg_orders_schedule_case_no_au
            AFTER UPDATE ON orders FOR EACH ROW
            UPDATE staff_schedule
            SET case_no = NEW.case_no
            WHERE order_id = NEW.id
              AND NEW.case_no IS NOT NULL AND NEW.case_no <> ''
              AND (case_no IS NULL OR case_no = '')
        """,
    }
    for name, statement in triggers.items():
        if selected is None or name in selected:
            cursor.execute(f"DROP TRIGGER IF EXISTS `{name}`")
            cursor.execute(statement)


def apply_migration(connection) -> tuple[str, str]:
    with connection.cursor() as cursor:
        if scalar(cursor, "SELECT GET_LOCK(%s, 10)", (LOCK_NAME,)) != 1:
            raise RuntimeError("could not acquire the migration lock")
        try:
            blockers = source_blockers(cursor)
            if blockers:
                raise RuntimeError("; ".join(blockers))
            before = mapping_checksum(cursor)

            ensure_column(
                cursor,
                "orders",
                "`case_no` VARCHAR(50) NULL COMMENT '過渡期案件識別碼；對應 clients.case_no' AFTER `id`",
                "case_no",
            )
            install_transition_triggers(
                cursor,
                {
                    "trg_clients_case_no_bu",
                    "trg_clients_case_no_au",
                    "trg_orders_case_no_bi",
                    "trg_orders_case_no_bu",
                },
            )
            cursor.execute(
                """
                UPDATE orders o JOIN clients c ON c.id = o.client_id
                SET o.case_no = c.case_no
                WHERE o.case_no IS NULL OR o.case_no = '' OR o.case_no <> c.case_no
                """
            )
            ensure_index(
                cursor, "orders", "uq_orders_case_no", "UNIQUE KEY `uq_orders_case_no` (`case_no`)"
            )
            ensure_foreign_key(
                cursor,
                "orders",
                "fk_orders_case_no",
                "FOREIGN KEY (`case_no`) REFERENCES `clients` (`case_no`) ON UPDATE CASCADE ON DELETE RESTRICT",
            )

            ensure_column(
                cursor,
                "matching_records",
                "`case_no` VARCHAR(50) NULL COMMENT '過渡期案件識別碼；對應 orders.case_no' AFTER `order_id`",
                "case_no",
            )
            install_transition_triggers(
                cursor,
                {
                    "trg_matching_case_no_bi",
                    "trg_matching_case_no_bu",
                    "trg_orders_matching_case_no_au",
                },
            )
            cursor.execute(
                """
                UPDATE matching_records mr JOIN orders o ON o.id = mr.order_id
                SET mr.case_no = o.case_no
                WHERE mr.case_no IS NULL OR mr.case_no = '' OR mr.case_no <> o.case_no
                """
            )
            ensure_index(
                cursor,
                "matching_records",
                "uq_matching_case_staff",
                "UNIQUE KEY `uq_matching_case_staff` (`case_no`, `staff_id`)",
            )
            ensure_foreign_key(
                cursor,
                "matching_records",
                "fk_matching_case_no",
                "FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON UPDATE CASCADE ON DELETE CASCADE",
            )

            ensure_column(
                cursor,
                "staff_schedule",
                "`case_no` VARCHAR(50) NULL COMMENT '過渡期案件識別碼；對應 orders.case_no' AFTER `order_id`",
                "case_no",
            )
            install_transition_triggers(
                cursor,
                {
                    "trg_schedule_case_no_bi",
                    "trg_schedule_case_no_bu",
                    "trg_orders_schedule_case_no_au",
                },
            )
            cursor.execute(
                """
                UPDATE staff_schedule ss JOIN orders o ON o.id = ss.order_id
                SET ss.case_no = o.case_no
                WHERE ss.case_no IS NULL OR ss.case_no = '' OR ss.case_no <> o.case_no
                """
            )
            ensure_index(
                cursor,
                "staff_schedule",
                "idx_schedule_case_no",
                "KEY `idx_schedule_case_no` (`case_no`)",
            )
            ensure_foreign_key(
                cursor,
                "staff_schedule",
                "fk_schedule_case_no",
                "FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON UPDATE CASCADE ON DELETE CASCADE",
            )

            install_transition_triggers(cursor)
            connection.commit()

            blockers = expanded_blockers(cursor) + schema_object_blockers(cursor)
            if blockers:
                raise RuntimeError("post-migration validation failed: " + "; ".join(blockers))
            after = mapping_checksum(cursor)
            if before != after:
                raise RuntimeError("legacy order/client mapping checksum changed during migration")
            return before, after
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))


def schema_status(cursor) -> Iterable[str]:
    yield f"orders.case_no: {'present' if column_exists(cursor, 'orders', 'case_no') else 'missing'}"
    yield f"matching_records.case_no: {'present' if column_exists(cursor, 'matching_records', 'case_no') else 'missing'}"
    yield f"staff_schedule.case_no: {'present' if column_exists(cursor, 'staff_schedule', 'case_no') else 'missing'}"
    yield f"legacy orders.id: {'present' if column_exists(cursor, 'orders', 'id') else 'missing'}"
    yield f"legacy matching_records.order_id: {'present' if column_exists(cursor, 'matching_records', 'order_id') else 'missing'}"
    yield f"legacy staff_schedule.order_id: {'present' if column_exists(cursor, 'staff_schedule', 'order_id') else 'missing'}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report blockers without changing data")
    mode.add_argument("--apply", action="store_true", help="apply the expand-only migration")
    args = parser.parse_args()

    connection = pymysql.connect(**DB_CONFIG)
    try:
        with connection.cursor() as cursor:
            for line in schema_status(cursor):
                print(line)
            print(f"order/client mapping sha256: {mapping_checksum(cursor)}")
            source_issues = source_blockers(cursor)
            expanded_issues = expanded_blockers(cursor) + schema_object_blockers(cursor)
            expanded_columns_present = all(
                column_exists(cursor, table, "case_no")
                for table in ("orders", "matching_records", "staff_schedule")
            )
        if args.check:
            blockers = source_issues + expanded_issues
            if blockers:
                print("BLOCKED: " + "; ".join(blockers), file=sys.stderr)
                return 1
            if expanded_columns_present:
                print("EXPANSION COMPLETE: data, indexes, foreign keys, and transition triggers are valid.")
            else:
                print("READY TO APPLY: source mappings are safe for the phase-2 expansion.")
            return 0

        if source_issues:
            raise RuntimeError("; ".join(source_issues))
        # Existing expanded columns may be stale; --apply intentionally repairs them.
        before, after = apply_migration(connection)
        print(f"DONE: expand migration applied; mapping checksum preserved ({before} == {after}).")
        print("Legacy IDs remain available until the application cutover.")
        return 0
    except Exception as exc:
        connection.rollback()
        print(f"Migration failed: {exc}", file=sys.stderr)
        print("MySQL DDL may already be partially applied; inspect and rerun this idempotent migration.", file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
