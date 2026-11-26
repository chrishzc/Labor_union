"""Shared composition for admin, public FAQ and LINE layout reads."""

from api.dependencies.knowledge_retrieval import get_published_faq_catalog
from api.dependencies.line_ai_qa_catalog import load_line_ai_qa_catalog
from domains.knowledge_retrieval.qa_catalog import QA_SOURCE_PREFIX
from infrastructure.mysql.knowledge_retrieval_unit_of_work import open_knowledge_retrieval_unit_of_work
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.shared_line_faq_cutover import shared_faq_reader_ready
from subsystems.knowledge_retrieval.faq_catalog import (
    KnowledgeCatalogUnavailable, PredecessorPublishedFaqCatalog, PublishedFaq,
)
from subsystems.line.faq_chat_layout import FaqChatLayoutApplication
from subsystems.line.predecessor_line_faq import PredecessorLineFaq
from subsystems.line.service_help_application import ServiceHelpFaqReaders


def get_faq_chat_layout_application() -> FaqChatLayoutApplication:
    return FaqChatLayoutApplication(open_line_unit_of_work, get_published_faq_catalog().get)


def get_service_help_faq_readers():
    """Resolve API and worker reads through the same database activation receipt."""
    shared = ServiceHelpFaqReaders(get_published_faq_catalog(), get_faq_chat_layout_application())
    catalog = PredecessorPublishedFaqCatalog(open_knowledge_retrieval_unit_of_work)
    previous = ServiceHelpFaqReaders(catalog, None, PredecessorLineFaq(catalog, _load_predecessor_seed))

    def select() -> ServiceHelpFaqReaders:
        try:
            with get_connection() as connection:
                ready = shared_faq_reader_ready(connection)
        except Exception as error:
            raise KnowledgeCatalogUnavailable("knowledge_catalog_unavailable") from error
        return shared if ready else previous

    return select


def _load_predecessor_seed() -> tuple[PublishedFaq, ...]:
    return tuple(
        PublishedFaq(
            qa_id=item.id, category=item.category, category_id=None, tag=item.tag,
            question=item.question, answer=item.answer, aliases=item.aliases,
            source_ref=item.source_ref, source_identity=QA_SOURCE_PREFIX + item.id,
            source_version=0, source_uri=item.source_ref,
        )
        for item in load_line_ai_qa_catalog()
        if item.enabled and item.answer.strip()
    )
