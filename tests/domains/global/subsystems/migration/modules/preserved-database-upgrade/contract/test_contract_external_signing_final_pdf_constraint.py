"""Contract coverage for external-signing final-PDF completion constraint."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = "1034_contract_external_signing_final_pdf_completion.sql"
MANIFEST = (
    "labor_union_2026_09_09_contract_external_signing_final_pdf_completion_v1.json"
)
CHECK_KEY = (
    "contract_external_signing_sessions",
    "chk_contract_external_session_state",
)


def _snapshot(clause: str) -> dict[str, object]:
    return {
        "constraints": [{
            "table_name": CHECK_KEY[0],
            "constraint_name": CHECK_KEY[1],
            "constraint_type": "CHECK",
            "check_clause": clause,
            "enforced": "YES",
        }],
        "show_create_tables": {},
    }


def test_release_is_latest_hash_bound_and_in_the_fresh_assembly() -> None:
    assert migration.DEFAULT_RELEASE_MANIFESTS[-1] == MANIFEST
    manifest_path = ROOT / "db/migration_releases" / MANIFEST
    manifest = load_migration_release_manifest(manifest_path, ROOT)
    sql_path = ROOT / "db/schema_parts" / ARTIFACT
    descriptor_path = manifest_path.with_name(
        "labor_union_2026_09_09_contract_external_signing_final_pdf_completion_v1.descriptors.json"
    )

    assert manifest.schema_paths(ROOT) == (sql_path.resolve(),)
    assert manifest.backfills == ()
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert raw["artifacts"][0]["sha256"] == hashlib.sha256(
        sql_path.read_bytes()
    ).hexdigest()
    assert raw["descriptor_artifact"]["sha256"] == hashlib.sha256(
        descriptor_path.read_bytes()
    ).hexdigest()
    assembly = json.loads((
        ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json"
    ).read_text(encoding="utf-8"))
    assert assembly["active_bootstrap"][-1].endswith(ARTIFACT)


def test_released_descriptor_matches_the_canonical_successor() -> None:
    manifest = load_migration_release_manifest(
        ROOT / "db/migration_releases" / MANIFEST,
        ROOT,
    )
    released = manifest.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)

    assert released["checks"] == canonical["checks"]
    assert set(canonical["checks"]) == {CHECK_KEY}
    statements = migration.split_sql(
        (ROOT / "db/schema_parts" / ARTIFACT).read_text(encoding="utf-8")
    )
    assert len(statements) == 1
    assert migration._local_classify_statement(statements[0]) == (
        "contract_external_signing_state_constraint_replacement"
    )


def test_only_the_released_predecessor_or_successor_is_accepted() -> None:
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    predecessor = (
        "(session_state = 'staff_reporting' AND commitment_id IS NULL "
        "AND client_reminder_task_id IS NULL) OR (session_state IN "
        "('staff_reports_complete','client_reported_final_pdf_pending','completed') "
        "AND commitment_id IS NOT NULL AND client_reminder_task_id IS NOT NULL) "
        "OR session_state = 'superseded'"
    )
    successor = canonical["checks"][CHECK_KEY]

    assert migration.local_additive_descriptor_state(
        _snapshot(predecessor), canonical, ARTIFACT
    ) == "absent"
    assert migration.local_additive_descriptor_state(
        _snapshot(successor), canonical, ARTIFACT
    ) == "exact"
    assert migration.local_additive_descriptor_state(
        _snapshot("commitment_id IS NOT NULL"), canonical, ARTIFACT
    ) == "drift"


def test_successor_makes_reports_and_client_reminder_non_blocking() -> None:
    sql = (ROOT / "db/schema_parts" / ARTIFACT).read_text(encoding="utf-8")

    assert "session_state = 'completed'" not in sql
    assert "'completed'" in sql
    assert "commitment_id IS NOT NULL" in sql
    assert "client_reminder_task_id" not in sql
    assert "contract_external_completion_reports" not in sql


def test_1005_owner_accepts_only_the_exact_1034_constraint_successor(
    monkeypatch,
) -> None:
    owner = migration._canonical_artifact_descriptor(
        "1005_contract_external_signing_successor.sql"
    )
    successor = migration._canonical_artifact_descriptor(ARTIFACT)
    calls = []

    def classify(_snapshot, descriptor, *_args, **_kwargs):
        calls.append(descriptor)
        if len(calls) == 1:
            return "drift"
        return (
            "exact"
            if descriptor["checks"][CHECK_KEY] == successor["checks"][CHECK_KEY]
            else "drift"
        )

    monkeypatch.setattr(migration, "_artifact_metadata_state", classify)
    owned_table, owned_columns = next(iter(owner["tables"].items()))
    owned_column = next(iter(owned_columns))

    assert migration._contract_external_signing_successor_state(
        {"columns": [{"table_name": owned_table, "column_name": owned_column}]},
        owner,
        defer_missing_triggers=False,
    ) == "exact"
    assert len(calls) == 2
