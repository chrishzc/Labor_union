import pytest

from domains.knowledge_retrieval.knowledge import KnowledgeReviewRequired
from domains.knowledge_retrieval.publication import KnowledgeState, next_knowledge_state
from infrastructure.mysql.knowledge_retrieval_repository import (
    MySqlKnowledgeRetrievalRepository,
    _answer,
    _unsupported_faq_payload,
)
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.knowledge_retrieval.answer_query import _format_cited_answer
from subsystems.knowledge_retrieval.contracts import PublishKnowledgeItemCommand, RetireKnowledgeItemCommand


def test_knowledge_draft_publishes_without_review():
    assert next_knowledge_state(KnowledgeState.DRAFT, "publish") is KnowledgeState.PUBLISHED
    # Preserved rows in the old intermediate state remain publishable.
    assert next_knowledge_state(KnowledgeState.REVIEWED, "publish") is KnowledgeState.PUBLISHED


class _TransitionCursor:
    def __init__(self, published_version=None, *, is_qa=True) -> None:
        qa = '{"schema":"line.common_qa.v1","id":"QA-001","category":"FAQ","tag":"FAQ","question":"Q","aliases":[],"answer":"A","source_ref":"builtin","notes":null,"migration_status":"ready"}'
        self.fetches = iter((
            {
                "id": 41, "state": "draft", "version": 1 if published_version is None else 3,
                "published_version": published_version, "content": qa if is_qa else "policy",
                "title": "Q", "source_digest": "d" * 64, "source_uri": "builtin",
                "source_trust_tier": "internal_policy",
            },
        ))
        self.executions = []
        self.lastrowid = 1

    def __enter__(self): return self
    def __exit__(self, *_): return None
    def execute(self, sql, parameters=()): self.executions.append((sql, parameters))
    def fetchone(self): return next(self.fetches)


class _TransitionConnection:
    def __init__(self, published_version=None, *, is_qa=True) -> None:
        self.cursor_instance = _TransitionCursor(published_version, is_qa=is_qa)
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
            "feedback_outcome": None,
            "failure_code": None,
        },)


class _QuestionRowsConnection:
    def __init__(self) -> None: self.cursor_instance = _QuestionRowsCursor()
    def cursor(self): return self.cursor_instance


def test_content_creator_may_publish_their_own_qa_with_audited_actor() -> None:
    connection = _TransitionConnection()
    command = PublishKnowledgeItemCommand(
        41,
        ExpectedVersion(1),
        ActorContext("7"),
        "owner published bundled content",
        IdempotencyKey("publish-same-actor-41"),
        CorrelationId("publish-same-actor-41"),
    )

    version = MySqlKnowledgeRetrievalRepository(connection).publish(command)

    assert version == 2
    projection_updates = [entry for entry in connection.cursor_instance.executions if "UPDATE knowledge_items SET" in entry[0]]
    assert len(projection_updates) == 1
    assert "published_by_admin_user_id=%s" in projection_updates[0][0]
    assert projection_updates[0][1][2:4] == (2, 7)


@pytest.mark.parametrize(
    ("published_version", "is_qa", "allowed"),
    [(2, True, True), (None, True, False), (None, False, False)],
    ids=["published-faq-with-draft", "unpublished-faq", "non-faq-draft"],
)
def test_faq_02_only_active_faq_can_retire_with_a_draft_editing_head(
    published_version, is_qa, allowed
) -> None:
    connection = _TransitionConnection(published_version, is_qa=is_qa)
    repository = MySqlKnowledgeRetrievalRepository(connection)
    command = RetireKnowledgeItemCommand(
        41, ExpectedVersion(3 if published_version else 1), ActorContext("7"),
        "retire official FAQ", IdempotencyKey("retire-41"), CorrelationId("retire-41"),
    )

    if not allowed:
        with pytest.raises(KnowledgeReviewRequired):
            repository.retire(command)
        assert not any("UPDATE knowledge_items" in sql for sql, _ in connection.cursor_instance.executions)
        return

    assert repository.retire(command) == 4
    update = next(
        parameters for sql, parameters in connection.cursor_instance.executions
        if "UPDATE knowledge_items" in sql
    )
    assert update[:3] == ("retired", 4, None)


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
    assert "feedback_outcome" in sql
    assert "source_response_id" in sql
    assert parameters == ("unsupported", "unsupported", 50)


def test_unsupported_question_routes_to_common_faq_topics() -> None:
    payload = _unsupported_faq_payload()

    assert "沒有答案" not in payload["text"]
    assert "常見問答" in payload["text"]
    assert [
        item["action"]["text"] for item in payload["quickReply"]["items"]
    ] == ["服務流程", "收費與補助", "查詢服務進度", "修改登記資料", "其他問題"]


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
