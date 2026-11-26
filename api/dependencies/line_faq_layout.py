"""Shared composition for admin, public FAQ and LINE layout reads."""

from api.dependencies.knowledge_retrieval import get_published_faq_catalog
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from subsystems.line.faq_chat_layout import FaqChatLayoutApplication


def get_faq_chat_layout_application() -> FaqChatLayoutApplication:
    return FaqChatLayoutApplication(open_line_unit_of_work, get_published_faq_catalog().get)
