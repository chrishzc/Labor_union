from domains.client_finance.reconciliation import (
    ClientObligation,
    IncomingBankFact,
    PaymentStage,
    ReconciliationStatus,
    build_reconciliation_candidate,
)
from shared_kernel.money import MoneyNTD
import pytest

from shared_kernel.errors import ErrorCategory
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.reconciliation_workflow import (
    ClientReconciliationApplyRequest,
    ClientReconciliationError,
    ClientReconciliationFacts,
    ClientReconciliationWorkflow,
    ReconciliationSelection,
)


def test_client_receipt_overage_is_blocked_by_the_normal_action() -> None:
    candidate = build_reconciliation_candidate(_bank_facts(3000), _obligations(2500))

    assert candidate.status is ReconciliationStatus.REVIEW_REQUIRED
    assert candidate.blockers == ("client_receipt_overpaid",)
    assert candidate.allocations == ()


def test_client_receipt_overage_disposition_preserves_cash_and_creates_refund_amount() -> None:
    candidate = build_reconciliation_candidate(
        _bank_facts(3000),
        _obligations(2500),
        allow_overage_disposition=True,
    )

    assert candidate.status is ReconciliationStatus.OVERAGE
    assert candidate.bank_total == MoneyNTD(3000)
    assert sum(item.amount.amount for item in candidate.allocations) == 2500
    assert candidate.overage_amount == MoneyNTD(500)
    assert candidate.blockers == ("client_receipt_overpaid",)


def _bank_facts(amount: int) -> tuple[IncomingBankFact, ...]:
    return (IncomingBankFact("row-1", MoneyNTD(amount), PaymentStage.DEPOSIT),)


def _obligations(amount: int) -> tuple[ClientObligation, ...]:
    return (
        ClientObligation(
            "case-1:deposit",
            "case-1",
            MoneyNTD(amount),
            PaymentStage.DEPOSIT,
        ),
    )


def test_partial_receipt_requires_explicit_choice_and_preserves_unreceived_balance():
    normal = build_reconciliation_candidate(_bank_facts(9000), _obligations(10000))
    assert normal.status is ReconciliationStatus.REVIEW_REQUIRED
    assert normal.allocations == ()
    selected = build_reconciliation_candidate(_bank_facts(9000), _obligations(10000), allow_partial_receipt=True)
    assert selected.status is ReconciliationStatus.PARTIAL
    assert selected.bank_total.amount == 9000
    assert selected.obligation_total.amount - sum(a.amount.amount for a in selected.allocations) == 1000
    assert selected.settlement_identity != normal.settlement_identity
    assert selected.overage_amount.amount == 0


def test_two_same_case_bank_entries_can_be_reconciled_directly_by_their_total():
    banks = tuple(IncomingBankFact(str(i), MoneyNTD(value), PaymentStage.DEPOSIT) for i,value in enumerate((9000,1000)))
    candidate = build_reconciliation_candidate(banks, _obligations(10000))
    assert candidate.status is ReconciliationStatus.EXACT
    assert not candidate.blockers
    assert [a.amount.amount for a in candidate.allocations] == [9000,1000]


def test_case_level_preview_api_accepts_multiple_stages_without_a_phase_picker():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes.client_receipt_reconciliation import router
    from api.dependencies.client_receipt_reconciliation import get_client_receipt_reconciliation_application
    from api.dependencies.admin_auth import require_system_admin
    from types import SimpleNamespace
    class Repository:
        def load(self, selection, *, for_update):
            return ClientReconciliationFacts(1,tuple(IncomingBankFact(str(identity),MoneyNTD(amount),selection.payment_stage) for identity,amount in ((9,9000),(10,1000))),tuple(ClientObligation(stage,'CASE',MoneyNTD(5000),PaymentStage(stage)) for stage in ('first','second')))
    workflow=ClientReconciliationWorkflow(Repository(),lambda:None)
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[require_system_admin]=lambda:object()
    app.dependency_overrides[get_client_receipt_reconciliation_application]=lambda:SimpleNamespace(preview=workflow.preview)
    with TestClient(app) as client:
        response=client.post('/api/v1/orders/CASE/client-finance/receipt-reconciliation/preview',json={'finance_import_row_ids':[9,10],'obligation_identities':['first','second']})
    assert response.status_code==200
    assert response.json()['data']['candidate']['payment_stage'] is None
    assert response.json()['data']['candidate']['status']=='exact'
