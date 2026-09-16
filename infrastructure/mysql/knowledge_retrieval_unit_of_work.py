"""Connection-owning MySQL Unit of Work for Knowledge Retrieval."""

from pymysql.err import IntegrityError

from infrastructure.mysql.knowledge_retrieval_repository import MySqlKnowledgeRetrievalRepository
from infrastructure.mysql.line_repository_support import mysql_error_code
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

    def record_inline_outcome(self, command, request_status: str) -> int:
        if request_status not in {"unsupported", "failed"}:
            raise ValueError("knowledge_inline_outcome_invalid")
        if not command.requester_line_user_id:
            raise ValueError("knowledge_inline_answer_actor_required")
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO knowledge_answer_requests "
                    "(question,requester_line_user_id,idempotency_key,correlation_id,"
                    "request_status,completed_at_utc) "
                    "VALUES (%s,%s,%s,%s,%s,CURRENT_TIMESTAMP(6))",
                    (
                        command.question,
                        command.requester_line_user_id,
                        command.idempotency_key.value,
                        command.correlation_id.value,
                        request_status,
                    ),
                )
                return int(cursor.lastrowid)
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id,question,requester_line_user_id,correlation_id,request_status "
                    "FROM knowledge_answer_requests WHERE idempotency_key=%s",
                    (command.idempotency_key.value,),
                )
                row = cursor.fetchone()
            expected = (
                command.question,
                command.requester_line_user_id,
                command.correlation_id.value,
                request_status,
            )
            actual = None if row is None else (
                str(row["question"]),
                str(row["requester_line_user_id"]),
                str(row["correlation_id"]),
                str(row["request_status"]),
            )
            if actual != expected:
                raise RuntimeError("knowledge_answer_idempotency_conflict") from error
            return int(row["id"])


class ManagedKnowledgeRetrievalMySqlUnitOfWork(KnowledgeRetrievalMySqlUnitOfWork):
    def __exit__(self, exception_type, exception, traceback) -> bool:
        try:
            return super().__exit__(exception_type, exception, traceback)
        finally:
            self._connection.close()


def open_knowledge_retrieval_unit_of_work():
    return ManagedKnowledgeRetrievalMySqlUnitOfWork(get_connection())


__all__ = ["KnowledgeRetrievalMySqlUnitOfWork", "open_knowledge_retrieval_unit_of_work"]
