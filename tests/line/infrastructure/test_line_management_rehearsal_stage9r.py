"""Stage 9.R read-model contracts found by the isolated API/UI rehearsal."""

from infrastructure.mysql.knowledge_retrieval_repository import (
    MySqlKnowledgeRetrievalRepository,
)


def test_answer_read_model_normalizes_mysql_boolean() -> None:
    repository = object.__new__(MySqlKnowledgeRetrievalRepository)
    responses = iter(
        [
            [{"id": 1, "request_status": "answered", "authoritative": 0}],
            [{"source_identity": "knowledge:1", "source_version": 3}],
        ]
    )
    repository._rows = lambda *_arguments: next(responses)

    result = repository.get_answer_request(1)

    assert result["authoritative"] is False
    assert result["citations"][0]["source_identity"] == "knowledge:1"


def test_pending_answer_keeps_unknown_authority_nullable() -> None:
    repository = object.__new__(MySqlKnowledgeRetrievalRepository)
    responses = iter([[{"id": 2, "authoritative": None}], []])
    repository._rows = lambda *_arguments: next(responses)

    result = repository.get_answer_request(2)

    assert result["authoritative"] is None
