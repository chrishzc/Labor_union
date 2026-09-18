"""Focused regressions for the governed LINE service-help catalog."""

from types import SimpleNamespace

from api.routes import line_service_help
from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa


class _KnowledgeRepository:
    def __init__(self, items):
        self._items = items
        self.calls = []

    def list_items(self, limit, lifecycle):
        self.calls.append((limit, lifecycle))
        return self._items


class _KnowledgeUnitOfWork:
    def __init__(self, items):
        self.knowledge = _KnowledgeRepository(items)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _published_item(qa_id: str = "published-only") -> dict[str, str]:
    return {
        "content": encode_governed_qa(
            GovernedQaContent(
                qa_id=qa_id,
                category="服務說明",
                tag="已發布",
                question="這是已發布問題嗎？",
                aliases=("已發布問題",),
                answer="這是目前已發布的核准回答。",
                source_ref="正式來源",
            )
        )
    }


def test_faq_returns_only_governed_published_items(monkeypatch) -> None:
    unit_of_work = _KnowledgeUnitOfWork([_published_item()])
    monkeypatch.setattr(
        line_service_help,
        "open_knowledge_retrieval_unit_of_work",
        lambda: unit_of_work,
    )

    response = line_service_help.get_published_faqs()

    assert unit_of_work.knowledge.calls == [(100, "published")]
    assert response.data is not None
    assert [item.qa_id for item in response.data.items] == ["published-only"]
    assert response.data.categories == ["服務說明"]


def test_ask_does_not_restore_hardcoded_answer_after_governed_lookup_misses() -> None:
    application = SimpleNamespace(
        test_semantics=lambda _: SimpleNamespace(
            outcome="unsupported",
            answer_text=None,
            qa_id=None,
            source_identity=None,
            source_version=None,
            index_version=None,
        )
    )

    response = line_service_help.ask_service_question(
        line_service_help.ServiceHelpAskRequest(
            question="月嫂每天的服務時數有哪些選擇？"
        ),
        application,
    )

    assert response.data is not None
    assert response.data.outcome == "unsupported"
    assert response.data.answer_text is None
    assert response.data.qa_id is None
    assert response.data.source_identity is None


def test_ask_preserves_governed_answer_source_identity() -> None:
    application = SimpleNamespace(
        test_semantics=lambda _: SimpleNamespace(
            outcome="answered",
            answer_text="目前已發布的核准回答。",
            qa_id="published-only",
            source_identity="line-common-qa:published-only",
            source_version=1,
            index_version=1,
        )
    )

    response = line_service_help.ask_service_question(
        line_service_help.ServiceHelpAskRequest(question="已發布問題"),
        application,
    )

    assert response.data is not None
    assert response.data.outcome == "answered"
    assert response.data.qa_id == "published-only"
    assert response.data.source_identity == "line-common-qa:published-only"
    assert response.data.source_ref == "line-common-qa:published-only"
