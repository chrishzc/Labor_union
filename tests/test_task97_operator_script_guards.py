"""Focused fail-closed checks for retained operator-only mutation runners."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import update_local_database as local_update
from scripts import upgrade_line_menu_merge_defaults as line_upgrade


def test_line_upgrade_rejects_operational_database_before_connection(monkeypatch) -> None:
    monkeypatch.setitem(line_upgrade.DB_CONFIG, "database", "union_db")
    with pytest.raises(ValueError, match="lu_test"):
        line_upgrade._require_target_database("union_db")


def test_line_upgrade_plan_and_backup_are_target_bound(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(
        '{"contract":"line-menu-merge-defaults/v1","mode":"dry-run",'
        '"target_database":"lu_test_a","target_hash":"hash"}',
        encoding="utf-8",
    )
    assert line_upgrade._read_plan(plan, "lu_test_a", "hash")["mode"] == "dry-run"
    with pytest.raises(ValueError, match="backup-receipt"):
        line_upgrade._validate_backup(None, "lu_test_a")


def test_local_update_rejects_production_profile_even_on_local_host() -> None:
    with pytest.raises(local_update.LocalDatabaseUpdateError, match="production"):
        local_update.validate_local_source(
            type("Config", (), {"host": "127.0.0.1"})(),
            "union_db",
            {"APP_ENV": "production"},
        )
