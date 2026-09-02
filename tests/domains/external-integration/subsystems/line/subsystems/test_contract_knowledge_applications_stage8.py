"""
File: test_contract_knowledge_applications_stage8.py
Description: 驗證 Knowledge worker 與整合能力契約。
"""

from domains.knowledge_retrieval.knowledge import (
    KnowledgeAnswer,
    KnowledgeAnswerUnsupported,
    KnowledgeCitation,
)
from subsystems.access.integration_capabilities import (
    IntegrationCapability,
    integration_capabilities_for_role,
)
from subsystems.knowledge_retrieval.application import KnowledgeWorker


class _KnowledgeRepository:
    def __init__(self):
        self.jobs = [
            {"id": 1, "job_type": "answer", "question": "問題", "answer_request_id": 7}
        ]
        self.completed = []
        self.unsupported = []

    def claim_next_job(self, _):
        return self.jobs.pop(0) if self.jobs else None

    def ready_index_version(self):
        return 3

    def complete_answer(self, job_id, request_id, answer):
        self.completed.append((job_id, request_id, answer))

    def complete_unsupported(self, job_id, request_id):
        self.unsupported.append((job_id, request_id))

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


class _UnsupportedGateway:
    def answer(self, question, version):
        del question, version
        raise KnowledgeAnswerUnsupported("knowledge_answer_unsupported")


def test_knowledge_worker_records_cited_answer_receipt() -> None:
    repository = _KnowledgeRepository()
    worker = KnowledgeWorker(
        lambda: _KnowledgeUow(repository), _Gateway(), "worker-1"
    )

    assert worker.run_once() == 1
    assert repository.completed[0][2].authoritative is False


def test_knowledge_worker_completes_unsupported_without_failed_job() -> None:
    repository = _KnowledgeRepository()
    worker = KnowledgeWorker(
        lambda: _KnowledgeUow(repository), _UnsupportedGateway(), "worker-1"
    )

    assert worker.run_once() == 1
    assert repository.completed == []
    assert repository.unsupported == [(1, 7)]


def test_known_roles_share_complete_integration_capability_set() -> None:
    expected = tuple(sorted(capability.value for capability in IntegrationCapability))

    for role in ("line_viewer", "line_agent", "line_manager", "system_admin"):
        assert integration_capabilities_for_role(role) == expected


def test_unknown_role_has_no_integration_capabilities() -> None:
    assert integration_capabilities_for_role("unknown-role") == ()
