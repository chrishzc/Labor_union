"""Focused fail-closed checks for the Task 97 delegated script entrypoints."""

from __future__ import annotations

import json

import pytest

from scripts.imports import adopt_historical_orders


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
