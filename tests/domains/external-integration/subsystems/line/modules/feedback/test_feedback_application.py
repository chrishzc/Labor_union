"""Canonical M2 feedback owner tests: terminal replay, conflict, ticket linkage and aggregate."""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from domains.customer_service.ticket import CustomerServiceCategory
from shared_kernel.identities import CorrelationId, IdempotencyKey, IdempotencyReceipt
from api.routes.line_ai_events import preview_router
from api.schemas.line_ai_events import LineRouterPreviewRequest
from subsystems.line.ai_router_contracts import Clarification, Unavailable
from subsystems.line.deterministic_ai_router import DeterministicLineRouter
from subsystems.line.feedback_application import FeedbackConflictError, LineFeedbackApplication
from subsystems.line.feedback_contracts import (
    FeedbackOutcome,
    RecordLineFeedback,
)


class _Receipts:
    def __init__(self):
        self.items = {}

    def get(self, key):
        return self.items.get(key.value)

    def append(self, receipt):
        self.items[receipt.key.value] = receipt


class _Feedback:
    def __init__(self):
        self.items = {}

    def get(self, actor_id, source_response_id):
        return self.items.get((actor_id, source_response_id))

    def append(self, root):
        key = (root.actor_id, root.source_response_id)
        if key in self.items:
            raise AssertionError("feedback root must be immutable and unique")
        self.items[key] = root

    def aggregate(self, catalog_revision, window_start, window_end):
        from subsystems.line.feedback_contracts import FeedbackAggregate

        roots = [
            root for root in self.items.values()
            if root.catalog_revision == catalog_revision
            and window_start <= root.occurred_at < window_end
        ]
        return FeedbackAggregate(
            catalog_revision, window_start, window_end,
            sum(root.outcome is FeedbackOutcome.RESOLVED for root in roots),
            sum(root.outcome is FeedbackOutcome.UNRESOLVED for root in roots),
        )


class _Tickets:
    def __init__(self):
        self.calls = []

    def create_or_append(self, command):
        assert command.category is CustomerServiceCategory.OTHER
        assert command.message == "LINE 回覆未解決，請客服協助。"
        self.calls.append(command)
        return type("Ticket", (), {"ticket_id": 42})()


class _Uow:
    def __init__(self):
        self.feedback = _Feedback()
        self.receipts = _Receipts()
        self.customer_service = _Tickets()
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.commits += 1


def _command(outcome, key="feedback-key", source="reply-1"):
    return RecordLineFeedback(
        actor_id="U-test",
        source_response_id=source,
        outcome=outcome,
        binding_version=3,
        response_revision=4,
        catalog_revision=1,
        rule_revision=None,
        idempotency_key=IdempotencyKey(key),
        correlation_id=CorrelationId("corr-1"),
    )


def test_unresolved_is_durable_and_links_exact_customer_service_ticket():
    uow = _Uow()
    app = LineFeedbackApplication(lambda: uow, lambda: datetime(2026, 9, 1, tzinfo=timezone.utc))

    result = app.apply(_command(FeedbackOutcome.UNRESOLVED))

    assert result.root.ticket_id == 42
    assert result.receipt.outcome is FeedbackOutcome.UNRESOLVED
    assert result.receipt.replayed is False
    assert len(uow.feedback.items) == 1
    assert len(uow.customer_service.calls) == 1
    assert uow.commits == 1


def test_exact_replay_returns_original_receipt_without_second_ticket_or_root():
    uow = _Uow()
    app = LineFeedbackApplication(lambda: uow, lambda: datetime(2026, 9, 1, tzinfo=timezone.utc))

    first = app.apply(_command(FeedbackOutcome.UNRESOLVED))
    replay = app.apply(_command(FeedbackOutcome.UNRESOLVED, key="feedback-key-2"))

    assert replay.root == first.root
    assert replay.receipt.replayed is True
    assert len(uow.customer_service.calls) == 1
    assert len(uow.feedback.items) == 1

    readback = app.query("U-test", "reply-1")
    assert readback is not None
    assert readback.root.idempotency_key.value == "feedback-key"
    assert readback.root.correlation_id.value == "corr-1"
    assert readback.receipt.replayed is True


def test_same_idempotency_key_with_different_payload_is_conflict_without_new_root():
    uow = _Uow()
    app = LineFeedbackApplication(lambda: uow, lambda: datetime(2026, 9, 1, tzinfo=timezone.utc))
    app.apply(_command(FeedbackOutcome.RESOLVED, key="same-key"))

    with pytest.raises(FeedbackConflictError, match="feedback_idempotency_conflict"):
        app.apply(_command(FeedbackOutcome.UNRESOLVED, key="same-key", source="reply-2"))

    assert len(uow.feedback.items) == 1
    assert uow.customer_service.calls == []


def test_different_terminal_outcome_is_conflict_and_does_not_edit_root():
    uow = _Uow()
    app = LineFeedbackApplication(lambda: uow, lambda: datetime(2026, 9, 1, tzinfo=timezone.utc))
    app.apply(_command(FeedbackOutcome.RESOLVED))

    with pytest.raises(FeedbackConflictError, match="feedback_terminal_decision_conflict"):
        app.apply(_command(FeedbackOutcome.UNRESOLVED, key="other-key"))

    assert next(iter(uow.feedback.items.values())).outcome is FeedbackOutcome.RESOLVED
    assert uow.customer_service.calls == []


def test_aggregate_is_recomputed_from_roots_for_fixed_revision_and_window():
    uow = _Uow()
    app = LineFeedbackApplication(lambda: uow, lambda: datetime(2026, 9, 1, tzinfo=timezone.utc))
    app.apply(_command(FeedbackOutcome.RESOLVED, key="resolved"))
    app.apply(_command(FeedbackOutcome.UNRESOLVED, key="unresolved", source="reply-2"))

    aggregate = app.aggregate(
        1,
        datetime(2026, 8, 31, tzinfo=timezone.utc),
        datetime(2026, 9, 2, tzinfo=timezone.utc),
    )

    assert (aggregate.resolved_count, aggregate.unresolved_count, aggregate.total_count) == (1, 1, 2)


def test_deterministic_buckets_keep_reason_confidence_and_revision_stable() -> None:
    clarification = DeterministicLineRouter().route(
        "模糊問題", source_event_id="event-clarification", score=65,
    )
    unavailable = DeterministicLineRouter().route(
        "高信心但沒有已發布答案", source_event_id="event-high-confidence", score=90,
    )

    assert isinstance(clarification, Clarification)
    assert (clarification.semantic_bucket, clarification.reason_code, clarification.confidence) == (
        "clarification", "ambiguous_intent", 65,
    )
    assert clarification.source_revision == 1
    assert isinstance(unavailable, Unavailable)
    assert (unavailable.semantic_bucket, unavailable.code, unavailable.retryable) == (
        "manual_fallback", "deterministic_answer_unavailable", False,
    )


def test_development_router_preview_exposes_fixed_buckets_and_requested_confidence(
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "local_bypass")
    monkeypatch.setenv("LIFF_REQUIRE_ID_TOKEN", "false")

    clarification = preview_router(LineRouterPreviewRequest(
        text="模糊問題", source_event_id="preview-clarification", score=65,
    )).data
    safe_menu = preview_router(LineRouterPreviewRequest(
        text="未命中問題", source_event_id="preview-safe-menu", score=20,
    )).data
    protected = preview_router(LineRouterPreviewRequest(
        text="綁定訂單", source_event_id="preview-protected", score=100,
    )).data
    unavailable = preview_router(LineRouterPreviewRequest(
        text="高信心但沒有已發布答案", source_event_id="preview-unavailable", score=90,
    )).data

    assert (clarification.semantic_bucket, clarification.reason_code, clarification.confidence) == (
        "clarification", "ambiguous_intent", 65,
    )
    assert (safe_menu.semantic_bucket, safe_menu.reason_code, safe_menu.confidence) == (
        "safe_menu", "unknown_intent", 0,
    )
    assert (protected.semantic_bucket, protected.route_key, protected.confidence) == (
        "protected_route", "customer_binding", 100,
    )
    assert (unavailable.semantic_bucket, unavailable.reason_code, unavailable.confidence, unavailable.score_band) == (
        "manual_fallback", "deterministic_answer_unavailable", 90, "gte_80",
    )


def test_router_preview_is_closed_outside_development_no_auth_profile(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "local_bypass")
    monkeypatch.setenv("LIFF_REQUIRE_ID_TOKEN", "false")

    with pytest.raises(HTTPException) as raised:
        preview_router(LineRouterPreviewRequest(
            text="模糊問題", source_event_id="preview-production", score=65,
        ))
    assert raised.value.status_code == 404
    assert raised.value.detail == "development_router_preview_unavailable"
