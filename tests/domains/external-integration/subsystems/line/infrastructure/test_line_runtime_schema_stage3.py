"""Static architecture checks for the Stage 3 independent LINE runtime."""

from pathlib import Path

from shared_kernel.migration_release import load_migration_release_manifest

PROJECT_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


def test_stage3_schema_contains_runtime_control_facts() -> None:
    schema = (PROJECT_ROOT / "db/schema_parts/157_line_runtime_control.sql").read_text(
        encoding="utf-8"
    )

    assert "line_worker_heartbeats" in schema
    assert "line_webhook_security_receipts" in schema
    assert "'ignored'" in schema


def test_fastapi_no_longer_owns_line_worker_lifecycle() -> None:
    source = (PROJECT_ROOT / "api/main.py").read_text(encoding="utf-8")

    assert "from line.worker import start_worker" not in source
    assert "start_worker()" not in source


def test_canonical_webhook_boundary_does_not_import_provider_adapter() -> None:
    source = (PROJECT_ROOT / "api/line_webhook_boundary.py").read_text(encoding="utf-8")

    assert "messaging_api_adapter" not in source
    assert "requests" not in source


def test_canonical_delivery_excludes_legacy_backfill_projection() -> None:
    source = (
        PROJECT_ROOT / "infrastructure/mysql/line_delivery_task_repository.py"
    ).read_text(encoding="utf-8")

    assert "source_aggregate_type<>'legacy_line_task'" in source


def test_redis_is_only_a_wakeup_dependency() -> None:
    source = (PROJECT_ROOT / "infrastructure/line/redis_wakeup.py").read_text(
        encoding="utf-8"
    )

    assert ".publish(" in source
    assert ".subscribe(" in source
    assert "line_delivery_tasks" not in source


def test_stage3_migration_release_is_hash_locked() -> None:
    manifest_path = (
        PROJECT_ROOT
        / "db/migration_releases/labor_union_2026_08_08_line_stage3_v1.json"
    )

    manifest = load_migration_release_manifest(manifest_path, PROJECT_ROOT)

    assert manifest.release_id == "labor-union-line-stage3-2026-08-08-v1"
    assert [item.artifact.name for item in manifest.schema_artifacts] == [
        "157_line_runtime_control.sql"
    ]
