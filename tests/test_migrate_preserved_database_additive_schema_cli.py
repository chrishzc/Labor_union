"""
File: test_migrate_preserved_database_additive_schema_cli.py
Description: 驗證 preserve-data CLI、container port與完整低權限mysqldump選項。
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import scripts.migrate_preserved_database_additive_schema as migration

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


def test_source_backup_avoids_process_privilege_for_tablespace_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    captured: list[str] = []

    def fake_run(command, **kwargs):
        captured.extend(command)
        kwargs["stdout"].write(b"-- dump")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        migration, "server_identity", lambda config, database: {"server": "test"}
    )
    monkeypatch.setattr(migration.subprocess, "run", fake_run)
    migration.create_source_dump(
        DatabaseConfig("127.0.0.1", 3306, "reader", "password"),
        "lu_source",
        tmp_path / "source.sql",
        tmp_path / "receipt.json",
    )

    assert "--no-tablespaces" in captured
    assert "--events" in captured
