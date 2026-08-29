"""Stage 5 migration release and owned-object lock tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


def test_stage5_release_locks_schema_and_owned_objects() -> None:
    manifest_path = (
        ROOT
        / "db/migration_releases/labor_union_2026_08_08_line_stage5_v1.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = manifest["artifacts"][0]
    descriptor_artifact = manifest["descriptor_artifact"]

    assert manifest["source_baseline"]["baseline_id"] == "line-stage4-v1"
    assert _sha(ROOT / artifact["relative_path"]) == artifact["sha256"]
    assert _sha(ROOT / descriptor_artifact["relative_path"]) == descriptor_artifact["sha256"]

    descriptors = json.loads(
        (ROOT / descriptor_artifact["relative_path"]).read_text(encoding="utf-8")
    )["descriptors"][artifact["name"]]
    assert "line_rich_menu_publication_step_receipts" in descriptors["tables"]
    assert set(descriptors["tables"]["line_domain_outbox"]) == {
        "max_attempts",
        "error_message",
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
