"""Connection-owning MySQL Unit of Work for Knowledge Retrieval."""

from infrastructure.mysql.knowledge_retrieval_repository import MySqlKnowledgeRetrievalRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork


class KnowledgeRetrievalMySqlUnitOfWork(MySqlUnitOfWork):
    def __init__(self, connection) -> None:
        super().__init__(connection)
        self.knowledge = MySqlKnowledgeRetrievalRepository(connection)


class ManagedKnowledgeRetrievalMySqlUnitOfWork(KnowledgeRetrievalMySqlUnitOfWork):
    def __exit__(self, exception_type, exception, traceback) -> bool:
        try:
            return super().__exit__(exception_type, exception, traceback)
        finally:
            self._connection.close()


def open_knowledge_retrieval_unit_of_work():
    return ManagedKnowledgeRetrievalMySqlUnitOfWork(get_connection())


__all__ = ["KnowledgeRetrievalMySqlUnitOfWork", "open_knowledge_retrieval_unit_of_work"]
