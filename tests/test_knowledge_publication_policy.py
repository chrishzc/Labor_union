import pytest

from domains.knowledge_retrieval.publication import (
    KnowledgeState,
    KnowledgeTransitionError,
    next_knowledge_state,
    require_separate_publisher,
    require_separate_reviewer,
)
from infrastructure.mysql.knowledge_retrieval_repository import _answer
from subsystems.knowledge_retrieval.answer_query import _format_cited_answer


def test_knowledge_requires_review_before_publication():
    assert next_knowledge_state(KnowledgeState.DRAFT, "review") is KnowledgeState.REVIEWED
    assert next_knowledge_state(KnowledgeState.REVIEWED, "publish") is KnowledgeState.PUBLISHED
    with pytest.raises(KnowledgeTransitionError, match="knowledge_state_conflict"):
        next_knowledge_state(KnowledgeState.DRAFT, "publish")


def test_knowledge_review_and_publication_are_separate_from_content_author():
    with pytest.raises(KnowledgeTransitionError, match="reviewer"):
        require_separate_reviewer(7, 7)
    with pytest.raises(KnowledgeTransitionError, match="publisher"):
        require_separate_publisher(7, 7)


def test_published_answer_has_versioned_citations_and_non_authoritative_boundary():
    answer = _answer([{
        "id": 12, "source_uri": "https://policy.example/subsidy", "title": "補助規則",
        "content": "補助資格需由行政確認。", "content_digest": "a" * 64,
        "version": 3, "published_at": "2026-08-09T12:00:00",
    }])

    assert answer is not None
    assert answer["authoritative"] is False
    assert answer["citations"][0]["version"] == 3
    assert "資料來源：https://policy.example/subsidy（v3）" in _format_cited_answer(answer)
