"""Integer floor-fee proration and deterministic allocation."""

from __future__ import annotations

from collections.abc import Mapping

from shared_kernel.money import MoneyNTD
from shared_kernel.validation import (
    require_nonnegative_integer,
    require_positive_integer,
)


def prorate_floor_fee(
    contractual_fee: MoneyNTD,
    contracted_service_days: int,
    actual_service_days: int,
) -> MoneyNTD:
    if not isinstance(contractual_fee, MoneyNTD):
        raise TypeError("contractual floor fee must be MoneyNTD")
    require_positive_integer(
        contracted_service_days, "contracted service days"
    )
    require_nonnegative_integer(actual_service_days, "actual service days")
    if actual_service_days > contracted_service_days:
        raise ValueError("actual service days exceed contracted service days")
    numerator = contractual_fee.amount * actual_service_days
    quotient, remainder = divmod(numerator, contracted_service_days)
    rounded = quotient + (1 if remainder * 2 >= contracted_service_days else 0)
    return MoneyNTD(rounded)


def allocate_largest_remainder(
    total: MoneyNTD,
    weights: Mapping[str, int],
) -> dict[str, MoneyNTD]:
    if not isinstance(total, MoneyNTD):
        raise TypeError("allocation total must be MoneyNTD")
    _validate_weights(weights)
    if not weights:
        if total.is_zero:
            return {}
        raise ValueError("positive allocation requires weights")
    weight_total = sum(weights.values())
    bases = {
        identity: total.amount * weight // weight_total
        for identity, weight in weights.items()
    }
    _distribute_remainder(total.amount, weights, bases, weight_total)
    return {identity: MoneyNTD(value) for identity, value in bases.items()}


def _validate_weights(weights) -> None:
    if not isinstance(weights, Mapping):
        raise TypeError("allocation weights must be a mapping")
    if any(not isinstance(key, str) or not key.strip() for key in weights):
        raise ValueError("allocation identities must be nonempty strings")
    if any(not isinstance(value, int) or value <= 0 for value in weights.values()):
        raise ValueError("allocation weights must be positive integers")


def _distribute_remainder(total, weights, bases, weight_total) -> None:
    remainder_count = total - sum(bases.values())
    ranking = sorted(
        weights,
        key=lambda identity: (
            -(total * weights[identity] % weight_total),
            identity,
        ),
    )
    for identity in ranking[:remainder_count]:
        bases[identity] += 1


__all__ = ["allocate_largest_remainder", "prorate_floor_fee"]
