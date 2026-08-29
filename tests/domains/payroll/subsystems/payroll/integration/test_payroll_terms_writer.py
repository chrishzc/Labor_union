from types import SimpleNamespace

from infrastructure.mysql.payroll_terms_writer import _action_requires_event
from shared_kernel.money import MoneyNTD
from subsystems.payroll.terms_impact import PayrollTermsActionKind


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
