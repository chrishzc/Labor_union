from datetime import date

from domains.client_finance.obligation_planning import (
    ClientChargeDay,
    ClientFinanceTermsFacts,
    ClientPaymentTerms,
    build_precontract_deposit_candidate,
    precontract_deposit_terms_impact,
)
from domains.client_finance.reconciliation import PaymentStage
from shared_kernel.money import MoneyNTD


def test_signed_commitment_creates_only_the_deposit_obligation_before_client_signature():
    candidate = build_precontract_deposit_candidate(
        _facts(), "commitment:case-1:plan-1",
    )

    assert candidate.mutates is True
    assert candidate.expected_account_version == 0
    assert candidate.resulting_account_version == 1
    assert candidate.deposit_stage.payment_stage is PaymentStage.DEPOSIT
    assert candidate.deposit_stage.amount == MoneyNTD(16000)
    assert candidate.deposit_action.payment_stage is PaymentStage.DEPOSIT
    assert candidate.deposit_action.obligation_identity == "client-obligation:CASE-1:deposit"
    impact = precontract_deposit_terms_impact(candidate)
    assert [item.payment_stage for item in impact.stage_plans] == [PaymentStage.DEPOSIT]
    assert [item.payment_stage for item in impact.actions] == [PaymentStage.DEPOSIT]


def _facts() -> ClientFinanceTermsFacts:
    return ClientFinanceTermsFacts(
        case_no="CASE-1",
        account_version=0,
        service_hours_per_day=8,
        floor_fee=MoneyNTD(0),
        charge_days=tuple(
            ClientChargeDay(date(2026, 8, day), False)
            for day in range(10, 15)
        ),
        payment_terms=ClientPaymentTerms(
            deposit_service_days=5,
            client_hourly_rate=MoneyNTD(400),
            deposit_due_date=date(2026, 8, 1),
            first_payment_due_date=date(2026, 8, 10),
            second_payment_due_date=None,
        ),
        existing_obligations=(),
    )
