"""Delegate zero-service historical payable corrections to Payroll."""

from domains.orders.terms import OrderTerms
from domains.payroll.historical_calculation import HistoricalCasePayrollCandidate
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.money import MoneyNTD
from subsystems.payroll.terms_impact import (
    HistoricalPayrollAllocation,
    PayrollTermsImpactCandidate,
    PayrollTermsSourceFacts,
    build_historical_payroll_attribution_impact,
)


def build_historical_unserved_payroll_impact(
    source: PayrollTermsSourceFacts,
    order_terms: OrderTerms,
    change_identity: str,
) -> PayrollTermsImpactCandidate:
    zero = MoneyNTD(0)
    payroll = HistoricalCasePayrollCandidate(
        (), zero, zero,
        fingerprint_payload({"case_no": source.case_no, "historical_confirmed_service_days": 0}),
    )
    return build_historical_payroll_attribution_impact(
        source, HistoricalPayrollAllocation(source.case_no, ()), payroll, (), order_terms, change_identity,
        confirmed_zero_service=True,
    )
