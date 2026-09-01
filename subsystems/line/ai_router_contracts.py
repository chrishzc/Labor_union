"""
File: ai_router_contracts.py
Description: 定義 M2 deterministic router 的不可變 closed outcomes 與安全錯誤契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from domains.customer_service.ticket import CustomerServiceCategory
from domains.knowledge_retrieval.knowledge import KnowledgeCitation
from shared_kernel.identities import IdempotencyKey
from shared_kernel.validation import require_canonical_text


class RouterOutcomeKind(StrEnum):
    DETERMINISTIC_ANSWER = "deterministic_answer"
    DETERMINISTIC_ROUTE = "deterministic_route"
    CLARIFICATION = "clarification"
    SAFE_MENU = "safe_menu"
    TICKET_REFERRAL = "ticket_referral"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class DeterministicAnswer:
    answer_key: str
    text: str
    citations: tuple[KnowledgeCitation, ...]
    source_version: int
    authoritative: bool = False
    source_identity: str = "LU96-M2-ROUTER-REPLY-SOURCE-V1"
    source_revision: int = 1
    semantic_bucket: str = "answer"
    confidence: int = 100
    kind: RouterOutcomeKind = RouterOutcomeKind.DETERMINISTIC_ANSWER

    def __post_init__(self) -> None:
        require_canonical_text(self.answer_key, "answer_key", 191)
        require_canonical_text(self.text, "answer text", 5000)
        if not self.citations:
            raise ValueError("deterministic answer requires citations")
        if self.source_version < 1:
            raise ValueError("source_version must be positive")
        if self.authoritative:
            raise ValueError("deterministic answer cannot be authoritative")
        require_canonical_text(self.source_identity, "answer source identity", 191)
        if self.source_revision < 1 or not 0 <= self.confidence <= 100:
            raise ValueError("answer source revision/confidence is invalid")


@dataclass(frozen=True, slots=True)
class DeterministicRoute:
    route_key: str
    category: CustomerServiceCategory | None
    identity_flow_id: str | None
    reason_code: str
    source_identity: str = "LU96-M2-ROUTER-REPLY-SOURCE-V1"
    source_revision: int = 1
    source_citation: str = "LU96-M2-ROUTER-REPLY-SOURCE-V1"
    semantic_bucket: str = "protected_route"
    confidence: int = 100
    kind: RouterOutcomeKind = RouterOutcomeKind.DETERMINISTIC_ROUTE

    def __post_init__(self) -> None:
        require_canonical_text(self.route_key, "route_key", 191)
        require_canonical_text(self.reason_code, "router reason code", 191)
        if self.identity_flow_id is not None:
            require_canonical_text(self.identity_flow_id, "identity flow id", 191)
        require_canonical_text(self.source_identity, "route source identity", 191)
        require_canonical_text(self.source_citation, "route source citation", 191)
        if self.source_revision < 1 or not 0 <= self.confidence <= 100:
            raise ValueError("route source revision/confidence is invalid")


@dataclass(frozen=True, slots=True)
class Clarification:
    question_key: str
    options: tuple[str, ...]
    reason_code: str
    score_band: str = "50_79"
    source_identity: str = "LU96-M2-ROUTER-REPLY-SOURCE-V1"
    source_revision: int = 1
    confidence: int = 50
    semantic_bucket: str = "clarification"
    kind: RouterOutcomeKind = RouterOutcomeKind.CLARIFICATION

    def __post_init__(self) -> None:
        require_canonical_text(self.question_key, "question_key", 191)
        require_canonical_text(self.reason_code, "router reason code", 191)
        if self.score_band != "50_79":
            raise ValueError("clarification score band must be 50_79")
        if not self.options:
            raise ValueError("clarification requires options")
        for option in self.options:
            require_canonical_text(option, "clarification option", 191)
        require_canonical_text(self.source_identity, "clarification source identity", 191)
        if self.source_revision < 1 or not 0 <= self.confidence <= 100:
            raise ValueError("clarification source revision/confidence is invalid")


@dataclass(frozen=True, slots=True)
class SafeMenu:
    menu_key: str
    options: tuple[str, ...]
    reason_code: str
    score_band: str = "lt_50"
    source_identity: str = "LU96-M2-ROUTER-REPLY-SOURCE-V1"
    source_revision: int = 1
    confidence: int = 0
    semantic_bucket: str = "safe_menu"
    kind: RouterOutcomeKind = RouterOutcomeKind.SAFE_MENU

    def __post_init__(self) -> None:
        require_canonical_text(self.menu_key, "menu_key", 191)
        require_canonical_text(self.reason_code, "router reason code", 191)
        if self.score_band != "lt_50":
            raise ValueError("safe menu score band must be lt_50")
        if not self.options:
            raise ValueError("safe menu requires options")
        for option in self.options:
            require_canonical_text(option, "safe menu option", 191)
        require_canonical_text(self.source_identity, "safe menu source identity", 191)
        if self.source_revision < 1 or not 0 <= self.confidence <= 100:
            raise ValueError("safe menu source revision/confidence is invalid")


@dataclass(frozen=True, slots=True)
class TicketReferral:
    category: CustomerServiceCategory
    reason_code: str
    source_event_id: str
    idempotency_key: IdempotencyKey
    source_identity: str = "LU96-M2-ROUTER-REPLY-SOURCE-V1"
    source_revision: int = 1
    semantic_bucket: str = "manual_fallback"
    kind: RouterOutcomeKind = RouterOutcomeKind.TICKET_REFERRAL

    def __post_init__(self) -> None:
        require_canonical_text(self.reason_code, "router reason code", 191)
        require_canonical_text(self.source_event_id, "source event id", 191)
        require_canonical_text(self.source_identity, "fallback source identity", 191)
        if self.source_revision < 1:
            raise ValueError("fallback source revision must be positive")


@dataclass(frozen=True, slots=True)
class Unavailable:
    code: str
    retryable: bool
    human_action: str
    source_identity: str = "LU96-M2-ROUTER-REPLY-SOURCE-V1"
    source_revision: int = 1
    semantic_bucket: str = "manual_fallback"
    kind: RouterOutcomeKind = RouterOutcomeKind.UNAVAILABLE

    def __post_init__(self) -> None:
        require_canonical_text(self.code, "unavailable code", 191)
        require_canonical_text(self.human_action, "human action", 500)
        if self.retryable:
            raise ValueError("M2 Phase 1 unavailable outcomes are non-retryable")
        require_canonical_text(self.source_identity, "unavailable source identity", 191)
        if self.source_revision < 1:
            raise ValueError("unavailable source revision must be positive")


RouterOutcome: TypeAlias = (
    DeterministicAnswer
    | DeterministicRoute
    | Clarification
    | SafeMenu
    | TicketReferral
    | Unavailable
)


__all__ = [
    "Clarification",
    "DeterministicAnswer",
    "DeterministicRoute",
    "RouterOutcome",
    "RouterOutcomeKind",
    "SafeMenu",
    "TicketReferral",
    "Unavailable",
]
