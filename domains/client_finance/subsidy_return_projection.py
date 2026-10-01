"""Read-only subsidy-return amounts; never creates payable or payment facts."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from domains.client_finance.subsidy_advance import subsidy_advance_due_date
from domains.client_finance.subsidy_coverage import derive_subsidy_coverage, normalize_subsidy_policy_identity


@dataclass(frozen=True, slots=True)
class SubsidyReturnProjection:
    amount_ntd: int | None
    due_date: date | None
    is_estimate: bool


def project_subsidy_return(
    *, identity_status: str, service_hours: Decimal | None,
    floor_fee: Decimal | None, client_hourly_rate_ntd: int | None,
    completed_on: date | None, has_formal_return: bool,
    formal_amount_ntd: int | None, formal_due_date: date | None,
    return_settled: bool,
) -> SubsidyReturnProjection | None:
    """Show eligible cases before posting, using the frozen customer terms rate.

    Posted payables remain authoritative. A terms-based amount is explicitly
    an estimate, including after service completion; it is never a payment
    instruction or evidence that the customer's fees have been collected.
    """
    identity = normalize_subsidy_policy_identity(identity_status)
    if identity not in {'一般市民', '補助市民'} or return_settled:
        return None
    if has_formal_return:
        return SubsidyReturnProjection(formal_amount_ntd, formal_due_date, False)
    due_date = subsidy_advance_due_date(completed_on) if completed_on else None
    if service_hours is None or floor_fee is None:
        return SubsidyReturnProjection(None, due_date, True)
    coverage = derive_subsidy_coverage(identity, service_hours, floor_fee)
    if coverage.is_full_subsidy_order or coverage.subsidy_hours == 0:
        return None
    if client_hourly_rate_ntd is None or client_hourly_rate_ntd <= 0:
        return SubsidyReturnProjection(None, due_date, True)
    amount = coverage.subsidy_hours * client_hourly_rate_ntd
    if amount != amount.to_integral_value():
        raise ValueError('subsidy return must be whole NTD')
    return SubsidyReturnProjection(int(amount), due_date, True)
