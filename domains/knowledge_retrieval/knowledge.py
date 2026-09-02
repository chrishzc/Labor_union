"""Pure lifecycle, freshness, citation, and answer-boundary rules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.validation import require_canonical_text


class KnowledgeItemStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    RETIRED = "retired"


class KnowledgeIndexStatus(StrEnum):
    REQUESTED = "requested"
    BUILDING = "building"
    READY = "ready"
    STALE = "stale"
    FAILED = "failed"


class KnowledgeReviewRequired(ValueError):
    pass


class KnowledgeIndexUnavailable(ValueError):
    pass


class KnowledgeAnswerUnsupported(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class KnowledgeCitation:
    source_identity: str
    source_version: int
    safe_excerpt: str

    def __post_init__(self) -> None:
        require_canonical_text(self.source_identity, "source_identity", 191)
        if self.source_version < 1:
            raise ValueError("source_version must be positive")
        require_canonical_text(self.safe_excerpt, "safe_excerpt", 500)


@dataclass(frozen=True, slots=True)
class KnowledgeAnswer:
    answer: str
    citations: tuple[KnowledgeCitation, ...]
    index_version: int
    authoritative: bool = False

    def __post_init__(self) -> None:
        require_canonical_text(self.answer, "answer", 5000)
        if not self.citations:
            raise ValueError("knowledge_answer_unsupported")
        if self.index_version < 1:
            raise ValueError("index_version must be positive")
        if self.authoritative:
            raise ValueError("knowledge answers cannot be authoritative")


def transition_item_status(current: KnowledgeItemStatus, target: KnowledgeItemStatus) -> KnowledgeItemStatus:
    allowed = {
        KnowledgeItemStatus.DRAFT: {KnowledgeItemStatus.REVIEWED},
        KnowledgeItemStatus.REVIEWED: {KnowledgeItemStatus.PUBLISHED, KnowledgeItemStatus.DRAFT},
        KnowledgeItemStatus.PUBLISHED: {KnowledgeItemStatus.RETIRED},
    }
    if target not in allowed.get(current, set()):
        raise KnowledgeReviewRequired("knowledge_review_required")
    return target


def require_ready_index(status: KnowledgeIndexStatus) -> None:
    if status is KnowledgeIndexStatus.STALE:
        raise KnowledgeIndexUnavailable("knowledge_index_stale")
    if status is not KnowledgeIndexStatus.READY:
        raise KnowledgeIndexUnavailable("knowledge_index_unavailable")


def source_digest(content: str) -> str:
    require_canonical_text(content, "knowledge content", 100000)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def content_set_digest(items: tuple[dict, ...]) -> str:
    facts = [
        {
            "source_identity": item["source_identity"],
            "source_version": item["source_version"],
            "source_digest": item["source_digest"],
        }
        for item in items
    ]
    encoded = json.dumps(facts, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "KnowledgeAnswer",
    "KnowledgeAnswerUnsupported",
    "KnowledgeCitation",
    "KnowledgeIndexStatus",
    "KnowledgeIndexUnavailable",
    "KnowledgeItemStatus",
    "KnowledgeReviewRequired",
    "require_ready_index",
    "content_set_digest",
    "source_digest",
    "transition_item_status",
]
