from dataclasses import replace
from datetime import date, datetime, time

import pytest

from domains.client_finance.obligation_planning import (
    ClientChargeDay,
    ClientFinanceTermsFacts,
    ClientPaymentTerms,
    ExistingClientStageObligation,
)
from domains.client_finance.reconciliation import PaymentStage
from domains.orders.contract_completion import (
    ContractCompletionBlocker,
    ContractCompletionFacts,
    ContractCompletionIntent,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.orders.terms import ServiceTimeTerms
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.orders.contract_completion_workflow import (
    ContractCompletionApplyRequest,
    ContractCompletionCommandClaimState,
    ContractCompletionWorkflow,
    ContractCompletionWorkflowError,
    ContractCompletionWorkflowFacts,
    StoredContractCompletionReceipt,
)


class _UnitOfWork:
    committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True


class _Repository:
    def __init__(self, facts):
        self.facts = facts
        self.receipt = None
        self.claim_state = ContractCompletionCommandClaimState.CREATED
        self.persisted = []

    def load_for_preview(self, _): return self.facts
    def load_for_apply(self, _): return self.facts
    def claim_command(self, *_): return self.claim_state
    def find_receipt(self, *_args, **_kwargs): return self.receipt
    def record_contract_identity(self, case_no, identity):
        assert case_no == self.facts.order.case_no
        current = self.facts.order.contract_identity
        if current is not None and current != identity:
            raise ValueError("contract_identity_already_recorded")
        self.facts = replace(
            self.facts,
            order=replace(self.facts.order, contract_identity=identity),
        )
    def append_contract_completion_event(self, *_): self.persisted.append("contract"); return 7
    def persist_client_finance_impact(self, command): self.persisted.append(command)
    def append_lifecycle_event(self, command): self.persisted.append(command); return 8
    def update_order_projection(self, command): self.persisted.append(command)
    def append_outbox_intent(self, *_): self.persisted.append("outbox")
    def save_receipt(self, command):
        self.persisted.append(command)
        self.receipt = command.stored_receipt


def _facts(*, charge_days=2, existing_obligations=()):
    order = ContractCompletionFacts(
        "CASE-1", 4, "CONTRACT-1", False, OrderLifecycleStatus.DISCUSSION,
        True, ServiceTimeTerms(time(8), time(17), 0),
    )
    finance = ClientFinanceTermsFacts(
        "CASE-1", 6, 8, MoneyNTD(0),
        tuple(ClientChargeDay(date(2026, 8, day), False) for day in range(1, charge_days + 1)),
        ClientPaymentTerms(0, MoneyNTD(100), date(2026, 7, 1), date(2026, 8, 1), None), existing_obligations,
    )
    return ContractCompletionWorkflowFacts(order, finance, 2)


def _workflow(repository):
    return ContractCompletionWorkflow(
        repository, _UnitOfWork,
        FixedBusinessClock(datetime(2026, 8, 3, 9, 0).astimezone()),
    )


def _request(preview):
    return ContractCompletionApplyRequest(
        "CASE-1", ContractCompletionIntent.CONFIRM_COMPLETED,
        ExpectedVersion(4), ExpectedVersion(6), preview.fingerprint,
        IdempotencyKey("contract-complete-1"), ActorContext("admin"),
        "service completed", CorrelationId("corr-1"),
    )


def test_preview_apply_persists_canonical_contract_completion_chain():
    repository = _Repository(_facts())
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", ContractCompletionIntent.CONFIRM_COMPLETED)
    receipt = workflow.apply(_request(preview))
    assert receipt.order_version == 5
    assert receipt.client_finance_version == 7
    assert receipt.lifecycle_status is OrderLifecycleStatus.ESTABLISHED
    assert repository.persisted[0] == "contract"
    assert repository.persisted[-1].stored_receipt.receipt == receipt


def test_apply_borrowed_leaves_commit_to_outer_owner():
    repository = _Repository(_facts())
    unit_of_work = _UnitOfWork()
    workflow = ContractCompletionWorkflow(
        repository,
        lambda: unit_of_work,
        FixedBusinessClock(datetime(2026, 8, 3, 9, 0).astimezone()),
    )
    preview = workflow.preview("CASE-1", ContractCompletionIntent.CONFIRM_COMPLETED)

    receipt = workflow.apply_borrowed(_request(preview))

    assert receipt.contract_completed is True
    assert repository.persisted[-1].stored_receipt.receipt == receipt
    assert unit_of_work.committed is False


def test_preview_and_borrowed_apply_can_bind_the_final_pdf_identity() -> None:
    facts = _facts()
    repository = _Repository(
        replace(facts, order=replace(facts.order, contract_identity=None))
    )
    workflow = _workflow(repository)
    identity = "external-final:" + "a" * 64
    preview = workflow.preview_with_identity(
        "CASE-1", ContractCompletionIntent.CONFIRM_COMPLETED, identity
    )

    receipt = workflow.apply_borrowed_with_identity(_request(preview), identity)

    assert receipt.contract_identity == identity
    assert repository.facts.order.contract_identity == identity


def test_final_pdf_preview_can_project_missing_commitment_dates_without_writing() -> None:
    initial = _facts(charge_days=0)
    facts = replace(initial, order=replace(initial.order, contract_identity=None))
    repository = _Repository(facts)
    workflow = _workflow(repository)
    identity = "external-final:" + "b" * 64
    service_dates = tuple(
        date(2026, 8, day) for day in range(1, facts.contracted_service_day_count + 1)
    )

    preview = workflow.preview_with_identity(
        "CASE-1",
        ContractCompletionIntent.CONFIRM_COMPLETED,
        identity,
        fallback_service_dates=service_dates,
    )

    assert len(preview.client_finance_impact.actions) > 0
    assert repository.persisted == []


def test_apply_replays_matching_receipt_without_new_writes():
    repository = _Repository(_facts())
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", ContractCompletionIntent.CONFIRM_COMPLETED)
    request = _request(preview)
    first = workflow.apply(request)
    second = workflow.apply(request)
    assert second == first
    assert len(repository.persisted) == 6


def test_query_reports_official_service_dates_blocker():
    workflow = _workflow(_Repository(_facts(charge_days=1)))
    query = workflow.query("CASE-1")
    assert query.completion_available is False
    assert query.domain_blockers == (
        ContractCompletionBlocker.OFFICIAL_SERVICE_DATES_INCOMPLETE,
    )


def test_apply_rejects_stale_client_finance_version():
    repository = _Repository(_facts())
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", ContractCompletionIntent.CONFIRM_COMPLETED)
    request = ContractCompletionApplyRequest(
        "CASE-1", ContractCompletionIntent.CONFIRM_COMPLETED,
        ExpectedVersion(4), ExpectedVersion(5), preview.fingerprint,
        IdempotencyKey("contract-complete-2"), ActorContext("admin"),
        "service completed", CorrelationId("corr-2"),
    )
    with pytest.raises(ContractCompletionWorkflowError, match="Client Finance"):
        workflow.apply(request)


def test_contract_completion_carries_the_one_precontract_deposit_obligation():
    deposit = ExistingClientStageObligation(
        "client-obligation:CASE-1:deposit", PaymentStage.DEPOSIT,
        MoneyNTD(0), MoneyNTD(0), date(2026, 7, 1), False,
    )

    query = _workflow(_Repository(_facts(existing_obligations=(deposit,)))).query("CASE-1")

    assert query.completion_available is True


def test_completion_preserves_current_tiered_case_pricing_and_existing_receivables():
    import re
    from decimal import Decimal
    from domains.client_finance.obligation_planning import ClientFinanceTermsSourceFacts
    from infrastructure.mysql.order_contract_completion_repository import _select_order
    from infrastructure.mysql.order_terms_read_model import _materialize_contract_client_finance_facts
    from infrastructure.mysql.pricing_configuration_repository import load_case_pricing

    order = {
        "case_no": "CASE-1", "contract_identity": "CONTRACT-1", "lifecycle_version": 4,
        "status": "洽談中", "service_days": 6, "service_hours_per_day": 7,
        "floor_fee": 500, "service_start_time": time(9), "service_end_time": time(16),
        "service_end_day_offset": 0, "actual_start_date": None,
        "pricing_policy_id": None, "pricing_override_event_id": 9, "pricing_revision": 1,
        "client_identity_status": "一般市民",
    }
    pricing = {"identity_name": "一般市民", "rule": "citizen", "subsidy_hours": 40,
               "client": {"covered": 400, "excess": 500},
               "payroll": {"covered": 400, "excess": 500}}

    class Cursor:
        def execute(self, sql, params):
            if "FROM orders" in sql:
                assert params == ("CASE-1",)
                # Simulate the actual selected columns, so an omitted binding
                # cannot accidentally remain in an overgenerous fake DB row.
                self.row = {key: value for key, value in order.items()
                            if re.search(rf"\b{key}\b", sql)}
            elif "FROM case_pricing_events" in sql:
                assert params == (9, "CASE-1")
                self.row = {"pricing_json": pricing}
            else:
                raise AssertionError(sql)

        def fetchone(self):
            return self.row

    cursor = Cursor()
    selected = _select_order(cursor, "CASE-1", lock=True)
    current_pricing = load_case_pricing(cursor, selected, lock=True)
    assert current_pricing is not None and current_pricing.subsidy_hours == Decimal(40)
    stages = (
        ExistingClientStageObligation("client-obligation:CASE-1:deposit", PaymentStage.DEPOSIT,
                                      MoneyNTD(14500), MoneyNTD(0), date(2026, 7, 1), False),
        ExistingClientStageObligation("client-obligation:CASE-1:first", PaymentStage.FIRST,
                                      MoneyNTD(3000), MoneyNTD(0), date(2026, 8, 1), False),
    )
    source = ClientFinanceTermsSourceFacts(
        "CASE-1", 6, ClientPaymentTerms(5, MoneyNTD(400), date(2026, 7, 1), date(2026, 8, 1), None),
        (), stages, identity_status="一般市民", pricing=current_pricing,
    )
    finance = _materialize_contract_client_finance_facts(selected,
        tuple(ClientChargeDay(date(2026, 8, day), False) for day in range(1, 7)), source)
    facts = replace(_facts(), client_finance=finance, contracted_service_day_count=6)
    preview = _workflow(_Repository(facts)).preview("CASE-1", ContractCompletionIntent.CONFIRM_COMPLETED)
    assert {row.payment_stage: row.amount.amount for row in preview.client_finance_impact.stage_plans} == {
        PaymentStage.DEPOSIT: 14500, PaymentStage.FIRST: 3000, PaymentStage.SECOND: 0,
    }
    assert all(action.action.value == "unchanged" for action in preview.client_finance_impact.actions)
    assert preview.client_finance_impact.resulting_account_version == 6
    assert preview.client_finance_impact.payment_terms is None
