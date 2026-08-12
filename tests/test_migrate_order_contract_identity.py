from __future__ import annotations

import pytest

from scripts.migrate_order_contract_identity import (
    CANONICAL_COLUMN,
    migrate,
    retire_legacy_contract_column,
)


class _Cursor:
    def __init__(self, columns: set[str]) -> None:
        self.columns = columns
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)
        if statement.startswith("ALTER TABLE"):
            self.columns.remove("contract_id")
            self.columns.add(CANONICAL_COLUMN)

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def fetchall(self) -> list[dict[str, str]]:
        return [{"Field": column} for column in self.columns]


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_instance = cursor
        self.committed = False

    def cursor(self) -> _Cursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True


def test_renames_only_the_legacy_provider_contract_column() -> None:
    cursor = _Cursor({"case_no", "contract_id"})

    outcome = retire_legacy_contract_column(cursor)

    assert outcome == "renamed"
    assert cursor.columns == {"case_no", CANONICAL_COLUMN}
    assert cursor.statements[-1].endswith("contract_id TO contract_identity")


def test_migration_rebuilds_the_dependent_order_details_view_after_rename() -> None:
    cursor = _Cursor({"case_no", "contract_id", "lifecycle_version"})
    connection = _Connection(cursor)

    migrate(connection)

    assert "CREATE OR REPLACE VIEW v_order_details AS" in cursor.statements[-1]
    assert "o.contract_identity" in cursor.statements[-1]


def test_replay_is_idempotent_after_the_legacy_column_is_retired() -> None:
    cursor = _Cursor({"case_no", CANONICAL_COLUMN})
    connection = _Connection(cursor)

    result = migrate(connection)

    assert result == {"status": "already_retired", "canonical_column": CANONICAL_COLUMN}
    assert connection.committed is True
    assert cursor.statements == ["SHOW COLUMNS FROM orders"]


@pytest.mark.parametrize("columns", [{"case_no"}, {"case_no", "contract_id", CANONICAL_COLUMN}])
def test_ambiguous_column_states_fail_closed(columns: set[str]) -> None:
    with pytest.raises(RuntimeError, match="absent or ambiguous"):
        retire_legacy_contract_column(_Cursor(columns))
