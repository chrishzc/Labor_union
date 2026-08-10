"""Stage 8 governed knowledge worker orchestration with fake ports."""

from domains.knowledge_retrieval.knowledge import KnowledgeAnswer, KnowledgeCitation
from subsystems.knowledge_retrieval.application import KnowledgeWorker


class _KnowledgeRepository:
    def __init__(self):
        self.jobs = [
            {"id": 1, "job_type": "answer", "question": "問題", "answer_request_id": 7}
        ]
        self.completed = []

    def claim_next_job(self, _):
        return self.jobs.pop(0) if self.jobs else None

    def ready_index_version(self):
        return 3

    def complete_answer(self, job_id, request_id, answer):
        self.completed.append((job_id, request_id, answer))

    def fail_job(self, *_):
        raise AssertionError("answer should not fail")


class _KnowledgeUow:
    def __init__(self, repository):
        self.knowledge = repository

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


class _Gateway:
    def answer(self, question, version):
        return KnowledgeAnswer(
            "有來源的回答", (KnowledgeCitation("policy:test", 1, "安全摘要"),), version
        )


def test_knowledge_worker_records_cited_answer_receipt() -> None:
    repository = _KnowledgeRepository()
    worker = KnowledgeWorker(
        lambda: _KnowledgeUow(repository), _Gateway(), "worker-1"
    )

    assert worker.run_once() == 1
    assert repository.completed[0][2].authoritative is False
