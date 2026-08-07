"""Public CLI entrypoint tests for preserve-data migration runner."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from scripts.migrate_preserved_database_additive_schema import (
    DatabaseConfig,
    _mysql_base,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = PROJECT_ROOT / "scripts" / "migrate_preserved_database_additive_schema.py"


def _run_runner(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER_PATH), *arguments],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_runner_help_is_available_without_database_connection() -> None:
    result = _run_runner("--help")

    assert result.returncode == 0
    assert "--candidate-database" in result.stdout
    assert "--complete-restart" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr
    assert "--rollback-switch" in result.stdout


def test_runner_rejects_missing_source_without_connecting() -> None:
    result = _run_runner(
        "--check",
        "--environment-file",
        "missing-environment-file.env",
        "--candidate-database",
        "lu_candidate",
    )

    assert result.returncode == 1
    assert "FileNotFoundError" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr


def test_container_client_uses_mysql_internal_port_not_host_mapping() -> None:
    command = _mysql_base(
        DatabaseConfig("127.0.0.1", 33084, "root", "password"),
        "mysqldump",
        container="labor_union_disposable_mysql_20260804",
    )

    assert command[:6] == [
        "docker", "exec", "-i", "-e", "MYSQL_PWD",
        "labor_union_disposable_mysql_20260804",
    ]
    assert command[6] == "mysqldump"
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "3306"
