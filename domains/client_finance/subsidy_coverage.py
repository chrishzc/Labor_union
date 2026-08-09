"""Pure subsidy-entitlement facts used by Client Finance and Payroll."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


_ZERO = Decimal("0")
_SUBSIDY_HOUR_CAPS = {
    "一般市民": Decimal("40"),
    "補助市民": Decimal("120"),
    "非市民": _ZERO,
}
_SUBSIDY_CLAIM_HOURLY_RATES = {
    "一般市民": Decimal("300"),
    "補助市民": Decimal("350"),
    "非市民": _ZERO,
}
_POLICY_IDENTITY_BY_SOURCE_IDENTITY = {
    "低收入戶": "補助市民",
    "中低收入戶": "補助市民",
}


@dataclass(frozen=True, slots=True)
class SubsidyCoverage:
    """Coverage result; eligibility never itself states a client amount."""

    identity_status: str
    total_service_hours: Decimal
    subsidy_hours: Decimal
    self_pay_service_hours: Decimal
    client_floor_fee: Decimal
    subsidy_claim_hourly_rate: Decimal

    @property
    def is_full_subsidy_order(self) -> bool:
        return (
            self.identity_status == "補助市民"
            and self.self_pay_service_hours == _ZERO
            and self.client_floor_fee == _ZERO
        )


def derive_subsidy_coverage(
    identity_status: str,
    total_service_hours: Decimal,
    client_floor_fee: Decimal,
) -> SubsidyCoverage:
    """Derive capped subsidy hours and the self-pay portion of a service case."""
    policy_identity_status = normalize_subsidy_policy_identity(identity_status)
    if policy_identity_status not in _SUBSIDY_HOUR_CAPS:
        raise ValueError("unsupported identity_status")
    if total_service_hours < _ZERO:
        raise ValueError("total_service_hours cannot be negative")
    if client_floor_fee < _ZERO:
        raise ValueError("client_floor_fee cannot be negative")
    subsidy_hours = min(
        _SUBSIDY_HOUR_CAPS[policy_identity_status],
        total_service_hours,
    )
    return SubsidyCoverage(
        policy_identity_status,
        total_service_hours,
        subsidy_hours,
        total_service_hours - subsidy_hours,
        client_floor_fee,
        _SUBSIDY_CLAIM_HOURLY_RATES[policy_identity_status],
    )


def normalize_subsidy_policy_identity(identity_status: str) -> str:
    """Map recorded low-income identities to their approved subsidy policy."""
    return _POLICY_IDENTITY_BY_SOURCE_IDENTITY.get(identity_status, identity_status)


__all__ = [
    "SubsidyCoverage",
    "derive_subsidy_coverage",
    "normalize_subsidy_policy_identity",
]
