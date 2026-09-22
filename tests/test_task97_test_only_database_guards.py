"""The retained dataset library validates its target before changing the environment."""

from __future__ import annotations

import os

import pytest

from scripts import seed_ui_validation_dataset as integrated_seed


def test_integrated_seed_validates_target_before_mutating_runtime_environment(monkeypatch) -> None:
    monkeypatch.setenv("DB_DATABASE", "lu_test_existing")
    arguments = type("Arguments", (), {"database": "union_db"})()

    with pytest.raises(ValueError, match="lu_test_dataset"):
        integrated_seed._configure_runtime_database(arguments)

    assert os.environ["DB_DATABASE"] == "lu_test_existing"
