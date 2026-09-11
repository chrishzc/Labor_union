"""
File: test_deterministic_ai_router.py
Description: 驗證 M2 deterministic 路由的真人確認優先序、typed closed outcome 與 fail-closed 邊界。
"""

from domains.customer_service.ticket import CustomerServiceCategory
from domains.knowledge_retrieval.knowledge import KnowledgeAnswer, KnowledgeCitation
from subsystems.line.ai_router_contracts import (
    Clarification,
    DeterministicAnswer,
    DeterministicRoute,
    RouterOutcomeKind,
    SafeMenu,
)
from subsystems.line.deterministic_ai_router import DeterministicLineRouter, score_band


def test_human_marker_precedes_exact_identity_alias() -> None:
    outcome = DeterministicLineRouter().route(
        "我要找客服，綁定訂單",
        source_event_id="event-1",
    )

    assert isinstance(outcome, DeterministicRoute)
    assert outcome.kind is RouterOutcomeKind.DETERMINISTIC_ROUTE
    assert outcome.category is CustomerServiceCategory.OTHER
    assert outcome.route_key == "human_handoff_confirmation"


def test_human_marker_precedes_service_registration() -> None:
    outcome = DeterministicLineRouter().route(
        "我要人工協助服務登記",
        source_event_id="event-human-registration",
    )

    assert isinstance(outcome, DeterministicRoute)
    assert outcome.route_key == "human_handoff_confirmation"


def test_explicit_confirmation_alias_creates_ticket_referral() -> None:
    from subsystems.line.ai_router_contracts import TicketReferral

    outcome = DeterministicLineRouter().route(
        "專人客服", source_event_id="event-confirmed-human"
    )

    assert isinstance(outcome, TicketReferral)
    assert outcome.kind is RouterOutcomeKind.TICKET_REFERRAL
    assert outcome.reason_code == "explicit_human_request"


def test_only_exact_unmarked_identity_alias_routes_to_identity() -> None:
    router = DeterministicLineRouter()

    outcome = router.route("綁定訂單", source_event_id="event-2")
    near_miss = router.route("綁定訂單，謝謝", source_event_id="event-3")

    assert outcome == DeterministicRoute(
        route_key="customer_binding",
        category=None,
        identity_flow_id="customer_binding",
        reason_code="protected_identity_alias",
    )
    assert isinstance(near_miss, SafeMenu)


def test_unknown_input_is_safe_menu_and_never_provider_or_domain_command() -> None:
    outcome = DeterministicLineRouter().route(
        "請幫我猜一個答案",
        source_event_id="event-4",
    )

    assert isinstance(outcome, SafeMenu)
    assert outcome.score_band == "lt_50"
    assert outcome.kind is RouterOutcomeKind.SAFE_MENU


def test_unscoped_subsidy_amount_question_requires_program_clarification() -> None:
    outcome = DeterministicLineRouter().route(
        "補助多少",
        source_event_id="event-subsidy-scope",
    )

    assert isinstance(outcome, Clarification)
    assert outcome.question_key == "subsidy_scope"
    assert outcome.options == ("一般市民補助", "低收／中低收入戶社福補助")
    assert outcome.reason_code == "subsidy_scope_ambiguous"


def test_social_welfare_subsidy_question_is_not_reclassified_as_general_subsidy() -> None:
    outcome = DeterministicLineRouter().route(
        "低收入戶社福補助多少",
        source_event_id="event-social-welfare-subsidy",
    )

    assert not (
        isinstance(outcome, Clarification) and outcome.question_key == "subsidy_scope"
    )


def test_published_cited_knowledge_can_be_projected_as_non_authoritative_answer() -> None:
    answer = KnowledgeAnswer(
        "請依正式文件向工會確認。",
        (KnowledgeCitation("policy:leave", 3, "需由工會確認個案資格。"),),
        7,
    )

    outcome = DeterministicLineRouter().route(
        "請問請假規定",
        source_event_id="event-5",
        knowledge_answer=answer,
    )

    assert isinstance(outcome, DeterministicAnswer)
    assert outcome.authoritative is False
    assert outcome.source_version == 7
    assert outcome.citations[0].source_identity == "policy:leave"


def test_missing_or_stale_knowledge_fails_closed() -> None:
    outcome = DeterministicLineRouter().route(
        "請問請假規定",
        source_event_id="event-6",
        knowledge_index_ready=False,
        knowledge_answer=KnowledgeAnswer(
            "不應輸出",
            (KnowledgeCitation("policy:leave", 3, "摘要"),),
            7,
        ),
    )

    assert isinstance(outcome, SafeMenu)
    assert outcome.reason_code == "knowledge_index_unavailable"


def test_score_band_is_closed_and_deterministic() -> None:
    assert score_band(80) == "gte_80"
    assert score_band(50) == "50_79"
    assert score_band(79) == "50_79"
    assert score_band(49) == "lt_50"
    assert score_band(None) == "lt_50"
