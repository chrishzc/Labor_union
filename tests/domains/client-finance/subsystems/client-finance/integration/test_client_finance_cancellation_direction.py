"""
File: test_client_finance_cancellation_direction.py
Description: 驗證取消帳務方向與金額的 server-owned typed contract。
"""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from api.schemas.order_cancellation import ClientFinanceActionView
from domains.client_finance.obligation_planning import (
    ClientChargeDay,
    ClientFinanceDirection,
    ClientSubsidyReturnPlan,
    ClientObligationAction,
    ClientObligationActionKind,
    ClientFinanceTermsSourceFacts,
    ClientPaymentTerms,
    build_client_finance_terms_candidate,
    build_client_finance_terms_impact,
)
from domains.orders.terms import OrderTerms, ServiceTimeTerms
from domains.scheduling.generation import AssignmentCandidate, SchedulingGenerationCandidate
from infrastructure.mysql.client_finance_terms_writer import (
    persist_client_finance_terms_impact,
)
from infrastructure.mysql.order_terms_read_model import (
    _materialize_contract_client_finance_facts,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.orders.terms_workflow import ClientFinanceImpactPersistenceCommand
from domains.client_finance.reconciliation import PaymentStage
from shared_kernel.money import MoneyNTD


def test_full_subsidy_terms_do_not_create_client_service_principal() -> None:
    dates = tuple(date(2026, 8, day) for day in range(1, 16))
    scheduling = SchedulingGenerationCandidate(
        "CASE-FULL-SUBSIDY",
        2,
        1,
        2,
        (1,),
        (
            AssignmentCandidate(
                "CASE-FULL-SUBSIDY:g2:a1",
                1,
                7,
                1,
                dates[0],
                dates[-1],
                dates,
                120,
            ),
        ),
        (),
    )
    source = ClientFinanceTermsSourceFacts(
        "CASE-FULL-SUBSIDY",
        3,
        ClientPaymentTerms(
            0,
            MoneyNTD(350),
            date(2026, 7, 1),
            date(2026, 8, 1),
            date(2026, 8, 15),
        ),
        (),
        (),
        identity_status="補助市民",
    )
    terms = OrderTerms(
        dates[0],
        15,
        8,
        MoneyNTD(0),
        ServiceTimeTerms(None, None, None),
    )

    candidate = build_client_finance_terms_impact(
        source,
        terms,
        scheduling,
        "actual-start:full-subsidy",
    )

    assert sum(plan.amount.amount for plan in candidate.stage_plans) == 0


def test_shared_contract_finance_reader_preserves_full_subsidy_waiver() -> None:
    start = date(2026, 10, 1)
    charge_days = tuple(
        ClientChargeDay(start + timedelta(days=offset), False)
        for offset in range(15)
    )
    source = ClientFinanceTermsSourceFacts(
        case_no="115000010",
        account_version=3,
        payment_terms=ClientPaymentTerms(
            deposit_service_days=5,
            client_hourly_rate=MoneyNTD(350),
            deposit_due_date=date(2026, 9, 20),
            first_payment_due_date=date(2026, 10, 1),
            second_payment_due_date=date(2026, 10, 15),
        ),
        double_pay_dates=(),
        existing_obligations=(),
        identity_status="補助市民",
    )

    facts = _materialize_contract_client_finance_facts(
        {"case_no": "115000010", "service_hours_per_day": 8, "floor_fee": 0},
        charge_days,
        source,
    )
    candidate = build_client_finance_terms_candidate(facts, "test-full-subsidy")

    assert facts.client_service_charge_waived is True
    assert sum(stage.amount.amount for stage in candidate.stage_plans) == 0


def _action(
    kind: ClientObligationActionKind,
    before: int,
    after: int,
    direction: ClientFinanceDirection,
    direction_amount: int,
) -> ClientObligationAction:
    return ClientObligationAction(
        kind,
        PaymentStage.FIRST,
        "client-obligation:CASE-1:first",
        MoneyNTD(before),
        MoneyNTD(after),
        MoneyNTD(abs(after - before)),
        date(2026, 8, 1),
        date(2026, 8, 2),
        None,
        direction,
        direction_amount,
    )


@pytest.mark.parametrize(
    ("kind", "before", "after", "direction", "amount"),
    (
        (
            ClientObligationActionKind.CREATE_STAGE,
            0,
            8000,
            ClientFinanceDirection.ADDITIONAL_CHARGE_DUE,
            8000,
        ),
        (
            ClientObligationActionKind.REPLACE_OPEN,
            8000,
            10000,
            ClientFinanceDirection.ADDITIONAL_CHARGE_DUE,
            2000,
        ),
        (
            ClientObligationActionKind.REPLACE_OPEN,
            10000,
            8000,
            ClientFinanceDirection.NO_FINANCE_CHANGE,
            0,
        ),
        (
            ClientObligationActionKind.REPLACE_OPEN,
            8000,
            8000,
            ClientFinanceDirection.NO_FINANCE_CHANGE,
            0,
        ),
        (
            ClientObligationActionKind.CANCEL_OPEN,
            8000,
            0,
            ClientFinanceDirection.NO_FINANCE_CHANGE,
            0,
        ),
        (
            ClientObligationActionKind.CREATE_ADJUSTMENT,
            8000,
            10000,
            ClientFinanceDirection.ADDITIONAL_CHARGE_DUE,
            2000,
        ),
        (
            ClientObligationActionKind.CREATE_REFUND,
            10000,
            8000,
            ClientFinanceDirection.REFUND_DUE,
            2000,
        ),
        (
            ClientObligationActionKind.UNCHANGED,
            8000,
            8000,
            ClientFinanceDirection.NO_FINANCE_CHANGE,
            0,
        ),
    ),
)
def test_action_accepts_canonical_direction_mapping(
    kind, before, after, direction, amount
) -> None:
    action = _action(kind, before, after, direction, amount)

    assert action.direction is direction
    assert action.direction_amount_ntd == amount


def test_action_rejects_direction_inferred_from_action_or_signed_amount() -> None:
    with pytest.raises(ValueError, match="client_finance_direction_mismatch"):
        _action(
            ClientObligationActionKind.CREATE_REFUND,
            10000,
            8000,
            ClientFinanceDirection.ADDITIONAL_CHARGE_DUE,
            2000,
        )

    with pytest.raises(ValueError, match="client_finance_direction_amount_mismatch"):
        _action(
            ClientObligationActionKind.CREATE_REFUND,
            10000,
            8000,
            ClientFinanceDirection.REFUND_DUE,
            1,
        )


def test_api_view_requires_direction_and_nonnegative_direction_amount() -> None:
    payload = {
        "action": "create_refund",
        "payment_stage": "first",
        "obligation_identity": "client-obligation:CASE-1:first",
        "before_amount": {"amount": 10000},
        "after_amount": {"amount": 8000},
        "obligation_amount": {"amount": 2000},
        "before_due_date": date(2026, 8, 1),
        "after_due_date": date(2026, 8, 2),
        "source_obligation_identity": None,
        "direction": "refund_due",
        "direction_amount_ntd": 2000,
    }

    assert ClientFinanceActionView.model_validate(payload).direction == "refund_due"
    with pytest.raises(ValueError):
        ClientFinanceActionView.model_validate({**payload, "direction_amount_ntd": -1})
    with pytest.raises(ValueError, match="financial direction amount must be positive"):
        ClientFinanceActionView.model_validate({**payload, "direction_amount_ntd": 0})
    with pytest.raises(ValueError, match="no_finance_change direction amount must be zero"):
        ClientFinanceActionView.model_validate(
            {
                **payload,
                "direction": "no_finance_change",
                "direction_amount_ntd": 1,
            }
        )


class _Cursor:
    def __init__(self):
        self.statements = []
        self.lastrowid = 20
        self.rowcount = 1

    def execute(self, statement, parameters):
        self.statements.append((" ".join(statement.split()), parameters))
        if "INSERT INTO client_obligation_events" in statement:
            self.lastrowid += 1


def test_cancellation_writer_persists_subsidy_return_as_separate_client_payable():
    cursor = _Cursor()
    plan = ClientSubsidyReturnPlan(
        "client-subsidy-return:CASE-1:terminal",
        MoneyNTD(14_400),
        date(2026, 10, 15),
    )
    candidate = SimpleNamespace(
        case_no="CASE-1",
        expected_account_version=5,
        resulting_account_version=6,
        actions=(),
        subsidy_return_plan=plan,
        fingerprint=PreviewFingerprint("a" * 64),
    )
    command = ClientFinanceImpactPersistenceCommand(
        candidate,
        IdempotencyKey("cancel-client-finance-1"),
        ActorContext("admin"),
        "mid-service cancellation",
        CorrelationId("cancel-client-finance-test"),
        "order-cancellation",
        9,
    )

    persist_client_finance_terms_impact(cursor, command)

    event = next(
        values
        for statement, values in cursor.statements
        if "INSERT INTO client_obligation_events" in statement
    )
    projection = next(
        values
        for statement, values in cursor.statements
        if "INSERT INTO client_obligations" in statement
    )
    assert event[2:5] == ("subsidy_return", "payable_to_client", "established")
    assert event[6] == 14_400
    assert projection[2:7] == (
        "subsidy_return",
        "payable_to_client",
        None,
        14_400,
        date(2026, 10, 15),
    )
