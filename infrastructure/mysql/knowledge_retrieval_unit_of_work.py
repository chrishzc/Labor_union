"""Connection-owning MySQL Unit of Work for Knowledge Retrieval."""

from infrastructure.mysql.knowledge_retrieval_repository import MySqlKnowledgeRetrievalRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork


class KnowledgeRetrievalMySqlUnitOfWork(MySqlUnitOfWork):
    def __init__(self, connection) -> None:
        super().__init__(connection)
        self.knowledge = MySqlKnowledgeRetrievalRepository(connection)

    def answer_receipt_catalog_revision(self, answer_receipt_id: int) -> int | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT index_version FROM knowledge_answer_receipts WHERE id=%s",
                (answer_receipt_id,),
            )
            row = cursor.fetchone()
        if row is None or row["index_version"] is None:
            return None
        return int(row["index_version"])


class ManagedKnowledgeRetrievalMySqlUnitOfWork(KnowledgeRetrievalMySqlUnitOfWork):
    def __exit__(self, exception_type, exception, traceback) -> bool:
        try:
            return super().__exit__(exception_type, exception, traceback)
        finally:
            self._connection.close()


def open_knowledge_retrieval_unit_of_work():
    return ManagedKnowledgeRetrievalMySqlUnitOfWork(get_connection())


__all__ = ["KnowledgeRetrievalMySqlUnitOfWork", "open_knowledge_retrieval_unit_of_work"]
