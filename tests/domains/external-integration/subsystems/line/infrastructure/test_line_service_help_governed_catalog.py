"""Focused regressions for the governed LINE service-help catalog."""

from types import SimpleNamespace

from api.routes import line_service_help
from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa
from subsystems.knowledge_retrieval.faq_catalog import PublishedFaqCatalog


class _KnowledgeRepository:
    def __init__(self, items):
        self._items = items
        self.calls = []

    def published_faq_page(self, cursor, limit):
        self.calls.append((cursor, limit))
        return self._items


class _KnowledgeUnitOfWork:
    def __init__(self, items):
        self.knowledge = _KnowledgeRepository(items)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _published_item(qa_id: str = "published-only") -> dict[str, str | int]:
    return {
        "source_identity": f"line-common-qa:{qa_id}",
        "source_version": 4,
        "source_uri": "正式來源",
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


def test_faq_returns_only_governed_published_items() -> None:
    unit_of_work = _KnowledgeUnitOfWork([_published_item()])
    catalog = PublishedFaqCatalog(lambda: unit_of_work)
    layout = SimpleNamespace(category_names=lambda: {})

    response = line_service_help.get_published_faqs(catalog, layout)
    assert unit_of_work.knowledge.calls == [(None, 51)]
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
