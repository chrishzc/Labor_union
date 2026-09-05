"""Knowledge review/publication and durable answer-request orchestration."""

from __future__ import annotations

from domains.knowledge_retrieval.knowledge import (
    KnowledgeAnswerUnsupported,
    content_set_digest,
)


class KnowledgeApplication:
    def __init__(self, unit_of_work) -> None:
        self._unit_of_work = unit_of_work

    def ingest(self, command):
        with self._unit_of_work() as unit_of_work:
            result = unit_of_work.knowledge.ingest(command)
            unit_of_work.commit()
        return result

    def review(self, command) -> int:
        with self._unit_of_work() as unit_of_work:
            version = unit_of_work.knowledge.review(command)
            unit_of_work.commit()
        return version

    def publish(self, command) -> int:
        with self._unit_of_work() as unit_of_work:
            version = unit_of_work.knowledge.publish(command)
            unit_of_work.commit()
        return version

    def retire(self, command) -> int:
        with self._unit_of_work() as unit_of_work:
            version = unit_of_work.knowledge.retire(command)
            unit_of_work.commit()
        return version

    def request_index_build(self, actor_id: str, idempotency_key: str) -> int:
        with self._unit_of_work() as unit_of_work:
            job_id = unit_of_work.knowledge.request_index_build(actor_id, idempotency_key)
            unit_of_work.commit()
        return job_id

    def ask(self, command) -> tuple[int, bool]:
        with self._unit_of_work() as unit_of_work:
            result = unit_of_work.knowledge.create_answer_request(command)
            unit_of_work.commit()
        return result

    def list_items(self, limit: int, lifecycle_status: str | None = None):
        with self._unit_of_work() as unit_of_work:
            result = unit_of_work.knowledge.list_items(limit, lifecycle_status)
        return result

    def get_item(self, item_id: int):
        return self._query("get_item", item_id)

    def list_jobs(self, limit: int, processing_status: str | None = None):
        with self._unit_of_work() as unit_of_work:
            result = unit_of_work.knowledge.list_jobs(limit, processing_status)
        return result

    def list_indexes(self, limit: int):
        return self._query("list_indexes", limit)

    def get_answer_request(self, request_id: int):
        return self._query("get_answer_request", request_id)

    def retry_job(self, job_id: int, actor_id: str, idempotency_key: str) -> int:
        with self._unit_of_work() as unit_of_work:
            result = unit_of_work.knowledge.retry_job(job_id, actor_id, idempotency_key)
            unit_of_work.commit()
        return result

    def _query(self, method: str, *args):
        with self._unit_of_work() as unit_of_work:
            result = getattr(unit_of_work.knowledge, method)(*args)
        return result


class KnowledgeWorker:
    def __init__(self, unit_of_work, index_gateway, worker_id: str) -> None:
        self._unit_of_work = unit_of_work
        self._index_gateway = index_gateway
        self._worker_id = worker_id

    def run_once(self) -> int:
        with self._unit_of_work() as unit_of_work:
            job = unit_of_work.knowledge.claim_next_job(self._worker_id)
            unit_of_work.commit()
        if job is None:
            return 0
        self._execute(job)
        return 1

    def _execute(self, job: dict) -> None:
        try:
            if job["job_type"] == "index_build":
                self._build_index(job)
                return
            if job["job_type"] == "answer":
                self._answer(job)
                return
            raise ValueError("knowledge_job_type_unsupported")
        except Exception as error:
            self._fail(job["id"], error)

    def _build_index(self, job: dict) -> None:
        with self._unit_of_work() as unit_of_work:
            items = unit_of_work.knowledge.published_items()
            version = int(job["target_index_version"])
            unit_of_work.commit()
        indexed_items = self._index_gateway.rebuild(version, items)
        if not indexed_items:
            raise ValueError("knowledge_source_invalid")
        with self._unit_of_work() as unit_of_work:
            unit_of_work.knowledge.complete_index(
                job["id"], version, content_set_digest(indexed_items)
            )
            unit_of_work.commit()

    def _answer(self, job: dict) -> None:
        with self._unit_of_work() as unit_of_work:
            version = unit_of_work.knowledge.ready_index_version()
            history = ()
            if hasattr(unit_of_work.knowledge, "recent_conversation_history") and job.get("answer_request_id"):
                history = unit_of_work.knowledge.recent_conversation_history(
                    int(job["answer_request_id"]), limit=3
                )
            unit_of_work.commit()
        if version is None:
            raise RuntimeError("knowledge_index_unavailable")
        try:
            answer = self._index_gateway.answer(job["question"], version, history=history)
        except KnowledgeAnswerUnsupported:
            with self._unit_of_work() as unit_of_work:
                unit_of_work.knowledge.complete_unsupported(
                    job["id"], job["answer_request_id"]
                )
                unit_of_work.commit()
            return
        with self._unit_of_work() as unit_of_work:
            unit_of_work.knowledge.complete_answer(
                job["id"], job["answer_request_id"], answer
            )
            unit_of_work.commit()

    def _fail(self, job_id: int, error: Exception) -> None:
        retryable = isinstance(error, (ConnectionError, TimeoutError))
        with self._unit_of_work() as unit_of_work:
            unit_of_work.knowledge.fail_job(job_id, str(error)[:191], retryable)
            unit_of_work.commit()


__all__ = ["KnowledgeApplication", "KnowledgeWorker"]
