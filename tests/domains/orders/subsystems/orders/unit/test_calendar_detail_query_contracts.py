"""Direct contracts for the bounded Orders calendar-detail query service."""

import pytest

from subsystems.orders.calendar_detail_query import (
    OrderCalendarDetailContractError,
    OrderCalendarDetailNotFoundError,
    OrderCalendarDetailQueryService,
)


class _Repository:
    def __init__(self, row):
        self.row = row
        self.requested_case_no = None

    def fetch_by_case_no(self, case_no: str):
        self.requested_case_no = case_no
        return self.row


@pytest.mark.parametrize("service_mode", ["週休2日", "週休1日", "連續服務"])
def test_query_accepts_only_supported_bounded_projection(service_mode: str) -> None:
    repository = _Repository({"case_no": "CASE-100", "service_mode": service_mode})

    detail = OrderCalendarDetailQueryService(repository).query("CASE-100")

    assert repository.requested_case_no == "CASE-100"
    assert detail.case_no == "CASE-100"
    assert detail.service_mode == service_mode


def test_query_rejects_noncanonical_case_identity_before_repository_access() -> None:
    repository = _Repository({"case_no": "CASE-100", "service_mode": "週休1日"})

    for invalid in ("", " CASE-100 ", "X" * 51, None):
        with pytest.raises(ValueError):
            OrderCalendarDetailQueryService(repository).query(invalid)

    assert repository.requested_case_no is None


def test_query_distinguishes_not_found_from_projection_contract_drift() -> None:
    with pytest.raises(OrderCalendarDetailNotFoundError):
        OrderCalendarDetailQueryService(_Repository(None)).query("CASE-404")

    bad_rows = (
        {"case_no": "CASE-100"},
        {"case_no": "CASE-100", "service_mode": "週休1日", "extra": True},
        {"case_no": "CASE-OTHER", "service_mode": "週休1日"},
        {"case_no": "CASE-100", "service_mode": "unsupported"},
    )
    for row in bad_rows:
        with pytest.raises(OrderCalendarDetailContractError):
            OrderCalendarDetailQueryService(_Repository(row)).query("CASE-100")
