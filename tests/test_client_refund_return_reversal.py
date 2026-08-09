import pytest

from domains.client_finance.client_refund_reversal import (
    ClientLedgerAllocationFact,
    ClientReversalTarget,
    ClientRefundReturnBankFact,
    build_client_reversal_candidate,
    build_client_refund_return_candidate,
)
from infrastructure.mysql.client_refund_reversal_repository import (
    _reopen_payable_obligations,
)
from shared_kernel.money import MoneyNTD
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.client_refund_reversal_workflow import (
    ClientRefundReversalApplyRequest,
    ClientRefundReversalFacts,
    ClientRefundReversalSelection,
    ClientRefundReversalWorkflow,
)
from domains.client_finance.client_refund_reversal import ClientFinanceCorrectionType


def test_returned_refund_builds_a_refund_reversal_candidate():
    target = ClientReversalTarget(
        "41", "C-1", "refund", MoneyNTD(300), MoneyNTD(0), "2026-08-04",
        (ClientLedgerAllocationFact("refund-1", MoneyNTD(300)),),
    )

    candidate = build_client_reversal_candidate("C-1", (target,))

    assert candidate.reversal_entry_type == "refund"
    assert candidate.entries[0].reversal_of_entry_identity == "41"
    assert candidate.entries[0].entry_type == "refund_reversal"


def test_returned_refund_reopens_the_original_payable_balance():
    target = ClientReversalTarget(
        "41", "C-1", "refund", MoneyNTD(300), MoneyNTD(0), "2026-08-04",
        (ClientLedgerAllocationFact("refund-1", MoneyNTD(300)),),
    )
    cursor = _Cursor()

    _reopen_payable_obligations(
        cursor,
        build_client_reversal_candidate("C-1", (target,)),
        {"refund-1": 300},
        8,
    )

    assert cursor.params == (300, 8, "refund-1", "C-1")
    assert "amount_due_ntd=amount_due_ntd+%s" in cursor.sql


def test_returned_union_subsidy_advance_uses_its_own_reversal_type():
    target = ClientReversalTarget(
        "42", "C-1", "subsidy_advance", MoneyNTD(300), MoneyNTD(0), "2026-08-04",
        (ClientLedgerAllocationFact("subsidy-1", MoneyNTD(300)),),
    )

    candidate = build_client_reversal_candidate("C-1", (target,))

    assert candidate.entries[0].entry_type == "subsidy_advance_reversal"


def test_bank_backed_customer_refund_return_reopens_only_the_original_refund():
    target = ClientReversalTarget(
        "41", "C-1", "refund", MoneyNTD(300), MoneyNTD(0), "2026-08-04",
        (ClientLedgerAllocationFact("refund-1", MoneyNTD(300)),),
    )
    bank_return = ClientRefundReturnBankFact(
        "bank-return-7", "C-1", MoneyNTD(300), "2026-08-05"
    )

    candidate = build_client_refund_return_candidate("C-1", bank_return, target)

    assert candidate.correction_type.value == "refund_return"
    assert candidate.entries[0].entry_type == "refund_reversal"
    assert candidate.entries[0].finance_import_row_identity == "bank-return-7"


def test_bank_return_rejects_wrong_amount_or_already_reversed_refund():
    target = ClientReversalTarget(
        "41", "C-1", "refund", MoneyNTD(300), MoneyNTD(0), "2026-08-04",
        (ClientLedgerAllocationFact("refund-1", MoneyNTD(300)),),
    )
    wrong_amount = ClientRefundReturnBankFact(
        "bank-return-7", "C-1", MoneyNTD(299), "2026-08-05"
    )

    with pytest.raises(ValueError, match="client_refund_return_invalid"):
        build_client_refund_return_candidate("C-1", wrong_amount, target)

    reversed_target = ClientReversalTarget(
        "41", "C-1", "refund", MoneyNTD(300), MoneyNTD(300), "2026-08-04",
        (ClientLedgerAllocationFact("refund-1", MoneyNTD(300)),),
    )
    with pytest.raises(ValueError, match="client_refund_return_invalid"):
        build_client_refund_return_candidate(
            "C-1",
            ClientRefundReturnBankFact("bank-return-7", "C-1", MoneyNTD(300), "2026-08-05"),
            reversed_target,
        )


def test_refund_return_apply_claims_bank_fact_reopens_payable_and_replays():
    selection = ClientRefundReversalSelection(
        "C-1", ClientFinanceCorrectionType.REFUND_RETURN,
        bank_fact_identities=("7",), reversal_target_identities=("41",),
    )
    repository = _WorkflowRepository()
    workflow = ClientRefundReversalWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(selection, CorrelationId("refund-return-preview"))
    request = ClientRefundReversalApplyRequest(
        selection, ExpectedVersion(3), preview.fingerprint,
        IdempotencyKey("refund-return-apply"), ActorContext("tester"),
        "verified returned transfer", CorrelationId("refund-return-apply"),
    )

    receipt = workflow.apply(request)

    assert receipt.correction_type is ClientFinanceCorrectionType.REFUND_RETURN
    assert repository.called == ["ledger", "allocation", "projection", "outbox", "receipt"]
    assert workflow.apply(request) == receipt


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


class _WorkflowRepository:
    def __init__(self):
        self.called = []
        self.receipt = None

    def load(self, selection, *, for_update):
        del selection, for_update
        target = ClientReversalTarget(
            "41", "C-1", "refund", MoneyNTD(300), MoneyNTD(0), "2026-08-04",
            (ClientLedgerAllocationFact("refund-1", MoneyNTD(300)),),
        )
        return ClientRefundReversalFacts(
            3, reversal_targets=(target,), refund_return_bank_facts=(
                ClientRefundReturnBankFact("7", "C-1", MoneyNTD(300), "2026-08-05"),
            ),
        )

    def find_receipt(self, _):
        return self.receipt

    def append_ledger_entries(self, _): self.called.append("ledger")
    def append_allocations(self, _): self.called.append("allocation")
    def update_projection(self, _, __): self.called.append("projection")
    def append_outbox(self, _, __): self.called.append("outbox")

    def save_receipt(self, _, receipt):
        self.called.append("receipt")
        self.receipt = receipt


class _Cursor:
    rowcount = 1
    sql = ""
    params = ()

    def execute(self, sql, params):
        self.sql = sql
        self.params = params
