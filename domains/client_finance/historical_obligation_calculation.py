"""Client Finance amounts derived from historical service-day counts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from domains.client_finance.order_amount_calculation import (
    SUBSIDIZED_EXCESS_CLIENT_HOURLY_RATE,
)
from domains.client_finance.subsidy_coverage import (
    derive_subsidy_coverage,
    normalize_subsidy_policy_identity,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_positive_integer


@dataclass(frozen=True, slots=True)
class HistoricalClientObligationCandidate:
    identity_status: str
    client_policy_version: str
    client_hourly_rate: MoneyNTD
    actual_service_days: int
    actual_service_hours: int
    historical_floor_fee: MoneyNTD
    service_receivable: MoneyNTD
    total_receivable: MoneyNTD
    subsidy_hours: int
    self_pay_service_hours: int
    fingerprint: PreviewFingerprint


def build_historical_client_obligation_candidate(
    *,
    identity_status: str,
    client_policy_version: str,
    client_hourly_rate: MoneyNTD,
    actual_service_days: int,
    service_hours_per_day: int,
    historical_floor_fee: MoneyNTD,
) -> HistoricalClientObligationCandidate:
    """Calculate the historical client obligation without payment-stage dates."""

    require_positive_integer(actual_service_days, "actual service days")
    require_positive_integer(service_hours_per_day, "service hours per day")
    if not str(client_policy_version).strip():
        raise ValueError("client payment policy version is required")
    if not isinstance(client_hourly_rate, MoneyNTD):
        raise TypeError("client hourly rate must be MoneyNTD")
    if client_hourly_rate.amount <= 0:
        raise ValueError("client hourly rate must be positive")
    if not isinstance(historical_floor_fee, MoneyNTD):
        raise TypeError("historical floor fee must be MoneyNTD")
    policy_identity = normalize_subsidy_policy_identity(identity_status)
    total_hours = actual_service_days * service_hours_per_day
    coverage = derive_subsidy_coverage(
        identity_status,
        Decimal(total_hours),
        Decimal(historical_floor_fee.amount),
    )
    if policy_identity == "補助市民":
        service_receivable = MoneyNTD(
            int(coverage.self_pay_service_hours)
            * int(SUBSIDIZED_EXCESS_CLIENT_HOURLY_RATE)
        )
    else:
        service_receivable = MoneyNTD(total_hours * client_hourly_rate.amount)
    total_receivable = service_receivable + historical_floor_fee
    payload = {
        "basis": "historical_actual_service_day_count",
        "identity_status": identity_status,
        "policy_identity_status": policy_identity,
        "client_policy_version": client_policy_version,
        "client_hourly_rate_ntd": client_hourly_rate.amount,
        "actual_service_days": actual_service_days,
        "actual_service_hours": total_hours,
        "historical_floor_fee_ntd": historical_floor_fee.amount,
        "subsidy_hours": int(coverage.subsidy_hours),
        "self_pay_service_hours": int(coverage.self_pay_service_hours),
        "service_receivable_ntd": service_receivable.amount,
        "total_receivable_ntd": total_receivable.amount,
    }
    return HistoricalClientObligationCandidate(
        identity_status=identity_status,
        client_policy_version=client_policy_version,
        client_hourly_rate=client_hourly_rate,
        actual_service_days=actual_service_days,
        actual_service_hours=total_hours,
        historical_floor_fee=historical_floor_fee,
        service_receivable=service_receivable,
        total_receivable=total_receivable,
        subsidy_hours=int(coverage.subsidy_hours),
        self_pay_service_hours=int(coverage.self_pay_service_hours),
        fingerprint=fingerprint_payload(payload),
    )


__all__ = [
    "HistoricalClientObligationCandidate",
    "build_historical_client_obligation_candidate",
]
