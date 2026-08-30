"""Focused fail-closed checks for the Task 97 production-script lane C."""

from __future__ import annotations

import pytest

from scripts import reconcile_fixture_order_dates_v2 as fixture_dates
def test_fixture_date_apply_is_blocked_before_db_connection(capsys) -> None:
    assert fixture_dates.main(
        [
            "--apply",
            "--target-database",
            "lu_test_orders",
            "--target-host",
            "mysql-test",
        ]
    ) == 2
    assert fixture_dates.CLI_BLOCKED_REASON in capsys.readouterr().out


def test_fixture_date_cli_rejects_union_db_before_db_connection(
    monkeypatch, capsys
) -> None:
    monkeypatch.setitem(fixture_dates.DB_CONFIG, "database", "union_db")
    monkeypatch.setenv("DB_HOST", "mysql-production")
    monkeypatch.setattr(
        fixture_dates,
        "reconcile",
        lambda *args, **kwargs: pytest.fail("non-disposable target must not connect"),
    )

    assert fixture_dates.main(
        [
            "--dry-run",
            "--target-database",
            "union_db",
            "--target-host",
            "mysql-production",
        ]
    ) == 2
    assert "lu_test_*" in capsys.readouterr().out
