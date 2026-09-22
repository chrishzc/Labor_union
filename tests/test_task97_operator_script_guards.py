"""Focused fail-closed checks for retained operator-only mutation runners."""

from __future__ import annotations


import pytest

from scripts import update_local_database as local_update


def test_local_update_rejects_production_profile_even_on_local_host() -> None:
    with pytest.raises(local_update.LocalDatabaseUpdateError, match="production"):
        local_update.validate_local_source(
            type("Config", (), {"host": "127.0.0.1"})(),
            "union_db",
            {"APP_ENV": "production"},
        )
