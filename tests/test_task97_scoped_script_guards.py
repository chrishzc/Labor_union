"""Focused fail-closed checks for the Task 97 delegated script entrypoints."""

from __future__ import annotations

import json
import sys

import pytest

from scripts import migrate_legacy_ui_dataset as legacy_dataset_migration
from scripts.imports import adopt_historical_orders


def test_legacy_dataset_cli_defaults_to_read_only_and_apply_is_blocked(monkeypatch) -> None:
    monkeypatch.setattr(
        legacy_dataset_migration.pymysql,
        "connect",
        lambda **_: pytest.fail("retired CLI apply must not connect"),
    )
    monkeypatch.setattr(sys, "argv", ["migrate_legacy_ui_dataset.py", "--database", "lu_test_dataset_guard", "--apply"])

    with pytest.raises(RuntimeError, match="legacy_ui_dataset_apply_guard_contract_incomplete"):
        legacy_dataset_migration.main()


def test_historical_order_apply_is_blocked_even_for_an_allowlisted_test_target(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DB_DATABASE", "lu_test_historical_orders")
    monkeypatch.setenv("HISTORICAL_IMPORT_ALLOWED_DATABASES", "lu_test_historical_orders")
    monkeypatch.setattr(
        adopt_historical_orders,
        "_connect",
        lambda _: pytest.fail("retired historical apply must not connect"),
    )

    assert adopt_historical_orders.main(
        [
            "missing.xlsx",
            "--apply",
            "--confirm-database",
            "lu_test_historical_orders",
        ]
    ) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["error"] == "historical_order_apply_guard_contract_incomplete"
