"""Keep explicitly configured disposable MySQL tests isolated from application DB settings."""

from __future__ import annotations

import os

import pytest


_DISPOSABLE_MYSQL_ENVIRONMENT = {
    "LABOR_UNION_TEST_MYSQL_HOST": "DB_HOST",
    "LABOR_UNION_TEST_MYSQL_PORT": "DB_PORT",
    "LABOR_UNION_TEST_MYSQL_USER": "DB_USER",
    "LABOR_UNION_TEST_MYSQL_PASSWORD": "DB_PASSWORD",
    "LABOR_UNION_TEST_MYSQL_DATABASE": "DB_DATABASE",
}


def pytest_configure() -> None:
    """Make legacy adapters use the same explicitly selected disposable database."""
    configured_values = _configured_disposable_values()
    if configured_values is None:
        return
    _apply_disposable_database_environment(configured_values)


def _configured_disposable_values() -> dict[str, str] | None:
    values = {
        source_name: os.getenv(source_name, "").strip()
        for source_name in _DISPOSABLE_MYSQL_ENVIRONMENT
    }
    if not any(values.values()):
        return None
    missing_names = [name for name, value in values.items() if not value]
    if missing_names:
        raise pytest.UsageError(
            "all LABOR_UNION_TEST_MYSQL_* values are required when any are set: "
            + ", ".join(missing_names)
        )
    return values


def _apply_disposable_database_environment(values: dict[str, str]) -> None:
    for source_name, target_name in _DISPOSABLE_MYSQL_ENVIRONMENT.items():
        target_value = values[source_name]
        existing_value = os.getenv(target_name, "").strip()
        if existing_value and existing_value != target_value:
            raise pytest.UsageError(
                f"{target_name} conflicts with the explicit disposable MySQL configuration"
            )
        os.environ[target_name] = target_value
