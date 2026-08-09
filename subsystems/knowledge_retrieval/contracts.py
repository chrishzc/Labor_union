"""Typed commands/results for reviewable knowledge and cited answers."""

from __future__ import annotations

from dataclasses import dataclass

from domains.knowledge_retrieval.knowledge import KnowledgeAnswer
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey


@dataclass(frozen=True, slots=True)
class IngestKnowledgeSourceCommand:
    source_identity: str
    title: str
    content: str
    source_uri: str | None
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ReviewKnowledgeItemCommand:
    item_id: int
    expected_version: ExpectedVersion
    actor: ActorContext
    reason: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class PublishKnowledgeItemCommand(ReviewKnowledgeItemCommand):
    pass


@dataclass(frozen=True, slots=True)
class RetireKnowledgeItemCommand(ReviewKnowledgeItemCommand):
    pass


@dataclass(frozen=True, slots=True)
class AskKnowledgeQuestionCommand:
    question: str
    requester_line_user_id: str | None
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerReceipt:
    request_id: int
    answer: KnowledgeAnswer
    line_delivery_task_id: int | None


__all__ = [
    "AskKnowledgeQuestionCommand",
    "IngestKnowledgeSourceCommand",
    "KnowledgeAnswerReceipt",
    "PublishKnowledgeItemCommand",
    "RetireKnowledgeItemCommand",
    "ReviewKnowledgeItemCommand",
]
