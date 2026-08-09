from pathlib import Path

from line import worker


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_rag_task_fails_closed_to_human_handoff():
    reply = worker._knowledge_retrieval_unavailable_reply()

    assert "已審核來源" in reply
    assert "人工處理" in reply


def test_line_worker_does_not_query_an_unreviewed_knowledge_index():
    worker_source = (ROOT / "line" / "worker.py").read_text(encoding="utf-8")

    assert "chromadb" not in worker_source
    assert "union_faq" not in worker_source


def test_line_worker_delivers_only_a_cited_published_answer(monkeypatch):
    monkeypatch.setattr(worker, "answer_line_question", lambda _: "已發布答案\n資料來源：https://policy.example（v2）")

    assert worker._knowledge_reply({"payload_json": '{"user_text":"補助"}'}) == "已發布答案\n資料來源：https://policy.example（v2）"
