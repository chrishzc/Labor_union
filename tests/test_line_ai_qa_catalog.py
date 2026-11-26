from __future__ import annotations

from api.dependencies.line_ai_qa_catalog import (
    CATALOG_SOURCE_IDENTITY,
    load_line_ai_qa_catalog,
)


def test_curated_line_ai_qa_catalog_is_visible_and_status_preserving() -> None:
    items = load_line_ai_qa_catalog()

    assert CATALOG_SOURCE_IDENTITY == "document/line/AI客服QA題庫.jsonl"
    assert len(items) == 54
    assert items[0].id == "QA-001"
    assert items[-1].id == "QA-054"
    assert sum(item.status == "ready" for item in items) == 40
    assert any(item.status == "missing" for item in items)
    assert all(item.status in {"ready", "missing"} for item in items)
    assert items[0].aliases
    grocery_fee = next(item for item in items if item.id == "QA-021")
    assert grocery_fee.enabled is True
    assert "食材費由客戶負擔" in grocery_fee.answer
    assert "月嫂不負責代買或代墊" in grocery_fee.answer


def test_faq_04_legacy_source_uses_recorded_ingest_fingerprint():
    from hashlib import sha256

    from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa
    from scripts.backfill_shared_line_faq import _historical_source_proven
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
    from subsystems.knowledge_retrieval.contracts import IngestKnowledgeSourceCommand

    official = GovernedQaContent("OLD-01", "服務流程", "測試", "舊問題", (), "A", "immutable:source")
    encoded = encode_governed_qa(official)
    root = {"source_identity": official.source_identity, "source_uri": "now-draft:source"}
    ingest = {"item_version": 1, "event_type": "ingested", "source_digest": "same", "content": encoded}
    publication = {
        "item_version": 2, "source_digest": "same",
        "title": None, "source_uri": None, "source_trust_tier": None,
    }

    def event_for(source_uri):
        command = IngestKnowledgeSourceCommand(
            official.source_identity, "internal_policy", official.question, encoded, source_uri,
            ActorContext("1"), IdempotencyKey("source-ingest"), CorrelationId("correlation"),
        )
        original_repr = repr(command).removesuffix(", expected_version=None)") + ")"
        return {
            "actor_admin_user_id": 1, "idempotency_key": "source-ingest", "correlation_id": "correlation",
            "command_fingerprint": sha256(original_repr.encode("utf-8")).hexdigest(),
        }

    assert _historical_source_proven(root, publication, [ingest], {1: event_for(official.source_ref)}, official)
    assert not _historical_source_proven(root, publication, [ingest], {1: event_for("other:source")}, official)
    assert not _historical_source_proven(root, publication, [ingest], {}, official)
