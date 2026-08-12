"""Migrate bootstrap receipts to preserve adopted Scheduling versions."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.mysql.mysql_adapter import get_connection

_OLD_CONSTRAINT = "chk_case_architecture_receipt_initial_versions"
_NEW_CONSTRAINT = "chk_case_architecture_receipt_bootstrap_versions"


def main() -> None:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            if _constraint_exists(cursor, _NEW_CONSTRAINT):
                print("already_applied")
                return
            if not _constraint_exists(cursor, _OLD_CONSTRAINT):
                raise RuntimeError("bootstrap_receipt_constraint_state_unknown")
            cursor.execute(
                "ALTER TABLE case_architecture_bootstrap_receipts "
                f"DROP CHECK {_OLD_CONSTRAINT}"
            )
            cursor.execute(
                "ALTER TABLE case_architecture_bootstrap_receipts "
                f"ADD CONSTRAINT {_NEW_CONSTRAINT} "
                "CHECK (client_finance_version = 0 AND payroll_version = 0)"
            )
        connection.commit()
        print("applied")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _constraint_exists(cursor, constraint_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM information_schema.table_constraints "
        "WHERE constraint_schema = DATABASE() "
        "AND table_name = 'case_architecture_bootstrap_receipts' "
        "AND constraint_name = %s AND constraint_type = 'CHECK'",
        (constraint_name,),
    )
    return cursor.fetchone() is not None


if __name__ == "__main__":
    main()
