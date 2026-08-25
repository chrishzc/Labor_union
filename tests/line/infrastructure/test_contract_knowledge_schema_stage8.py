"""Stage 8 governed knowledge runtime and retirement boundaries."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_stage8_extends_the_governed_knowledge_root() -> None:
    knowledge_sql = (ROOT / "db/schema_parts/163_knowledge_runtime.sql").read_text(
        "utf-8"
    )
    preview_sql = (
        ROOT / "db/schema_parts/164_line_rich_menu_preview_bridge.sql"
    ).read_text("utf-8")

    assert "CREATE TABLE IF NOT EXISTS knowledge_items" not in knowledge_sql
    assert "CREATE TABLE IF NOT EXISTS knowledge_item_versions" in knowledge_sql
    assert "CREATE TABLE IF NOT EXISTS knowledge_answer_receipts" in knowledge_sql
    assert "chk_knowledge_answer_non_authoritative" in knowledge_sql
    assert "canonical_publication_task_id" in preview_sql


def test_stage8_manifest_hashes_are_exact() -> None:
    manifest = json.loads(
        (
            ROOT
            / "db/migration_releases/labor_union_2026_08_09_line_stage8_v1.json"
        ).read_text("utf-8")
    )
    artifacts = [*manifest["artifacts"], manifest["descriptor_artifact"]]

    for artifact in artifacts:
        actual = hashlib.sha256(
            (ROOT / artifact["relative_path"]).read_bytes()
        ).hexdigest()
        assert actual == artifact["sha256"]


def test_retired_provider_and_legacy_rag_bypasses_stay_absent() -> None:
    line_bot = (ROOT / "line/line_bot.py").read_text("utf-8")
    legacy_worker = (ROOT / "line/worker.py").read_text("utf-8")
    webhook_handlers = (ROOT / "subsystems/line/webhook_identity_handlers.py").read_text("utf-8")

    assert "webhook/breezysign" not in line_bot.lower()
    assert "PersistentClient" not in legacy_worker
    assert "legacy_rag_retired" in legacy_worker
    assert "actual_start_date = %s" not in line_bot
    assert "?target=profile_update" not in line_bot
    assert "?target=profile_update" not in webhook_handlers
    assert "此對話不會直接變更正式資料" in webhook_handlers
