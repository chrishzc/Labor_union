"""Static and replay safety tests for the canonical LINE schema release."""

from pathlib import Path

from scripts.init_db import load_schema_parts
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PARTS = (
    "154_line_integration_inbox_delivery.sql",
    "155_line_identity_review_configuration.sql",
    "156_line_publication_media_order_group.sql",
)


class RecordingCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, statement: str) -> None:
        self.executed.append(statement)


def _schema_text(name: str) -> str:
    return (ROOT / "db" / "schema_parts" / name).read_text(encoding="utf-8")


def test_stage2_schema_is_additive_and_keeps_invitation_urls_transient() -> None:
    combined = "\n".join(_schema_text(name) for name in SCHEMA_PARTS).lower()

    assert "drop table" not in combined
    assert "truncate table" not in combined
    assert "delete from" not in combined
    assert "invitation_url" not in combined
    assert "line_order_group_migration_anomalies" in combined


def test_stage2_append_only_facts_have_mutation_guards() -> None:
    combined = "\n".join(_schema_text(name) for name in SCHEMA_PARTS)
    protected_tables = (
        "line_delivery_attempt_events",
        "line_command_receipts",
        "line_domain_audit_events",
        "line_identity_binding_events",
        "line_review_decision_events",
        "line_configuration_revisions",
        "line_order_group_binding_events",
    )

    for table_name in protected_tables:
        assert f"BEFORE UPDATE ON {table_name}" in combined
        assert f"BEFORE DELETE ON {table_name}" in combined


def test_stage2_schema_parts_replay_through_project_loader(tmp_path) -> None:
    parts = tmp_path / "schema_parts"
    parts.mkdir()
    for name in SCHEMA_PARTS:
        (parts / name).write_text(_schema_text(name), encoding="utf-8")
    cursor = RecordingCursor()

    loaded = load_schema_parts(cursor, parts)

    assert loaded == list(SCHEMA_PARTS)
    assert any("CREATE TABLE IF NOT EXISTS line_inbox_events" in item for item in cursor.executed)
    assert any("CREATE TABLE IF NOT EXISTS line_review_requests" in item for item in cursor.executed)
    assert any("CREATE TABLE IF NOT EXISTS line_media_records" in item for item in cursor.executed)


def test_stage2_migration_release_is_hash_locked_and_complete() -> None:
    manifest_path = (
        ROOT
        / "db"
        / "migration_releases"
        / "labor_union_2026_08_08_line_stage2_v1.json"
    )

    manifest = load_migration_release_manifest(manifest_path, ROOT)

    assert manifest.release_id == "labor-union-line-stage2-2026-08-08-v1"
    assert [item.artifact.name for item in manifest.schema_artifacts] == list(
        SCHEMA_PARTS
    )
