"""Integer New Taiwan Dollar value object."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MoneyNTD:
    amount: int

    def __post_init__(self) -> None:
        if isinstance(self.amount, bool) or not isinstance(self.amount, int):
            raise TypeError("MoneyNTD amount must be an integer")

    def __add__(self, other: Any) -> MoneyNTD:
        if not isinstance(other, MoneyNTD):
            return NotImplemented
        return MoneyNTD(self.amount + other.amount)

    def __sub__(self, other: Any) -> MoneyNTD:
        if not isinstance(other, MoneyNTD):
            return NotImplemented
        return MoneyNTD(self.amount - other.amount)

    def __mul__(self, multiplier: Any) -> MoneyNTD:
        if isinstance(multiplier, bool) or not isinstance(multiplier, int):
            return NotImplemented
        return MoneyNTD(self.amount * multiplier)

    def __neg__(self) -> MoneyNTD:
        return MoneyNTD(-self.amount)

    @property
    def is_zero(self) -> bool:
        return self.amount == 0
