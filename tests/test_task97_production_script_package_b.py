"""Focused Task 97 package B checks for migration CLI retirement boundaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import migrate_assignment_schedule_integrity as assignment
from scripts import migrate_case_architecture_bootstrap_receipt_version_contract as case_bootstrap
from scripts import migrate_leave_substitution_holiday_only_batch_contract as leave_batch


ROOT = Path(__file__).resolve().parents[1]


def test_access_schema_migration_is_fail_closed_only() -> None:
    source = (
        ROOT / "scripts/migrate_admin_capability_grants_schema.py"
    ).read_text(encoding="utf-8")

    assert "def migrate(connection" not in source
    assert ".commit(" not in source
    assert "ALTER TABLE" not in source
    assert "def main" in source
    assert 'if __name__ == "__main__"' in source


@pytest.mark.parametrize(
    ("module", "reason"),
    [
        (case_bootstrap, "187_case_architecture_bootstrap_receipt_version_contract.sql"),
        (leave_batch, "180_leave_substitution_holiday_only_batch_contract.sql"),
    ],
)
def test_unabsorbed_migrations_fail_closed_without_db_connection(
    module, reason: str, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(sys, "argv", [module.__name__, "--apply"])

    assert module.main() == 2
    captured = capsys.readouterr()
    assert reason in captured.err
    assert "migration blocked" in captured.err


def test_assignment_apply_fails_closed_before_connect(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["assignment", "--apply"])

    def unexpected_connect(**kwargs):
        raise AssertionError("blocked apply must not connect to MySQL")

    monkeypatch.setattr("pymysql.connect", unexpected_connect)

    with pytest.raises(SystemExit) as exc_info:
        assignment.main()

    assert exc_info.value.code == 2
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["success"] is False
    assert manifest["apply_result"]["applied"] is False
    assert manifest["errors"] == [assignment.APPLY_BLOCKED_REASON]
