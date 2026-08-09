"""Release-v6 metadata protects the Finance Import attempt ledger schema."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "db/migration_releases/labor_union_2026_08_09_v6.json"


def test_v6_release_hashes_the_ingestion_attempt_artifacts() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    artifact = manifest["artifacts"][0]
    descriptor = manifest["descriptor_artifact"]

    assert manifest["predecessor_release_id"] == "labor-union-2026-08-09-v5"
    assert artifact["name"] == "152_finance_import_ingestion_attempts.sql"
    assert manifest["application_compatibility"]["post_cutover_smoke_ids"] == [
        "finance-import-read"
    ]
    assert hashlib.sha256((ROOT / artifact["relative_path"]).read_bytes()).hexdigest() == artifact["sha256"]
    assert hashlib.sha256((ROOT / descriptor["relative_path"]).read_bytes()).hexdigest() == descriptor["sha256"]
