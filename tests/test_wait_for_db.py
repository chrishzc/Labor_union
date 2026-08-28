"""Verify local DB readiness uses the same configured database target as the updater."""

from pathlib import Path

import pytest

from scripts.wait_for_db import configured_target


def test_configured_target_reads_database_and_non_default_port_from_dotenv(
    tmp_path: Path,
) -> None:
    environment = tmp_path / ".env"
    environment.write_text(
        "DB_HOST=127.0.0.1\nDB_PORT=43306\nDB_USER=developer\n"
        "DB_PASSWORD=local-only\nDB_DATABASE=developer_orders\n",
        encoding="utf-8",
    )

    config, database = configured_target(environment)

    assert config.host == "127.0.0.1"
    assert config.port == 43306
    assert config.user == "developer"
    assert config.password == "local-only"
    assert database == "developer_orders"


def test_configured_target_refuses_missing_database(tmp_path: Path) -> None:
    environment = tmp_path / ".env"
    environment.write_text("DB_HOST=127.0.0.1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="DB_DATABASE is required"):
        configured_target(environment)
