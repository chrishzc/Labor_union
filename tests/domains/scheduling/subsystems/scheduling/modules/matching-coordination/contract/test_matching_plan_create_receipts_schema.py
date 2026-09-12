"""Static contract for fresh and preserve matching-plan create receipt storage."""

import hashlib
import json
from pathlib import Path

from scripts.schema_assembly import load_schema_assembly


ROOT = Path(__file__).resolve().parents[8]
FRESH_PART = ROOT / "db/schema_parts/222_matching_plan_create_receipts.sql"
PRESERVE_PART = ROOT / "db/schema_parts/1039_matching_plan_create_receipts.sql"
MANIFEST = ROOT / (
    "db/migration_releases/labor_union_2026_09_12_matching_plan_create_receipts_v1.json"
)
DESCRIPTOR = MANIFEST.with_name(
    "labor_union_2026_09_12_matching_plan_create_receipts_v1.descriptors.json"
)


def test_i281_matching_plan_create_receipt_schema_is_fresh_canonical_and_preserve_equivalent():
    assembly = load_schema_assembly()
    assert FRESH_PART in assembly.active_artifact_paths
    assert assembly.classifications[PRESERVE_PART.relative_to(ROOT).as_posix()] == "migration-only"
    assert FRESH_PART.read_bytes() == PRESERVE_PART.read_bytes()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    descriptor = json.loads(DESCRIPTOR.read_text(encoding="utf-8"))
    artifact = manifest["artifacts"]
    assert artifact == [{
        "name": PRESERVE_PART.name,
        "relative_path": PRESERVE_PART.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(PRESERVE_PART.read_bytes()).hexdigest(),
        "dependencies": [],
        "data_effect": "schema_only",
        "rollback_policy": "forward-only-preserve-matching-plan-create-receipts",
        "resumable_boundary_policy": "statement-sha256-with-durable-receipt",
    }]
    assert manifest["backfills"] == []
    assert manifest["descriptor_artifact"]["sha256"] == hashlib.sha256(
        DESCRIPTOR.read_bytes()
    ).hexdigest()
    owned = descriptor["descriptors"][PRESERVE_PART.name]
    assert owned["tables"]["matching_plan_create_receipts"] == [
        "id", "idempotency_key", "command_fingerprint", "case_no", "plan_id",
        "plan_version", "plan_status", "actor", "as_of", "result_kind",
        "ordered_segments", "result_snapshot", "created_at_utc",
    ]
    assert set(owned["triggers"]) == {
        "trg_matching_plan_create_receipts_before_update",
        "trg_matching_plan_create_receipts_before_delete",
    }
