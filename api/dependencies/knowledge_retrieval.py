"""Per-request Knowledge Retrieval application construction."""

from infrastructure.mysql.knowledge_retrieval_unit_of_work import (
    open_knowledge_retrieval_unit_of_work,
)
from subsystems.knowledge_retrieval.application import KnowledgeApplication


def get_knowledge_application() -> KnowledgeApplication:
    return KnowledgeApplication(open_knowledge_retrieval_unit_of_work)


__all__ = ["get_knowledge_application"]

