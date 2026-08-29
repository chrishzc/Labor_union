"""Stage 6.R contracts for isolated LINE operations migration rehearsals."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as runner


ROOT = Path(__file__).resolve().parents[3]
MANIFESTS = tuple(
    ROOT / "db" / "migration_releases" / name
    for name in (
        "labor_union_2026_08_08_line_stage2_v1.json",
        "labor_union_2026_08_08_line_stage3_v1.json",
        "labor_union_2026_08_08_line_stage4_v1.json",
        "labor_union_2026_08_08_line_stage5_v1.json",
        "labor_union_2026_08_08_line_stage6_v1.json",
    )
)


def test_line_release_chain_selects_stage2_through_stage6() -> None:
    original = _runner_release_state()
    try:
        runner.configure_release_manifests(MANIFESTS)

        assert tuple(path.name for path in runner.SCHEMA_PARTS) == (
            "154_line_integration_inbox_delivery.sql",
            "155_line_identity_review_configuration.sql",
            "156_line_publication_media_order_group.sql",
            "157_line_runtime_control.sql",
            "158_line_identity_runtime.sql",
            "159_line_messaging_publication_runtime.sql",
            "160_line_order_group_runtime.sql",
            "161_runtime_monitoring_line_alerts.sql",
        )
        assert runner.MANIFEST_DRIVEN_RELEASE is True
        assert len(runner.RELEASE_MANIFEST.manifests) == 5
        assert set(runner.OWNED_OBJECTS) == {
            path.name for path in runner.SCHEMA_PARTS
        }
    finally:
        _restore_runner_release_state(original)


def test_stage6_descriptor_claims_only_columns_added_by_stage6() -> None:
    descriptor_path = (
        ROOT
        / "db"
        / "migration_releases"
        / "labor_union_2026_08_08_line_stage6_v1.descriptors.json"
    )
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    columns = descriptor["descriptors"][
        "160_line_order_group_runtime.sql"
    ]["tables"]["line_order_group_bindings"]

    assert columns == ["last_invitation_at_utc", "activated_at_utc"]
    assert "binding_status" not in columns


def _runner_release_state() -> tuple[object, object, object, bool]:
    return (
        runner.RELEASE_MANIFEST,
        runner.SCHEMA_PARTS,
        runner.OWNED_OBJECTS,
        runner.MANIFEST_DRIVEN_RELEASE,
    )


def _restore_runner_release_state(
    state: tuple[object, object, object, bool],
) -> None:
    (
        runner.RELEASE_MANIFEST,
        runner.SCHEMA_PARTS,
        runner.OWNED_OBJECTS,
        runner.MANIFEST_DRIVEN_RELEASE,
    ) = state
