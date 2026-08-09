from pathlib import Path

from line import worker
from subsystems.line.knowledge_question_application import (
    enqueue_line_knowledge_question,
)


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_rag_task_fails_closed_to_canonical_worker():
    outcome = worker._execute_task({"task_type": "rag_reply"})

    assert outcome == (
        False,
        False,
        "legacy_rag_retired",
        "Use canonical Knowledge Retrieval worker",
    )


def test_line_worker_does_not_query_an_unreviewed_knowledge_index():
    worker_source = (ROOT / "line" / "worker.py").read_text(encoding="utf-8")

    assert "chromadb" not in worker_source
    assert "union_faq" not in worker_source


def test_canonical_line_question_uses_durable_knowledge_request():
    source = (ROOT / "subsystems/line/knowledge_question_application.py").read_text(
        encoding="utf-8"
    )

    assert enqueue_line_knowledge_question is not None
    assert "create_answer_request" in source
    assert "knowledge-question:" in source
