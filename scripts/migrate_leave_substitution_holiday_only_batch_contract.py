"""Allow persisted Holiday Query-only leave/substitution batches."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.mysql.mysql_adapter import get_connection

_CONSTRAINT = "chk_scheduling_leave_batch_identity"


def main() -> None:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            if not _constraint_exists(cursor):
                raise RuntimeError("leave_substitution_batch_constraint_missing")
            cursor.execute(
                "ALTER TABLE scheduling_leave_substitution_batches "
                f"DROP CHECK {_CONSTRAINT}"
            )
            cursor.execute(
                "ALTER TABLE scheduling_leave_substitution_batches "
                f"ADD CONSTRAINT {_CONSTRAINT} "
                "CHECK (item_count >= 0 "
                "AND CHAR_LENGTH(TRIM(batch_key)) > 0 "
                "AND CHAR_LENGTH(TRIM(actor)) > 0 "
                "AND CHAR_LENGTH(TRIM(reason)) > 0 "
                "AND CHAR_LENGTH(TRIM(correlation_id)) > 0)"
            )
        connection.commit()
        print("applied")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _constraint_exists(cursor) -> bool:
    cursor.execute(
        "SELECT 1 FROM information_schema.table_constraints "
        "WHERE constraint_schema = DATABASE() "
        "AND table_name = 'scheduling_leave_substitution_batches' "
        "AND constraint_name = %s AND constraint_type = 'CHECK'",
        (_CONSTRAINT,),
    )
    return cursor.fetchone() is not None


if __name__ == "__main__":
    main()
