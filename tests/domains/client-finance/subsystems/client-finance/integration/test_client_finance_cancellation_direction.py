"""
File: test_client_finance_cancellation_direction.py
Description: 驗證取消帳務方向與金額的 server-owned typed contract。
"""

from datetime import date

import pytest

from api.schemas.order_cancellation import ClientFinanceActionView
from domains.client_finance.obligation_planning import (
    ClientFinanceDirection,
    ClientObligationAction,
    ClientObligationActionKind,
)
from domains.client_finance.reconciliation import PaymentStage
from shared_kernel.money import MoneyNTD


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
