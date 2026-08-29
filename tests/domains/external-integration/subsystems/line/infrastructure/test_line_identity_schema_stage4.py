"""Static migration and public-boundary checks for LINE identity Stage 4."""

from pathlib import Path

from scripts.init_db import load_schema_parts
from shared_kernel.migration_release import load_migration_release_manifest

PROJECT_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


class RecordingCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, statement: str) -> None:
        self.executed.append(statement)


def test_stage4_schema_has_durable_identity_and_friend_facts() -> None:
    schema = (PROJECT_ROOT / "db/schema_parts/158_line_identity_runtime.sql").read_text(
        encoding="utf-8"
    )

    assert "line_platform_users" in schema
    assert "line_friend_state_events" in schema
    assert "line_identity_flows" in schema
    assert "ADD COLUMN IF NOT EXISTS" not in schema
    assert "active_subject_key" in schema


def test_stage4_migration_release_is_hash_locked() -> None:
    manifest_path = (
        PROJECT_ROOT
        / "db/migration_releases/labor_union_2026_08_08_line_stage4_v1.json"
    )

    manifest = load_migration_release_manifest(manifest_path, PROJECT_ROOT)

    assert manifest.release_id == "labor-union-line-stage4-2026-08-08-v1"
    assert [item.artifact.name for item in manifest.schema_artifacts] == [
        "158_line_identity_runtime.sql"
    ]


def test_stage4_schema_replays_through_project_loader(tmp_path) -> None:
    source = PROJECT_ROOT / "db/schema_parts/158_line_identity_runtime.sql"
    parts = tmp_path / "schema_parts"
    parts.mkdir()
    (parts / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    cursor = RecordingCursor()

    loaded = load_schema_parts(cursor, parts)

    assert loaded == ["158_line_identity_runtime.sql"]
    assert any("CREATE TABLE IF NOT EXISTS line_identity_flows" in sql for sql in cursor.executed)


def test_public_identity_response_does_not_expose_owner_primary_keys() -> None:
    schema = (PROJECT_ROOT / "api/schemas/line_identity.py").read_text(encoding="utf-8")
    public_models = schema.split("class CanonicalLineReviewDecisionRequest", 1)[0]

    assert "subject_reference" not in public_models


def test_public_liff_route_does_not_accept_internal_service_key_as_identity() -> None:
    route = (PROJECT_ROOT / "api/routes/line_identity.py").read_text(encoding="utf-8")
    public_section = route.split("@review_router.get", 1)[0]

    assert "require_internal_service" not in public_section
    assert "get_liff_token_verifier" in public_section
