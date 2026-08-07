"""Unit contracts for the typed Client Finance to Orders outbox boundary."""

from __future__ import annotations

import pytest

from subsystems.orders.client_finance_outbox_consumer import _settlement_identity


def test_orders_delivery_requires_a_canonical_settlement_identity() -> None:
    identity = "a" * 64

    assert _settlement_identity({"settlement_identity": identity}) == identity


@pytest.mark.parametrize("value", (None, "short", 1))
def test_orders_delivery_rejects_invalid_settlement_identity(value) -> None:
    with pytest.raises(ValueError, match="settlement identity"):
        _settlement_identity({"settlement_identity": value})
