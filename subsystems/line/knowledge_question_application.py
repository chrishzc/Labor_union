"""Translate one canonical LINE text event into a durable knowledge request."""

from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.knowledge_retrieval.contracts import AskKnowledgeQuestionCommand


def enqueue_line_knowledge_question(inbox, unit_of_work, line_user_id, question):
    event_id = inbox.event.event_id.value
    return unit_of_work.knowledge_questions.create_answer_request(
        AskKnowledgeQuestionCommand(
            question,
            line_user_id.value,
            IdempotencyKey(f"knowledge-question:{event_id}"),
            CorrelationId(f"line-event:{event_id}"),
        )
    )


__all__ = ["enqueue_line_knowledge_question"]
