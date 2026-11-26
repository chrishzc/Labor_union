from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes import line_service_help
from subsystems.knowledge_retrieval.faq_catalog import PublishedFaqCatalog
from subsystems.line.service_help_application import ServiceHelpFaqReaders


class _FailingKnowledgeUnitOfWork:
    def __enter__(self):
        raise OSError("synthetic repository unavailable")

    def __exit__(self, *_):
        return False


def test_faq_repository_failure_is_not_a_successful_empty_catalog() -> None:
    catalog = PublishedFaqCatalog(_FailingKnowledgeUnitOfWork)
    layout = SimpleNamespace(category_names=lambda: {})

    with pytest.raises(HTTPException) as caught:
        line_service_help.get_published_faqs(lambda: ServiceHelpFaqReaders(catalog, layout))

    error = caught.value
    assert error.status_code == 503
    assert error.detail["error"]["code"] == "knowledge_catalog_unavailable"
    assert error.detail["error"]["retryable"] is True
