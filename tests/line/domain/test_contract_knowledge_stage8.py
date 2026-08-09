"""Stage 8 pure governed Knowledge Retrieval rules."""

import pytest

from domains.knowledge_retrieval.knowledge import (
    KnowledgeAnswer,
    KnowledgeCitation,
    KnowledgeIndexStatus,
    KnowledgeIndexUnavailable,
    KnowledgeItemStatus,
    require_ready_index,
    transition_item_status,
)


def test_knowledge_requires_review_publish_and_ready_index() -> None:
    assert transition_item_status(
        KnowledgeItemStatus.DRAFT, KnowledgeItemStatus.REVIEWED
    ) is KnowledgeItemStatus.REVIEWED
    assert transition_item_status(
        KnowledgeItemStatus.REVIEWED, KnowledgeItemStatus.PUBLISHED
    ) is KnowledgeItemStatus.PUBLISHED
    require_ready_index(KnowledgeIndexStatus.READY)

    with pytest.raises(KnowledgeIndexUnavailable, match="knowledge_index_stale"):
        require_ready_index(KnowledgeIndexStatus.STALE)


def test_answer_is_non_authoritative_and_requires_citations() -> None:
    citation = KnowledgeCitation("policy:leave", 2, "依法規與工會正式說明辦理。")
    answer = KnowledgeAnswer("請先洽工會確認個案。", (citation,), 4)

    assert answer.authoritative is False
    with pytest.raises(ValueError, match="knowledge_answer_unsupported"):
        KnowledgeAnswer("沒有來源", (), 4)
