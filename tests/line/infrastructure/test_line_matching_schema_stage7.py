"""Stage 7 matching schema and release artifact contracts."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_stage7_schema_has_intents_actions_responses_and_append_only_events() -> None:
    sql = (ROOT / "db/schema_parts/152_matching_line_communication.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS matching_notification_intents" in sql
    assert "CREATE TABLE IF NOT EXISTS matching_line_interactions" in sql
    assert "CREATE TABLE IF NOT EXISTS matching_response_events" in sql
    assert "trg_matching_response_events_before_update" in sql
    assert "legacy-matching-response:" in sql
    assert "communication_version" in sql


def test_stage7_manifest_hashes_are_exact() -> None:
    manifest_path = (
        ROOT
        / "db/migration_releases/labor_union_2026_08_09_line_stage7_v1.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for artifact in manifest["artifacts"]:
        path = ROOT / artifact["relative_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
    descriptor = manifest["descriptor_artifact"]
    path = ROOT / descriptor["relative_path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == descriptor["sha256"]


def test_stage7_schema_does_not_persist_raw_interaction_token() -> None:
    sql = (ROOT / "db/schema_parts/152_matching_line_communication.sql").read_text(
        encoding="utf-8"
    )

    assert "token_hash CHAR(64)" in sql
    assert "interaction_token VARCHAR" not in sql
