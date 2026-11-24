from datetime import date, time

import pytest
from pydantic import ValidationError

from api.schemas.historical_unserved_correction import HistoricalUnservedCorrectionBody
from domains.orders.historical_unserved_correction import (
    HistoricalUnservedCorrectionIntent,
    HistoricalUnservedEvidence,
    historical_unserved_blockers,
    historical_unserved_review_codes,
)
from domains.orders.lifecycle import OrderEstablishmentEvidence, OrderLifecycleStatus
from domains.orders.terms import OrderTerms, ServiceTimeTerms
from shared_kernel.money import MoneyNTD
from subsystems.orders.historical_unserved_correction import build_historical_unserved_payroll_impact
from subsystems.payroll.terms_impact import (
    ExistingStaffObligationTermsFact,
    PayrollTermsActionKind,
    PayrollTermsSourceFacts,
    StaffObligationDirection,
    StaffObligationKind,
)


@pytest.mark.parametrize(
    ("establishment", "actual_service", "review_code"),
    [
        (OrderEstablishmentEvidence(), (), "historical_unserved_establishment_evidence_missing"),
        (
            OrderEstablishmentEvidence((12,)), ("service_day_log",),
            "historical_unserved_actual_service_evidence",
        ),
        (OrderEstablishmentEvidence((12,)), (), None),
    ],
)
def test_old_establishment_and_service_facts_prompt_review_without_blocking(
    establishment, actual_service, review_code,
):
    evidence = HistoricalUnservedEvidence(establishment, (), (13,), actual_service, None)

    assert historical_unserved_blockers(evidence, OrderLifecycleStatus.CANCELLED) == ()
    assert historical_unserved_review_codes(evidence) == ((review_code,) if review_code else ())


def test_correction_uses_operator_confirmation_even_without_legacy_receipts():
    evidence = HistoricalUnservedEvidence(
        OrderEstablishmentEvidence(current_owner_status=OrderLifecycleStatus.CANCELLED),
        (), (), ("service_day_log",), None,
        review_codes=("historical_unserved_cash_evidence_requires_review",),
    )

    assert historical_unserved_blockers(evidence, OrderLifecycleStatus.CANCELLED) == ()
    assert set(historical_unserved_review_codes(evidence)) == {
        "historical_unserved_not_historical",
        "historical_unserved_establishment_evidence_missing",
        "historical_unserved_actual_service_evidence",
        "historical_unserved_cash_evidence_requires_review",
    }
    assert not evidence.establishment.established
    assert HistoricalUnservedCorrectionIntent().resulting_status is OrderLifecycleStatus.ESTABLISHED_UNSERVED
    assert historical_unserved_blockers(evidence, OrderLifecycleStatus.COMPLETED) == (
        "historical_unserved_status_ineligible",
    )


def test_confirmation_is_required_and_text_is_optional():
    with pytest.raises(ValidationError, match="confirmed_actual_service_day_count"):
        HistoricalUnservedCorrectionBody()
    assert HistoricalUnservedCorrectionBody(confirmed_actual_service_day_count=0).to_intent() == (
        HistoricalUnservedCorrectionIntent("", "", 0)
    )
    with pytest.raises(ValidationError, match="historical_unserved_evidence_text_invalid"):
        HistoricalUnservedCorrectionBody(confirmed_actual_service_day_count=0, reason=" 修正")


@pytest.mark.parametrize("confirmation", [False, True, 1, 0.0, "0"])
def test_confirmation_requires_exact_actual_zero(confirmation):
    with pytest.raises(ValidationError, match="historical_unserved_confirmation_required"):
        HistoricalUnservedCorrectionBody(
            reason="歷史日期誤登", evidence_source="核對紀錄",
            confirmed_actual_service_day_count=confirmation,
        )


@pytest.mark.parametrize(("paid", "legacy_paid_marker"), [(0, False), (0, True), (3000, False), (3000, True)])
def test_payroll_zero_service_reuses_original_paid_or_unpaid_obligation(paid, legacy_paid_marker):
    original = ExistingStaffObligationTermsFact(
        "svc-1", 42, 3, StaffObligationKind.SERVICE_PAY, StaffObligationDirection.PAYABLE_TO_STAFF,
        MoneyNTD(8000), MoneyNTD(8000 - paid), MoneyNTD(paid), bool(paid), None,
        historically_settled=legacy_paid_marker,
    )
    source = PayrollTermsSourceFacts("CASE-1", 4, (), (original,), None)
    terms = OrderTerms(date(2026, 8, 1), 12, 8, MoneyNTD(0), ServiceTimeTerms(time(8), time(16), 0))

    impact = build_historical_unserved_payroll_impact(source, terms, "historical-unserved:case-1")

    assert impact.payroll.assignments == ()
    assert impact.payroll.total_payable == MoneyNTD(0)
    assert len(impact.actions) == 1
    if paid:
        assert impact.actions[0].action is PayrollTermsActionKind.APPEND_FROZEN_DIFFERENCE
        assert impact.actions[0].source_obligation_identity == original.obligation_identity
        assert impact.frozen_settlements[0].recovery_increase == MoneyNTD(paid)
        assert impact.frozen_settlements[0].paid_net_amount == MoneyNTD(paid)
    else:
        assert impact.actions[0].action is PayrollTermsActionKind.CLOSE_UNPAID
        assert impact.actions[0].obligation_identity == original.obligation_identity
        assert impact.frozen_settlements == ()
