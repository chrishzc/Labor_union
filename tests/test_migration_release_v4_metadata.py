"""Release-v4 metadata protects the approved session and Rich Menu schema."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "db/migration_releases/labor_union_2026_08_09_v4.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v4_release_hashes_the_confirmation_and_session_policy_artifact() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["predecessor_release_id"] == "labor-union-2026-08-09-v3"
    assert [item["name"] for item in manifest["artifacts"]] == [
        "150_line_publication_confirmation_and_session_expiry.sql"
    ]
    artifact = manifest["artifacts"][0]
    assert _sha256(ROOT / artifact["relative_path"]) == artifact["sha256"]
    descriptor = manifest["descriptor_artifact"]
    assert _sha256(ROOT / descriptor["relative_path"]) == descriptor["sha256"]
