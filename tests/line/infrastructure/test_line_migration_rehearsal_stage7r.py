"""Stage 7.R contracts for isolated matching migration rehearsals."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as runner


ROOT = Path(__file__).resolve().parents[3]
MANIFEST_NAMES = (
    "labor_union_2026_08_08_line_stage2_v1.json",
    "labor_union_2026_08_08_line_stage3_v1.json",
    "labor_union_2026_08_08_line_stage4_v1.json",
    "labor_union_2026_08_08_line_stage5_v1.json",
    "labor_union_2026_08_08_line_stage6_v1.json",
    "labor_union_2026_08_09_line_stage7_v1.json",
)
MANIFESTS = tuple(
    ROOT / "db" / "migration_releases" / name for name in MANIFEST_NAMES
)


def test_line_release_chain_selects_stage2_through_stage7() -> None:
    original = _runner_release_state()
    try:
        runner.configure_release_manifests(MANIFESTS)

        assert runner.SCHEMA_PARTS[-1].name == "152_matching_line_communication.sql"
        assert len(runner.SCHEMA_PARTS) == 9
        assert len(runner.RELEASE_MANIFEST.manifests) == 6
        assert runner.MANIFEST_DRIVEN_RELEASE is True
        assert set(runner.OWNED_OBJECTS) == {path.name for path in runner.SCHEMA_PARTS}
    finally:
        _restore_runner_release_state(original)


def test_stage7_descriptor_owns_only_stage7_matching_objects() -> None:
    descriptor = _load_stage7_descriptor()
    tables = descriptor["descriptors"]["152_matching_line_communication.sql"]["tables"]

    assert tables["caregiver_matching_plans"] == ["communication_version"]
    assert set(tables) == {
        "caregiver_matching_plans",
        "matching_notification_intents",
        "matching_line_interactions",
        "matching_response_events",
    }


def test_stage7_descriptor_never_persists_raw_interaction_tokens() -> None:
    descriptor = _load_stage7_descriptor()
    interaction_columns = descriptor["descriptors"][
        "152_matching_line_communication.sql"
    ]["tables"]["matching_line_interactions"]

    assert "token_hash" in interaction_columns
    assert "token" not in interaction_columns


def _load_stage7_descriptor() -> dict[str, object]:
    path = ROOT / "db" / "migration_releases" / (
        "labor_union_2026_08_09_line_stage7_v1.descriptors.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


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
