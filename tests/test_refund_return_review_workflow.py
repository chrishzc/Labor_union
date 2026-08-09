import pytest

from domains.client_finance.refund_return_review import RefundReturnReviewFacts, RefundReturnReviewSelection
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.finance_import.refund_return_review_workflow import RefundReturnReviewApplyRequest, RefundReturnReviewWorkflow, RefundReturnReviewWorkflowError


def test_review_records_only_a_confirmed_link_and_replays():
    selection = _selection()
    repository = _Repository(_facts())
    workflow = RefundReturnReviewWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(selection, CorrelationId("preview"))
    request = _request(selection, preview.fingerprint)

    receipt = workflow.apply(request)

    assert receipt.review_event_identity == "client-refund-return-review:12"
    assert repository.calls == ["append", "receipt"]
    assert workflow.apply(request) == receipt
    assert repository.calls == ["append", "receipt"]


def test_review_rejects_amount_mismatch_before_it_can_create_a_ledger_entry():
    selection = _selection()
    repository = _Repository(_facts(bank_amount=299))
    workflow = RefundReturnReviewWorkflow(repository, _UnitOfWork)

    with pytest.raises(RefundReturnReviewWorkflowError) as raised:
        workflow.preview(selection, CorrelationId("preview"))

    assert raised.value.error.code == "refund_return_amount_mismatch"
    assert repository.calls == []


def _selection():
    return RefundReturnReviewSelection("finance-import-row:71", "client-ledger-entry:41", "C-1", "bank return receipt verified", ("bank-return-document:7",))


def _facts(bank_amount=300):
    return RefundReturnReviewFacts("finance-import-batch:4", 3, MoneyNTD(bank_amount), True, MoneyNTD(300), True, "C-1")


def _request(selection, fingerprint):
    return RefundReturnReviewApplyRequest(selection, ExpectedVersion(3), fingerprint, IdempotencyKey("refund-return-review-1"), ActorContext("tester"), CorrelationId("apply"))


class _UnitOfWork:
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def commit(self): return None


class _Repository:
    def __init__(self, facts): self.facts = facts; self.calls = []; self.stored = None
    def load_refund_return_review(self, _selection, *, for_update): return self.facts
    def find_refund_return_review_receipt(self, _key): return self.stored
    def append_refund_return_review(self, _candidate, _request): self.calls.append("append"); return "client-refund-return-review:12"
    def save_refund_return_review_receipt(self, _key, stored): self.calls.append("receipt"); self.stored = stored
