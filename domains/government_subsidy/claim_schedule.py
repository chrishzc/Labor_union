"""Pure Government Subsidy quarter and application-month projection."""

from __future__ import annotations

from datetime import date


def project_claim_schedule(service_end: date | None) -> tuple[int, int, int] | None:
    if service_end is None:
        return None
    quarter = (service_end.month - 1) // 3 + 1
    application_month = quarter * 3 + 1
    application_year = service_end.year
    if application_month == 13:
        application_month = 1
        application_year += 1
    return quarter, application_year, application_month


__all__ = ["project_claim_schedule"]
