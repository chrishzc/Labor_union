"""Focused zero-write checks for the Task 97 script-governance lane A."""

from __future__ import annotations

import json
from argparse import Namespace
import builtins
from pathlib import Path
import sys

import pytest

from scripts import backfill_canonical_accounting_projections as accounting
from scripts import bootstrap_disposable_mysql_schema as disposable
from scripts import bootstrap_line_configuration as line_config
from scripts import create_admin
from scripts import export_db_snapshot_fixture_v2 as exporter
from scripts import fix_schedule_conflicts as conflicts
from scripts import import_db_snapshot_fixture_v2 as importer


def test_accounting_apply_requires_exact_confirmation_before_runner(monkeypatch) -> None:
    monkeypatch.setattr(
        accounting,
        "run_migration",
        lambda **_: pytest.fail("guarded CLI must not reach the migration runner"),
    )
    monkeypatch.setattr(
        accounting.sys,
        "argv",
        ["accounting", "--apply", "--target-database", "lu_test_a", "--confirm-apply", "wrong"],
    )
    with pytest.raises(SystemExit) as error:
        accounting.main()
    assert error.value.code == 2


def test_disposable_bootstrap_dry_run_is_plan_only(tmp_path: Path) -> None:
    arguments = Namespace(
        database="lu_test_a",
        confirm_database="lu_test_a",
        max_schema_part=None,
        base_only=False,
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(disposable, "selected_schema_parts", lambda _manifest: [])
    try:
        payload = disposable._dry_run_payload(arguments, {"release_id": "r1"})
    finally:
        monkeypatch.undo()
    assert payload["mode"] == "dry-run"
    assert payload["database"] == "lu_test_a"
    assert payload["plan_fingerprint"]


def test_line_config_rejects_union_database(monkeypatch) -> None:
    monkeypatch.setitem(line_config.DB_CONFIG, "database", "union_db")
    with pytest.raises(ValueError, match="lu_test"):
        line_config._require_target_database("union_db")


def test_admin_default_is_dry_run_and_does_not_prompt(monkeypatch, capsys) -> None:
    monkeypatch.setattr(create_admin.sys, "argv", ["create_admin", "--target-database", "lu_test_a"])
    monkeypatch.setattr(builtins, "input", lambda *_: pytest.fail("must not prompt in dry-run"))
    monkeypatch.setattr(create_admin.getpass, "getpass", lambda *_: pytest.fail("must not prompt in dry-run"))
    assert create_admin.main() == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "dry-run"


def test_export_cli_requires_explicit_target_before_connection(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["export"])
    monkeypatch.setattr(exporter, "get_connection", lambda: pytest.fail("must not connect"))
    with pytest.raises(SystemExit) as error:
        exporter.main()
    assert error.value.code == 2


def test_import_cli_requires_explicit_target_before_connection(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["import"])
    monkeypatch.setattr(importer, "get_connection", lambda: pytest.fail("must not connect"))
    with pytest.raises(SystemExit) as error:
        importer.main()
    assert error.value.code == 2


def test_schedule_conflict_target_rejects_union_database(monkeypatch) -> None:
    monkeypatch.setitem(conflicts.DB_CONFIG, "database", "union_db")
    with pytest.raises(ValueError, match="lu_test"):
        conflicts._require_target_database("union_db")
