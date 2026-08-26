"""
File: test_wp78_local_database_partial_recovery.py
Description: 驗證已審核 schema partial recovery 與本機 DB 更新器的啟動入口。
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
KNOWLEDGE_RETRIEVAL = ROOT / "db/schema_parts/148_knowledge_retrieval.sql"
LINE_IDENTITY_MANAGEMENT = ROOT / "db/schema_parts/186_line_identity_management.sql"
CUSTOMER_SERVICE_RUNTIME = ROOT / "db/schema_parts/185_customer_service_runtime.sql"


def _knowledge_runtime_snapshot(*, source_column: bool, source_index: bool) -> dict:
    return {
        "columns": ([
            {"table_name": "knowledge_items", "column_name": "id", "column_type": "bigint unsigned", "is_nullable": "NO", "column_default": None, "extra": "auto_increment"},
            {"table_name": "knowledge_items", "column_name": "source_identity"},
        ] if source_column else [{
            "table_name": "knowledge_items", "column_name": "id", "column_type": "bigint unsigned", "is_nullable": "NO", "column_default": None, "extra": "auto_increment"},]),
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


def test_knowledge_recovery_matches_a_legacy_unsigned_parent_identifier() -> None:
    statements = migration.schema_statements_for_state(
        KNOWLEDGE_RUNTIME,
        "partial",
        _knowledge_runtime_snapshot(source_column=False, source_index=False),
    )

    assert "item_id BIGINT UNSIGNED NOT NULL" in "\n".join(statements)


def test_knowledge_retrieval_recovery_matches_a_legacy_unsigned_parent_identifier() -> None:
    statements = migration.schema_statements_for_state(
        KNOWLEDGE_RETRIEVAL,
        "partial",
        _knowledge_runtime_snapshot(source_column=False, source_index=False),
    )

    assert "knowledge_item_id BIGINT UNSIGNED NOT NULL" in "\n".join(statements)


def test_knowledge_descriptor_accepts_only_the_known_unsigned_identifier_variant() -> None:
    snapshot = _knowledge_runtime_snapshot(source_column=False, source_index=False)
    descriptor = migration._canonical_artifact_descriptor("148_knowledge_retrieval.sql")

    migration._apply_legacy_knowledge_identifier_contract(
        descriptor, snapshot, "148_knowledge_retrieval.sql"
    )

    assert descriptor["tables"]["knowledge_items"]["id"]["column_type"] == "bigint unsigned"
    assert descriptor["tables"]["knowledge_item_events"]["knowledge_item_id"]["column_type"] == "bigint unsigned"


def test_knowledge_recovery_rejects_an_unknown_parent_identifier_type() -> None:
    snapshot = _knowledge_runtime_snapshot(source_column=False, source_index=False)
    snapshot["columns"][0]["column_type"] = "int unsigned"

    with pytest.raises(migration.UpgradeBlocked, match="supported legacy shape"):
        migration.schema_statements_for_state(KNOWLEDGE_RUNTIME, "partial", snapshot)


def test_local_update_allows_only_reviewed_partial_artifacts() -> None:
    assert update.LOCAL_RESUMABLE_PARTIAL_ARTIFACTS == frozenset({
        "148_knowledge_retrieval.sql",
        "163_knowledge_runtime.sql",
        "181_matching_service_date_confirmation.sql",
        "185_customer_service_runtime.sql",
        "186_line_identity_management.sql",
    })


def _exact_customer_service_ticket_snapshot() -> dict:
    descriptor = migration._canonical_artifact_descriptor(
        "185_customer_service_runtime.sql"
    )
    ticket = "customer_service_tickets"
    columns = [
        {"table_name": ticket, "column_name": name, **contract}
        for name, contract in descriptor["tables"][ticket].items()
    ]
    indexes = [
        {
            "table_name": table,
            "index_name": name,
            "non_unique": contract["non_unique"],
            "columns": ",".join(contract["columns"]),
        }
        for (table, name), contract in descriptor["indexes"].items()
        if table == ticket
    ]
    constraints = []
    key_columns = []
    foreign_keys = []
    for (table, name), contract in descriptor["foreign_keys"].items():
        if table != ticket:
            continue
        constraints.append({
            "table_name": table,
            "constraint_name": name,
            "constraint_type": "FOREIGN KEY",
        })
        foreign_keys.append({
            "table_name": table,
            "constraint_name": name,
            "update_rule": contract["update_rule"],
            "delete_rule": contract["delete_rule"],
        })
        key_columns.extend({
            "table_name": table,
            "constraint_name": name,
            "column_name": local,
            "referenced_table_name": contract["referenced_table"],
            "referenced_column_name": remote,
        } for local, remote in zip(
            contract["columns"], contract["referenced_columns"], strict=True
        ))
    return {
        "columns": columns,
        "indexes": indexes,
        "constraints": constraints,
        "key_columns": key_columns,
        "foreign_keys": foreign_keys,
        "show_create_tables": {},
        "triggers": [],
    }


def test_customer_service_partial_recovery_creates_only_missing_events() -> None:
    statements = migration.schema_statements_for_state(
        CUSTOMER_SERVICE_RUNTIME,
        "partial",
        _exact_customer_service_ticket_snapshot(),
    )

    assert len(statements) == 1
    assert "CREATE TABLE IF NOT EXISTS customer_service_ticket_events" in statements[0]


def test_customer_service_unknown_partial_shape_remains_blocked() -> None:
    snapshot = _exact_customer_service_ticket_snapshot()
    snapshot["columns"][0]["column_type"] = "int"

    with pytest.raises(
        migration.UpgradeBlocked,
        match="customer service runtime partial state is not resumable",
    ):
        migration.schema_statements_for_state(
            CUSTOMER_SERVICE_RUNTIME, "partial", snapshot
        )


def _line_identity_legacy_snapshot(*, malformed: bool = False) -> dict:
    binding_type = "varchar(20)" if malformed else "enum('unbound','pending_review','bound','revoked')"
    return {
        "columns": [
            {"table_name": "line_identity_bindings", "column_name": "binding_status", "column_type": binding_type, "extra": ""},
            {"table_name": "line_identity_bindings", "column_name": "active_subject_key", "column_type": "varchar(400)", "extra": "STORED GENERATED"},
            {"table_name": "line_identity_binding_events", "column_name": "action", "column_type": "enum('claim_submitted','bound','revoked','rebound','legacy_imported')", "extra": ""},
        ],
        "indexes": [],
    }


def test_line_identity_legacy_shape_resumes_the_full_published_release() -> None:
    statements = migration.schema_statements_for_state(
        LINE_IDENTITY_MANAGEMENT,
        "partial",
        _line_identity_legacy_snapshot(),
    )

    assert statements[0].startswith("ALTER TABLE line_identity_bindings")
    assert statements[-1].startswith("CREATE TABLE IF NOT EXISTS line_identity_revocation_requests")


def test_line_identity_unknown_partial_shape_remains_blocked() -> None:
    with pytest.raises(
        migration.UpgradeBlocked,
        match="partial state is not resumable",
    ):
        migration.schema_statements_for_state(
            LINE_IDENTITY_MANAGEMENT,
            "partial",
            _line_identity_legacy_snapshot(malformed=True),
        )


def test_apply_failure_is_reported_without_a_raw_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = type("Config", (), {"host": "127.0.0.1"})()
    preview = {
        "source_database": "lu_test_source",
        "candidate_database": "lu_test_candidate",
        "plan": {},
    }
    monkeypatch.setattr(
        update.migration,
        "config_from_env",
        lambda _path: (config, "lu_test_source"),
    )
    monkeypatch.setattr(update, "build_preview", lambda *_args: preview)
    monkeypatch.setattr(
        update,
        "apply_update",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
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
            mysql_container="mysql_db",
            strategy="replacement",
            allow_long_run=True,
        )
