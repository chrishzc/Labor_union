"""
File: test_wp78_local_database_partial_recovery.py
Description: 驗證 Knowledge schema partial recovery 與本機 DB 更新器的兩種啟動入口。
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from scripts import migrate_preserved_database_additive_schema as migration
from scripts import update_local_database as update


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_RUNTIME = ROOT / "db/schema_parts/163_knowledge_runtime.sql"


def _knowledge_runtime_snapshot(*, source_column: bool, source_index: bool) -> dict:
    return {
        "columns": ([{
            "table_name": "knowledge_items",
            "column_name": "source_identity",
        }] if source_column else []),
        "indexes": ([{
            "table_name": "knowledge_items",
            "index_name": "uq_knowledge_source_identity",
            "non_unique": 0,
            "columns": "source_identity",
        }] if source_index else []),
    }


def test_direct_script_entrypoint_resolves_the_project_package() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/update_local_database.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0
    assert "No module named 'scripts'" not in completed.stderr


@pytest.mark.parametrize(
    ("source_column", "source_index", "expected_fragment"),
    [
        (False, False, "ADD COLUMN source_identity"),
        (True, False, "ADD UNIQUE KEY uq_knowledge_source_identity"),
    ],
)
def test_runtime_partial_recovery_selects_the_missing_alter_boundary(
    source_column: bool,
    source_index: bool,
    expected_fragment: str,
) -> None:
    statements = migration.schema_statements_for_state(
        KNOWLEDGE_RUNTIME,
        "partial",
        _knowledge_runtime_snapshot(
            source_column=source_column,
            source_index=source_index,
        ),
    )

    assert expected_fragment in statements[0]


def test_runtime_partial_recovery_skips_a_completed_alter_boundary() -> None:
    statements = migration.schema_statements_for_state(
        KNOWLEDGE_RUNTIME,
        "partial",
        _knowledge_runtime_snapshot(source_column=True, source_index=True),
    )

    assert statements[0].startswith("UPDATE knowledge_items")
    assert all("ADD COLUMN source_identity" not in item for item in statements)


def test_runtime_partial_recovery_rejects_an_impossible_index_boundary() -> None:
    with pytest.raises(
        migration.UpgradeBlocked,
        match="index exists without source_identity",
    ):
        migration.schema_statements_for_state(
            KNOWLEDGE_RUNTIME,
            "partial",
            _knowledge_runtime_snapshot(source_column=False, source_index=True),
        )


def test_local_update_allows_only_reviewed_partial_artifacts() -> None:
    assert update.LOCAL_RESUMABLE_PARTIAL_ARTIFACTS == frozenset({
        "148_knowledge_retrieval.sql",
        "163_knowledge_runtime.sql",
        "181_matching_service_date_confirmation.sql",
    })


def test_apply_failure_is_reported_without_a_raw_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = type("Config", (), {"host": "127.0.0.1"})()
    preview = {
        "source_database": "union_db",
        "candidate_database": "union_db_local_test",
        "plan": {},
    }
    monkeypatch.setattr(
        update.migration,
        "config_from_env",
        lambda _path: (config, "union_db"),
    )
    monkeypatch.setattr(update, "build_preview", lambda *_args: preview)
    monkeypatch.setattr(
        update,
        "apply_update",
        lambda *_args: (_ for _ in ()).throw(
            migration.UpgradeBlocked("source backup validation failed")
        ),
    )

    with pytest.raises(
        update.LocalDatabaseUpdateError,
        match="source backup validation failed",
    ):
        update.update_local_database(
            environment_file=tmp_path / ".env",
            receipt_root=tmp_path,
            apply=True,
            confirm_configured_database=True,
        )
