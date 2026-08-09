"""Stage 8 durable intake and knowledge worker orchestration with fake ports."""

import json
from datetime import datetime, timezone

import pytest

from domains.contract_integration.contract_event import ContractProjectionStatus, VerifiedContractEvent
from domains.knowledge_retrieval.knowledge import KnowledgeAnswer, KnowledgeCitation
from shared_kernel.identities import CorrelationId
from subsystems.contract_integration.application import ContractSignatureInvalid, ContractWebhookApplication
from subsystems.contract_integration.contracts import ReceiveContractWebhookCommand
from subsystems.knowledge_retrieval.application import KnowledgeWorker


class _ContractRepository:
    def __init__(self):
        self.receipts = []
        self.inbox = []

    def record_security_receipt(self, *values):
        self.receipts.append(values)
        return len(self.receipts)

    def add_inbox(self, event, minimal_payload, received_at):
        self.inbox.append((event, minimal_payload, received_at))
        return len(self.inbox), True


class _ContractUow:
    def __init__(self, repository):
        self.contracts = repository
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True


class _Verifier:
    def __init__(self, valid):
        self.valid = valid

    def verify(self, *_):
        return self.valid


class _Normalizer:
    def normalize(self, _):
        return VerifiedContractEvent(
            "breezysign", "contract-1", "event-1", "changed",
            ContractProjectionStatus.SIGNED, datetime.now(timezone.utc), "a" * 64,
        )


def test_invalid_signature_persists_receipt_but_never_creates_inbox() -> None:
    repository = _ContractRepository()
    app = ContractWebhookApplication(lambda: _ContractUow(repository), _Verifier(False), _Normalizer())
    command = ReceiveContractWebhookCommand(
        "breezysign", b"{}", "bad", datetime.now(timezone.utc), CorrelationId("test")
    )

    with pytest.raises(ContractSignatureInvalid):
        app.receive(command)

    assert len(repository.receipts) == 1
    assert repository.inbox == []


def test_verified_webhook_creates_minimal_durable_inbox() -> None:
    repository = _ContractRepository()
    app = ContractWebhookApplication(lambda: _ContractUow(repository), _Verifier(True), _Normalizer())
    payload = {"event_id": "event-1", "event": "changed", "contract_id": "contract-1", "status": "done", "occurred_at": "now", "secret": "drop-me"}

    result = app.receive(ReceiveContractWebhookCommand(
        "breezysign", json.dumps(payload).encode(), "valid",
        datetime.now(timezone.utc), CorrelationId("test"),
    ))

    assert result.outcome.value == "accepted"
    assert "drop-me" not in repository.inbox[0][1]


class _KnowledgeRepository:
    def __init__(self):
        self.jobs = [{"id": 1, "job_type": "answer", "question": "問題", "answer_request_id": 7}]
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
            "有來源的回答", (KnowledgeCitation("faq:test", 1, "安全摘要"),), version
        )


def test_knowledge_worker_records_cited_answer_receipt() -> None:
    repository = _KnowledgeRepository()
    worker = KnowledgeWorker(lambda: _KnowledgeUow(repository), _Gateway(), "worker-1")

    assert worker.run_once() == 1
    assert repository.completed[0][2].authoritative is False

