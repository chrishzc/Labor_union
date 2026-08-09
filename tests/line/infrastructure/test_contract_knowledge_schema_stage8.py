"""Stage 8 additive schema, manifest hashes, and critical bypass retirement."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_stage8_schema_owns_durable_contract_and_knowledge_roots() -> None:
    contract_sql = (ROOT / "db/schema_parts/156_contract_integration.sql").read_text("utf-8")
    knowledge_sql = (ROOT / "db/schema_parts/157_knowledge_retrieval.sql").read_text("utf-8")

    assert "CREATE TABLE IF NOT EXISTS contract_webhook_inbox" in contract_sql
    assert "CREATE TABLE IF NOT EXISTS external_contract_events" in contract_sql
    assert "trg_external_contract_events_before_update" in contract_sql
    assert "CREATE TABLE IF NOT EXISTS knowledge_item_versions" in knowledge_sql
    assert "CREATE TABLE IF NOT EXISTS knowledge_answer_receipts" in knowledge_sql
    assert "chk_knowledge_answer_non_authoritative" in knowledge_sql


def test_stage8_manifest_hashes_are_exact() -> None:
    manifest = json.loads((ROOT / "db/migration_releases/labor_union_2026_08_09_line_stage8_v1.json").read_text("utf-8"))
    artifacts = [*manifest["artifacts"], manifest["descriptor_artifact"]]

    for artifact in artifacts:
        assert hashlib.sha256((ROOT / artifact["relative_path"]).read_bytes()).hexdigest() == artifact["sha256"]


def test_critical_legacy_breezysign_and_rag_bypasses_are_retired() -> None:
    line_bot = (ROOT / "line/line_bot.py").read_text("utf-8")
    legacy_worker = (ROOT / "line/worker.py").read_text("utf-8")

    assert '@router.post("/webhook/breezysign")' not in line_bot
    assert "PersistentClient" not in legacy_worker
    assert "legacy_rag_retired" in legacy_worker
    assert "actual_start_date = %s" not in line_bot
