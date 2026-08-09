"""Stage 8 pure Contract Integration and Knowledge Retrieval rules."""

from datetime import datetime, timezone

import pytest

from domains.contract_integration.contract_event import (
    ContractProjectionStatus,
    ContractStatusRegression,
    UnknownProviderStatus,
    canonical_payload_hash,
    map_provider_status,
    validate_projection_transition,
)
from domains.knowledge_retrieval.knowledge import (
    KnowledgeAnswer,
    KnowledgeCitation,
    KnowledgeIndexStatus,
    KnowledgeIndexUnavailable,
    KnowledgeItemStatus,
    require_ready_index,
    transition_item_status,
)


def test_provider_status_mapping_is_exact_and_unknown_fails_closed() -> None:
    mapping = {"provider-complete": "signed"}

    assert map_provider_status("provider-complete", mapping) is ContractProjectionStatus.SIGNED
    with pytest.raises(UnknownProviderStatus, match="external_contract_status_unknown"):
        map_provider_status("completed", mapping)


def test_terminal_contract_status_cannot_regress() -> None:
    validate_projection_transition(None, ContractProjectionStatus.PENDING_SIGNATURE)
    validate_projection_transition(ContractProjectionStatus.SIGNED, ContractProjectionStatus.SIGNED)

    with pytest.raises(ContractStatusRegression, match="external_contract_status_regression"):
        validate_projection_transition(ContractProjectionStatus.SIGNED, ContractProjectionStatus.CANCELLED)


def test_knowledge_requires_review_publish_and_ready_index() -> None:
    assert transition_item_status(KnowledgeItemStatus.DRAFT, KnowledgeItemStatus.REVIEWED) is KnowledgeItemStatus.REVIEWED
    assert transition_item_status(KnowledgeItemStatus.REVIEWED, KnowledgeItemStatus.PUBLISHED) is KnowledgeItemStatus.PUBLISHED
    require_ready_index(KnowledgeIndexStatus.READY)

    with pytest.raises(KnowledgeIndexUnavailable, match="knowledge_index_stale"):
        require_ready_index(KnowledgeIndexStatus.STALE)


def test_answer_is_non_authoritative_and_requires_citations() -> None:
    citation = KnowledgeCitation("faq:leave", 2, "依法規與工會正式說明辦理。")
    answer = KnowledgeAnswer("請先洽工會確認個案。", (citation,), 4)

    assert answer.authoritative is False
    with pytest.raises(ValueError, match="knowledge_answer_unsupported"):
        KnowledgeAnswer("沒有來源", (), 4)


def test_canonical_contract_payload_hash_is_order_independent() -> None:
    assert canonical_payload_hash({"a": 1, "b": 2}) == canonical_payload_hash({"b": 2, "a": 1})

