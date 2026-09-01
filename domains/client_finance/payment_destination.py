"""Client Finance rules for the union collection payment destination."""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel.validation import require_canonical_text


@dataclass(frozen=True, slots=True)
class ClientPaymentDestination:
    account_display: str
    revision: int

    def __post_init__(self) -> None:
        require_canonical_text(self.account_display, "union collection account", 255)
        if self.revision < 0:
            raise ValueError("client_payment_destination_revision_invalid")


def canonical_account_display(value: str) -> str:
    return require_canonical_text(value, "union collection account", 255)

