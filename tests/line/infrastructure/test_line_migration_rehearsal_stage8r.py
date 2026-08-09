"""Stage 8.R contracts for isolated Contract and Knowledge rehearsals."""

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
    "labor_union_2026_08_09_line_stage8_v1.json",
)
MANIFESTS = tuple(
    ROOT / "db" / "migration_releases" / name for name in MANIFEST_NAMES
)


def test_line_release_chain_selects_stage2_through_stage8() -> None:
    original = _runner_release_state()
    try:
        runner.configure_release_manifests(MANIFESTS)

        assert runner.SCHEMA_PARTS[-1].name == "164_line_rich_menu_preview_bridge.sql"
        assert len(runner.SCHEMA_PARTS) == 11
        assert len(runner.RELEASE_MANIFEST.manifests) == 7
        assert runner.MANIFEST_DRIVEN_RELEASE is True
        assert set(runner.OWNED_OBJECTS) == {
            path.name for path in runner.SCHEMA_PARTS
        }
    finally:
        _restore_runner_release_state(original)


def test_stage8_descriptor_extends_governed_knowledge_and_preview_roots() -> None:
    descriptors = _stage8_descriptors()
    knowledge_tables = set(descriptors["163_knowledge_runtime.sql"]["tables"])
    preview_tables = set(
        descriptors["164_line_rich_menu_preview_bridge.sql"]["tables"]
    )

    assert "knowledge_items" in knowledge_tables
    assert "knowledge_answer_receipts" in knowledge_tables
    assert preview_tables == {"line_rich_menu_publish_previews"}


def test_stage8_manifest_requires_all_independent_runtime_restarts() -> None:
    manifest = json.loads(MANIFESTS[-1].read_text(encoding="utf-8"))
    restart_targets = set(
        manifest["application_compatibility"]["required_restart_targets"]
    )

    assert restart_targets == {
        "api",
        "line-worker",
        "knowledge-retrieval-worker",
        "runtime-monitor",
    }


def _stage8_descriptors() -> dict[str, object]:
    path = ROOT / "db" / "migration_releases" / (
        "labor_union_2026_08_09_line_stage8_v1.descriptors.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))["descriptors"]


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
