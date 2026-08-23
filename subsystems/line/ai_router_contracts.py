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


@dataclass(frozen=True, slots=True)
class DeterministicRoute:
    route_key: str
    category: CustomerServiceCategory | None
    identity_flow_id: str | None
    reason_code: str
    kind: RouterOutcomeKind = RouterOutcomeKind.DETERMINISTIC_ROUTE

    def __post_init__(self) -> None:
        require_canonical_text(self.route_key, "route_key", 191)
        require_canonical_text(self.reason_code, "router reason code", 191)
        if self.identity_flow_id is not None:
            require_canonical_text(self.identity_flow_id, "identity flow id", 191)


@dataclass(frozen=True, slots=True)
class Clarification:
    question_key: str
    options: tuple[str, ...]
    reason_code: str
    score_band: str = "50_79"
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


@dataclass(frozen=True, slots=True)
class SafeMenu:
    menu_key: str
    options: tuple[str, ...]
    reason_code: str
    score_band: str = "lt_50"
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


@dataclass(frozen=True, slots=True)
class TicketReferral:
    category: CustomerServiceCategory
    reason_code: str
    source_event_id: str
    idempotency_key: IdempotencyKey
    kind: RouterOutcomeKind = RouterOutcomeKind.TICKET_REFERRAL

    def __post_init__(self) -> None:
        require_canonical_text(self.reason_code, "router reason code", 191)
        require_canonical_text(self.source_event_id, "source event id", 191)


@dataclass(frozen=True, slots=True)
class Unavailable:
    code: str
    retryable: bool
    human_action: str
    kind: RouterOutcomeKind = RouterOutcomeKind.UNAVAILABLE

    def __post_init__(self) -> None:
        require_canonical_text(self.code, "unavailable code", 191)
        require_canonical_text(self.human_action, "human action", 500)
        if self.retryable:
            raise ValueError("M2 Phase 1 unavailable outcomes are non-retryable")


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
