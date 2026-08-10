"""Release-v3 metadata protects Access and Knowledge candidate DDL ordering."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIRECTORY = ROOT / "db" / "migration_releases"
MANIFEST_PATH = RELEASE_DIRECTORY / "labor_union_2026_08_09_v3.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v3_release_has_hashed_additive_access_and_knowledge_artifacts():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["release_id"] == "labor-union-2026-08-09-v3"
    assert manifest["predecessor_release_id"] == "labor-union-2026-08-08-v2"
    assert [item["name"] for item in manifest["artifacts"]] == [
        "149_admin_authorization_version.sql",
        "147_access_capability_grants.sql",
        "148_knowledge_retrieval.sql",
    ]
    for artifact in manifest["artifacts"]:
        assert _sha256(ROOT / artifact["relative_path"]) == artifact["sha256"]

    descriptor = manifest["descriptor_artifact"]
    assert _sha256(ROOT / descriptor["relative_path"]) == descriptor["sha256"]
