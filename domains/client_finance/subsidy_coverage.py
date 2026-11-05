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
    "社福": "補助市民",
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


def is_full_subsidy_case(identity_status: str | None, service_hours: Decimal | None,
                         subsidy_limit: Decimal | None) -> bool | None:
    """FULL-01: use the case's effective limit, never a fixed identity threshold."""
    if identity_status is None:
        return None
    if normalize_subsidy_policy_identity(identity_status) not in {"補助市民", "原住民"}:
        return False
    if service_hours is None or subsidy_limit is None:
        return None
    hours, limit = Decimal(str(service_hours)), Decimal(str(subsidy_limit))
    if not hours.is_finite() or not limit.is_finite() or hours < 0 or limit < 0:
        raise ValueError("full_subsidy_hours_invalid")
    return 0 < hours <= limit


__all__ = [
    "SubsidyCoverage",
    "derive_subsidy_coverage",
    "normalize_subsidy_policy_identity",
    "is_full_subsidy_case",
]
