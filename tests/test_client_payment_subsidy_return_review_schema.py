from pathlib import Path

from scripts.init_db import load_schema_parts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"
MIGRATION_PATH = (
    PROJECT_ROOT
    / "db"
    / "schema_parts"
    / "97_client_payment_subsidy_return_review.sql"
)


class RecordingCursor:
    def __init__(self):
        self.executed = []

    def execute(self, statement):
        self.executed.append(statement)


def _migration_sql():
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_migration_adds_nullable_review_fields_matching_payment_schema():
    migration = _migration_sql()
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    status_definition = (
        "subsidy_return_review_status` ENUM(''review_required'') NULL"
    )
    assert status_definition in migration
    assert "subsidy_return_review_status ENUM('review_required') NULL" in schema
    assert "subsidy_return_review_reason` TEXT NULL" in migration
    assert "subsidy_return_review_reason TEXT NULL" in schema


def test_each_column_is_guarded_for_idempotent_replay():
    sql = _migration_sql()

    assert sql.count("INFORMATION_SCHEMA.COLUMNS") == 2
    assert "COLUMN_NAME = 'subsidy_return_review_status'" in sql
    assert "COLUMN_NAME = 'subsidy_return_review_reason'" in sql
    assert sql.count("'SELECT 1'") == 2
    assert sql.count("EXECUTE subsidy_return_review_stmt") == 2
    assert sql.count("DEALLOCATE PREPARE subsidy_return_review_stmt") == 2


def test_migration_is_additive_and_never_rewrites_client_payment_history():
    ddl = _migration_sql().upper()

    assert "ALTER TABLE `CLIENT_PAYMENTS` ADD COLUMN" in ddl
    assert "UPDATE CLIENT_PAYMENTS" not in ddl
    assert "DELETE FROM CLIENT_PAYMENTS" not in ddl
    assert "DROP TABLE" not in ddl
    assert "DROP COLUMN" not in ddl
    assert "TRUNCATE TABLE" not in ddl


def test_schema_parts_loader_parses_migration_in_stable_replay_order():
    cursor = RecordingCursor()
    parts_dir = MIGRATION_PATH.parent

    loaded_parts = load_schema_parts(cursor, parts_dir)
    assert MIGRATION_PATH.name in loaded_parts
    first_run = list(cursor.executed)
    assert any("subsidy_return_review_status" in statement for statement in first_run)

    assert load_schema_parts(cursor, parts_dir) == loaded_parts
    assert cursor.executed == first_run + first_run
