from domains.knowledge_retrieval.publication import KnowledgeState, KnowledgeTransitionError, next_knowledge_state
from infrastructure.mysql.knowledge_retrieval_repository import MySqlKnowledgeRetrievalRepository, _answer
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.knowledge_retrieval.answer_query import _format_cited_answer
from subsystems.knowledge_retrieval.contracts import ReviewKnowledgeItemCommand


def test_knowledge_requires_review_before_publication():
    assert next_knowledge_state(KnowledgeState.DRAFT, "review") is KnowledgeState.REVIEWED
    assert next_knowledge_state(KnowledgeState.REVIEWED, "publish") is KnowledgeState.PUBLISHED
    try:
        next_knowledge_state(KnowledgeState.DRAFT, "publish")
    except KnowledgeTransitionError as error:
        assert str(error) == "knowledge_state_conflict"
    else:
        raise AssertionError("draft knowledge must not publish without review")


class _TransitionCursor:
    def __init__(self) -> None:
        self.fetches = iter((
            {"id": 41, "state": "draft", "version": 1},
            {"content": '{"schema":"line.common_qa.v1","id":"QA-001","category":"FAQ","tag":"FAQ","question":"Q","aliases":[],"answer":"A","source_ref":"builtin","notes":null,"migration_status":"ready"}', "source_digest": "d" * 64},
        ))
        self.executions = []
        self.lastrowid = 1

    def __enter__(self): return self
    def __exit__(self, *_): return None
    def execute(self, sql, parameters=()): self.executions.append((sql, parameters))
    def fetchone(self): return next(self.fetches)


class _TransitionConnection:
    def __init__(self) -> None: self.cursor_instance = _TransitionCursor()
    def cursor(self): return self.cursor_instance


class _QuestionRowsCursor:
    def __init__(self) -> None:
        self.executed = None
    def __enter__(self): return self
    def __exit__(self, *_): return None
    def execute(self, sql, parameters=()): self.executed = (sql, parameters)
    def fetchall(self):
        return ({
            "id": 8,
            "question": "這個問題有答案嗎？",
            "request_status": "unsupported",
            "source_identity": None,
            "failure_code": None,
        },)


class _QuestionRowsConnection:
    def __init__(self) -> None: self.cursor_instance = _QuestionRowsCursor()
    def cursor(self): return self.cursor_instance


def test_content_creator_may_review_their_own_qa_with_audited_actor() -> None:
    connection = _TransitionConnection()
    command = ReviewKnowledgeItemCommand(
        41,
        ExpectedVersion(1),
        ActorContext("7"),
        "owner reviewed bundled content",
        IdempotencyKey("review-same-actor-41"),
        CorrelationId("review-same-actor-41"),
    )

    version = MySqlKnowledgeRetrievalRepository(connection).review(command)

    assert version == 2
    projection_updates = [entry for entry in connection.cursor_instance.executions if "UPDATE knowledge_items SET" in entry[0]]
    assert len(projection_updates) == 1
    assert "reviewed_by_admin_user_id=%s" in projection_updates[0][0]
    assert projection_updates[0][1][2] == 7


def test_question_observation_exposes_gap_without_line_identity() -> None:
    connection = _QuestionRowsConnection()

    rows = MySqlKnowledgeRetrievalRepository(connection).list_answer_requests(
        50,
        "unsupported",
    )

    assert rows[0]["question"] == "這個問題有答案嗎？"
    sql, parameters = connection.cursor_instance.executed
    assert "requester_line_user_id" not in sql
    assert "last_error_code" in sql
    assert parameters == ("unsupported", "unsupported", 50)


def test_published_answer_has_versioned_citations_and_non_authoritative_boundary():
    answer = _answer([{
        "id": 12, "source_uri": "https://policy.example/subsidy", "title": "補助規則",
        "content": "補助資格需由行政確認。", "content_digest": "a" * 64,
        "version": 3, "published_at": "2026-08-09T12:00:00",
    }])

    assert answer is not None
    assert answer["authoritative"] is False
    assert answer["citations"][0]["version"] == 3
    assert "資料來源：https://policy.example/subsidy（v3）" in _format_cited_answer(answer)
