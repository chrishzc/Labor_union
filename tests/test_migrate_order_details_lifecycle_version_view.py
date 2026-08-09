from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from scripts import migrate_order_details_lifecycle_version_view as migration


CANONICAL = """CREATE OR REPLACE VIEW v_order_details AS
SELECT
    o.case_no AS case_no,
    o.lifecycle_version,
    o.status AS order_status
FROM orders o;
"""
ORIGINAL = (
    "CREATE ALGORITHM=UNDEFINED VIEW `v_order_details` AS "
    "SELECT o.case_no AS case_no,o.status AS order_status FROM orders o"
)


class FakeCursor:
    def __init__(
        self,
        *,
        view_statement: str = ORIGINAL,
        columns: list[str] | None = None,
        row_count: int = 8,
        mismatch_count: int = 0,
        mutate_before_ddl: bool = False,
        post_row_count: int | None = None,
        show_key: str = "Create View",
        source_column_exists: bool = True,
    ) -> None:
        self.view_statement = view_statement
        self.columns = columns or ["case_no", "order_status"]
        self.row_count = row_count
        self.mismatch_count = mismatch_count
        self.mutate_before_ddl = mutate_before_ddl
        self.post_row_count = post_row_count
        self.show_key = show_key
        self.source_column_exists = source_column_exists
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.ddl_count = 0
        self.show_count = 0
        self._one: Any = None
        self._many: Any = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        compact = " ".join(sql.split())
        self.calls.append((compact, params))
        self._one = None
        self._many = None
        if compact.startswith("SHOW CREATE VIEW"):
            self.show_count += 1
            if self.mutate_before_ddl and self.show_count == 2:
                self.view_statement = (
                    ORIGINAL.replace(
                        "o.status AS order_status",
                        "o.cancel_reason,o.status AS order_status",
                    )
                )
            self._one = {self.show_key: self.view_statement}
        elif compact.startswith("SELECT DATABASE()"):
            self._one = {
                "database_name": "union_db_upgraded",
                "server_hostname": "mysql-1",
            }
        elif (
            "FROM information_schema.columns" in compact
            and "table_name = 'orders'" in compact
        ):
            self._one = {"count": 1 if self.source_column_exists else 0}
        elif "FROM information_schema.columns" in compact:
            self._many = [
                {"column_name": column_name} for column_name in self.columns
            ]
        elif "lifecycle_version_mismatches" in compact:
            self._one = {"count": self.mismatch_count}
        elif compact == "SELECT COUNT(*) AS count FROM `v_order_details`":
            count = (
                self.post_row_count
                if self.ddl_count and self.post_row_count is not None
                else self.row_count
            )
            self._one = {"count": count}
        elif compact.startswith("CREATE OR REPLACE VIEW v_order_details AS"):
            self.ddl_count += 1
            self.view_statement = CANONICAL.strip()
            self.columns = ["case_no", "lifecycle_version", "order_status"]
        else:
            raise AssertionError(f"unexpected SQL: {compact}")

    def fetchone(self) -> Any:
        return self._one

    def fetchall(self) -> Any:
        return self._many


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_instance = cursor

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def schema_file(tmp_path: Path, content: str = CANONICAL) -> Path:
    path = tmp_path / "schema.sql"
    path.write_text(content, encoding="utf-8")
    return path


def test_canonical_statement_is_uniquely_extracted_from_schema(
    tmp_path: Path,
) -> None:
    path = schema_file(tmp_path)

    statement = migration.canonical_view_statement(path)

    assert statement == CANONICAL.strip()
    assert statement.count("o.lifecycle_version") == 1


@pytest.mark.parametrize(
    "content",
    [
        "SELECT 1;",
        CANONICAL + "\n" + CANONICAL,
        CANONICAL.replace("o.lifecycle_version,", ""),
        CANONICAL.replace(
            "o.lifecycle_version,",
            "o.lifecycle_version,\n    (SELECT 1); DELETE FROM orders;",
        ),
    ],
)
def test_canonical_statement_rejects_missing_duplicate_or_unsafe_sql(
    tmp_path: Path, content: str
) -> None:
    with pytest.raises(RuntimeError):
        migration.canonical_view_statement(schema_file(tmp_path, content))


def test_default_dry_run_is_read_only_and_returns_recovery_definition(
    tmp_path: Path,
) -> None:
    cursor = FakeCursor()

    manifest = migration.run_migration(
        FakeConnection(cursor),
        schema_path=schema_file(tmp_path),
    )

    assert manifest["mode"] == "dry-run"
    assert manifest["status"] == "ready"
    assert manifest["ddl"]["executed"] is False
    assert manifest["recovery"]["create_view"] == ORIGINAL
    assert cursor.ddl_count == 0
    assert not any(
        sql.startswith(("DELETE ", "UPDATE ", "INSERT ", "DROP ", "TRUNCATE "))
        for sql, _ in cursor.calls
    )


def test_missing_orders_lifecycle_version_blocks_before_view_ddl(
    tmp_path: Path,
) -> None:
    cursor = FakeCursor(source_column_exists=False)

    manifest = migration.run_migration(
        FakeConnection(cursor),
        apply=True,
        schema_path=schema_file(tmp_path),
    )

    assert manifest["status"] == "blocked_missing_orders_lifecycle_version"
    assert manifest["before"]["orders_lifecycle_version_exists"] is False
    assert manifest["ddl"]["executed"] is False
    assert cursor.ddl_count == 0


def test_apply_rechecks_fingerprint_then_replaces_and_validates(
    tmp_path: Path,
) -> None:
    cursor = FakeCursor()

    manifest = migration.run_migration(
        FakeConnection(cursor),
        apply=True,
        schema_path=schema_file(tmp_path),
    )

    assert manifest["status"] == "applied"
    assert manifest["ddl"]["executed"] is True
    assert manifest["before"]["row_count"] == 8
    assert manifest["after"]["row_count"] == 8
    assert manifest["after"]["value_parity_mismatch_count"] == 0
    assert manifest["after"]["columns"].count("lifecycle_version") == 1
    assert cursor.ddl_count == 1
    assert cursor.show_count == 3


def test_apply_fails_closed_when_preddl_fingerprint_changes(
    tmp_path: Path,
) -> None:
    cursor = FakeCursor(mutate_before_ddl=True)

    manifest = migration.run_migration(
        FakeConnection(cursor),
        apply=True,
        schema_path=schema_file(tmp_path),
    )

    assert manifest["status"] == "blocked_preddl_fingerprint_changed"
    assert manifest["ddl"]["executed"] is False
    assert manifest["preddl_recheck"]["create_view"] != ORIGINAL
    assert cursor.ddl_count == 0


def test_canonical_existing_view_is_verified_without_replacing(
    tmp_path: Path,
) -> None:
    cursor = FakeCursor(
        view_statement=CANONICAL.strip(),
        columns=["case_no", "lifecycle_version", "order_status"],
    )

    manifest = migration.run_migration(
        FakeConnection(cursor),
        apply=True,
        schema_path=schema_file(tmp_path),
    )

    assert manifest["status"] == "existing"
    assert manifest["ddl"]["executed"] is False
    assert cursor.ddl_count == 0


def test_failed_postcheck_keeps_original_manual_recovery_statement(
    tmp_path: Path,
) -> None:
    cursor = FakeCursor(post_row_count=7)

    manifest = migration.run_migration(
        FakeConnection(cursor),
        apply=True,
        schema_path=schema_file(tmp_path),
    )

    assert manifest["status"] == "failed_no_rollback_claimed"
    assert manifest["ddl"]["executed"] is True
    assert manifest["recovery"]["create_view"] == ORIGINAL
    assert manifest["before"]["row_count"] == 8
    assert manifest["after"]["row_count"] == 7


def test_show_create_dictcursor_key_is_case_insensitive() -> None:
    cursor = FakeCursor(show_key="CREATE VIEW")

    statement = migration._show_create_view(cursor)

    assert statement == ORIGINAL


def test_show_create_non_mapping_shape_fails_closed() -> None:
    class TupleCursor:
        def execute(self, sql):
            pass

        def fetchone(self):
            return ("v_order_details", ORIGINAL)

    with pytest.raises(RuntimeError, match="mapping"):
        migration._show_create_view(TupleCursor())


def test_source_contains_no_destructive_database_or_data_statement() -> None:
    source = Path(migration.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    executable_sql = "\n".join(
        node.args[0].value
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        )
    )

    assert "DROP DATABASE" not in executable_sql.upper()
    assert "CREATE DATABASE" not in executable_sql.upper()
    assert "DROP TABLE" not in executable_sql.upper()
    assert "TRUNCATE " not in executable_sql.upper()
    assert "DELETE FROM" not in executable_sql.upper()
    assert "UPDATE orders" not in executable_sql
    assert "INSERT INTO" not in executable_sql.upper()
