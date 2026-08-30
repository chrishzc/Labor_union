"""Fail-closed guards for Task 97 test-only database entrypoints."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import audit_staff_historical_adoption as staff_audit
from scripts import run_contract_signing_normal_chain as normal_chain
from scripts import run_task96_rpre_browser_scenario as rpre
from scripts import seed_ui_validation_dataset as integrated_seed


def test_staff_historical_audit_rejects_non_disposable_configured_database(monkeypatch) -> None:
    monkeypatch.setitem(staff_audit.DB_CONFIG, "database", "union_db")

    with pytest.raises(ValueError, match="lu_test"):
        staff_audit._require_validation_database()


def test_staff_resume_connection_has_no_union_database_fallback(monkeypatch) -> None:
    source = (Path(__file__).resolve().parents[1] / "scripts" / "generate_staff_resume_docs.py").read_text(
        encoding="utf-8"
    )
    assert 'database=os.getenv("DB_DATABASE", "union_db")' not in source
    assert "def _require_validation_database" in source


def test_integrated_seed_validates_target_before_mutating_runtime_environment(monkeypatch) -> None:
    monkeypatch.setenv("DB_DATABASE", "lu_test_existing")
    arguments = type("Arguments", (), {"database": "union_db"})()

    with pytest.raises(ValueError, match="lu_test_dataset"):
        integrated_seed._configure_runtime_database(arguments)

    assert os.environ["DB_DATABASE"] == "lu_test_existing"


def test_scenario_database_guards_require_complete_allowlist_pattern(monkeypatch) -> None:
    arguments = type(
        "Arguments",
        (),
        {
            "confirm_database": "lu_test_dataset_valid",
            "database": "lu_test_dataset_invalid-",
        },
    )()
    arguments.confirm_database = arguments.database
    with pytest.raises(ValueError, match="validation dataset"):
        normal_chain._configure_database(arguments)

    monkeypatch.setenv("DB_DATABASE", "lu_test_")
    with pytest.raises(RuntimeError, match="lu_test"):
        rpre._configured_database()
