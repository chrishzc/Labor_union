from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api.routes.line_feedback as line_feedback
from api.schemas.line_feedback import RecordLineFeedbackRequest
from subsystems.line.feedback_contracts import KnowledgeAnswerFeedbackContext


class _KnowledgeUnitOfWork:
    def __init__(self, context):
        self.knowledge = SimpleNamespace(feedback_context=lambda receipt_id, actor_id: context(receipt_id, actor_id))

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False


def _payload(**overrides):
    values = {
        "line_id_token": "token",
        "source_response_id": "knowledge-answer-receipt:42",
        "outcome": "resolved",
        "response_revision": 1,
        "catalog_revision": 9,
        "rule_revision": None,
        "idempotency_key": "feedback-42",
        "correlation_id": "feedback-correlation-42",
    }
    values.update(overrides)
    return RecordLineFeedbackRequest(**values)


def test_knowledge_feedback_uses_actor_scoped_answer_context(monkeypatch):
    calls = []

    def context(receipt_id, actor_id):
        calls.append((receipt_id, actor_id))
        return KnowledgeAnswerFeedbackContext(
            source_response_id="knowledge-answer-receipt:42",
            response_revision=1,
            rule_revision=None,
        )

    monkeypatch.setattr(
        line_feedback,
        "open_knowledge_retrieval_unit_of_work",
        lambda: _KnowledgeUnitOfWork(context),
    )

    command = line_feedback._feedback_command(_payload(), "U-owner", 7)

    assert calls == [(42, "U-owner")]
    assert command.actor_id == "U-owner"
    assert command.source_response_id == "knowledge-answer-receipt:42"
    assert command.response_revision == 1
    assert command.binding_version == 7


def test_knowledge_feedback_rejects_answer_not_owned_by_actor(monkeypatch):
    monkeypatch.setattr(
        line_feedback,
        "open_knowledge_retrieval_unit_of_work",
        lambda: _KnowledgeUnitOfWork(lambda _receipt_id, _actor_id: None),
    )

    with pytest.raises(HTTPException) as captured:
        line_feedback._feedback_command(_payload(), "U-wrong", 7)

    assert captured.value.status_code == 404
    assert captured.value.detail == "line_feedback_source_unavailable"


def test_knowledge_feedback_rejects_source_revision_drift(monkeypatch):
    context = KnowledgeAnswerFeedbackContext(
        source_response_id="knowledge-answer-receipt:42",
        response_revision=1,
        rule_revision=None,
    )
    monkeypatch.setattr(
        line_feedback,
        "open_knowledge_retrieval_unit_of_work",
        lambda: _KnowledgeUnitOfWork(lambda _receipt_id, _actor_id: context),
    )

    with pytest.raises(HTTPException) as captured:
        line_feedback._feedback_command(
            _payload(response_revision=2),
            "U-owner",
            7,
        )

    assert captured.value.status_code == 409
    assert captured.value.detail == "line_feedback_source_version_conflict"


def test_non_knowledge_feedback_keeps_existing_owner_path(monkeypatch):
    monkeypatch.setattr(
        line_feedback,
        "open_knowledge_retrieval_unit_of_work",
        lambda: pytest.fail("non-Knowledge feedback must not open Knowledge UoW"),
    )

    command = line_feedback._feedback_command(
        _payload(
            source_response_id="router-response:123",
            response_revision=3,
            catalog_revision=4,
            rule_revision=5,
        ),
        "U-owner",
        7,
    )

    assert command.source_response_id == "router-response:123"
    assert command.response_revision == 3
    assert command.catalog_revision == 4
    assert command.rule_revision == 5
