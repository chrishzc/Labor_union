"""Release-v9 metadata protects the canonical anomaly idempotency width."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "db/migration_releases/labor_union_2026_08_09_v9.json"


def test_v9_release_hashes_the_anomaly_idempotency_artifact() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    artifact = manifest["artifacts"][0]
    descriptor = manifest["descriptor_artifact"]

    assert manifest["predecessor_release_id"] == "labor-union-2026-08-09-v8"
    assert artifact["name"] == "165_anomaly_workflow_event_idempotency_widen.sql"
    assert _sha(ROOT / artifact["relative_path"]) == artifact["sha256"]
    assert _sha(ROOT / descriptor["relative_path"]) == descriptor["sha256"]


def test_v9_widens_only_the_canonical_anomaly_idempotency_key() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    artifact = manifest["artifacts"][0]
    sql = (ROOT / artifact["relative_path"]).read_text(encoding="utf-8")

    assert "MODIFY COLUMN idempotency_key VARCHAR(320) NOT NULL" in sql
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE TABLE" not in sql.upper()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
