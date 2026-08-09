"""Release-v5 metadata protects the administrator audit archive schema."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "db/migration_releases/labor_union_2026_08_09_v5.json"


def test_v5_release_hashes_the_admin_audit_archive_artifact() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    artifact = manifest["artifacts"][0]
    descriptor = manifest["descriptor_artifact"]

    assert manifest["predecessor_release_id"] == "labor-union-2026-08-09-v4"
    assert artifact["name"] == "151_admin_security_audit_retention.sql"
    assert hashlib.sha256((ROOT / artifact["relative_path"]).read_bytes()).hexdigest() == artifact["sha256"]
    assert hashlib.sha256((ROOT / descriptor["relative_path"]).read_bytes()).hexdigest() == descriptor["sha256"]
