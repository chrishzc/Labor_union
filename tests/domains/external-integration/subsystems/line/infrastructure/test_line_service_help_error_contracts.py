"""Focused regressions for LINE service-help failure classification."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes import line_service_help


class _FailingKnowledgeUnitOfWork:
    def __enter__(self):
        raise RuntimeError("synthetic repository unavailable")

    def __exit__(self, *_):
        return False


def _semantic_result(outcome: str, code: str | None = None):
    return SimpleNamespace(
        outcome=outcome,
        answer_text=None,
        qa_id=None,
        source_identity=None,
        code=code,
    )


def test_unsupported_remains_normal_manual_handoff() -> None:
    application = SimpleNamespace(
        test_semantics=lambda _: _semantic_result(
            "unsupported", "knowledge_answer_unsupported"
        )
    )

    response = line_service_help.ask_service_question(
        line_service_help.ServiceHelpAskRequest(question="題庫沒有這一題"),
        application,
    )

    assert response.data is not None
    assert response.data.outcome == "unsupported"
    assert response.data.suggestion


@pytest.mark.parametrize(
    ("outcome", "code"),
    (
        ("index_unavailable", "knowledge_index_unavailable"),
        ("provider_error", "timeout"),
        ("provider_error", "rate_limited"),
    ),
)
def test_semantic_runtime_failures_are_typed_503(outcome: str, code: str) -> None:
    application = SimpleNamespace(
        test_semantics=lambda _: _semantic_result(outcome, code)
    )

    with pytest.raises(HTTPException) as caught:
        line_service_help.ask_service_question(
            line_service_help.ServiceHelpAskRequest(question="服務問題"),
            application,
        )

    error = caught.value
    assert error.status_code == 503
    assert error.detail["error"]["category"] == "unavailable"
    assert error.detail["error"]["code"] == code
    assert error.detail["error"]["retryable"] is True
    assert "synthetic" not in error.detail["error"]["message"]


def test_unexpected_semantic_exception_does_not_become_unsupported() -> None:
    def fail(_question: str):
        raise RuntimeError("provider raw detail must stay private")

    application = SimpleNamespace(test_semantics=fail)

    with pytest.raises(HTTPException) as caught:
        line_service_help.ask_service_question(
            line_service_help.ServiceHelpAskRequest(question="服務問題"),
            application,
        )

    error = caught.value
    assert error.status_code == 503
    assert error.detail["error"]["code"] == "knowledge_query_unavailable"
    assert "provider raw detail" not in error.detail["error"]["message"]


def test_faq_repository_failure_is_not_a_successful_empty_catalog(monkeypatch) -> None:
    monkeypatch.setattr(
        line_service_help,
        "open_knowledge_retrieval_unit_of_work",
        lambda: _FailingKnowledgeUnitOfWork(),
    )

    with pytest.raises(HTTPException) as caught:
        line_service_help.get_published_faqs()

    error = caught.value
    assert error.status_code == 503
    assert error.detail["error"]["code"] == "knowledge_catalog_unavailable"
    assert error.detail["error"]["retryable"] is True


def test_liff_distinguishes_unsupported_from_runtime_and_malformed_failures() -> None:
    source = Path("line/static/service_help.html").read_text(encoding="utf-8")

    assert "if (!response.ok || !result?.data" in source
    assert "!Array.isArray(result.data.items)" in source
    assert "result.data.outcome === 'unsupported'" in source
    assert "系統目前無法完成知識庫查詢" in source
    assert "問答服務暫時無法使用" in source
    assert "result.data?.suggestion ||" not in source
