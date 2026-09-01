import hashlib
import json
from pathlib import Path

from scripts.schema_assembly import load_schema_assembly


ROOT = Path(__file__).resolve().parents[8]
PART = ROOT / "db/schema_parts/1029_client_payment_destination_configuration.sql"
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_09_01_client_payment_destination_configuration_v1.json"


def test_payment_destination_schema_is_in_fresh_and_preserve_data_release():
    names = {path.name for path in load_schema_assembly().active_artifact_paths}
    assert PART.name in names
    release = json.loads(MANIFEST.read_text(encoding="utf-8"))
    artifact = release["artifacts"][0]
    assert artifact["relative_path"] == "db/schema_parts/1029_client_payment_destination_configuration.sql"
    assert artifact["sha256"] == hashlib.sha256(PART.read_bytes()).hexdigest()


def test_payment_destination_schema_preserves_versioned_current_and_receipts():
    sql = PART.read_text(encoding="utf-8")
    for table in (
        "client_payment_destination_configuration_events",
        "client_payment_destination_configuration_current",
        "client_payment_destination_configuration_receipts",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "resulting_revision = expected_revision + 1" in sql
    assert "client payment destination events are immutable" in sql
