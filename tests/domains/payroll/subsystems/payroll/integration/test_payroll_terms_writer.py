from datetime import date
from types import SimpleNamespace

from infrastructure.mysql.payroll_terms_writer import (
    _action_requires_event,
)
from shared_kernel.money import MoneyNTD
from subsystems.payroll.terms_impact import (
    _candidate,
    PayrollTermsActionKind,
)


def test_zero_amount_payroll_action_does_not_create_an_immutable_event():
    action = SimpleNamespace(
        action=PayrollTermsActionKind.ESTABLISH,
        amount=MoneyNTD(0),
    )

    assert _action_requires_event(action) is False


def test_nonzero_payroll_action_still_creates_an_immutable_event():
    action = SimpleNamespace(
        action=PayrollTermsActionKind.CLOSE_UNPAID,
        amount=MoneyNTD(1),
    )

    assert _action_requires_event(action) is True


def test_legacy_dates_do_not_create_payroll_events_or_change_candidate_fingerprint():
    def facts(service_date):
        return SimpleNamespace(
            case_no="CASE-1",
            payroll_version=3,
            scheduling=SimpleNamespace(
                assignments=(
                    SimpleNamespace(
                        candidate_key="case-1:g2:a1",
                        sequence=1,
                        double_pay_dates=(service_date,),
                    ),
                )
            ),
        )

    payroll = SimpleNamespace(fingerprint=SimpleNamespace(value="payroll-facts"))

    first = _candidate(facts(date(2026, 8, 8)), payroll, (), ())
    second = _candidate(facts(date(2026, 8, 9)), payroll, (), ())

    assert first.special_pay_events == ()
    assert first.fingerprint == second.fingerprint
