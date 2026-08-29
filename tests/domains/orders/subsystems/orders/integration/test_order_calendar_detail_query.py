from types import SimpleNamespace

import pytest

from subsystems.orders.calendar_detail_query import (
    OrderCalendarDetailContractError,
    OrderCalendarDetailNotFoundError,
    OrderCalendarDetailQueryService,
)


def _service(row):
    return OrderCalendarDetailQueryService(
        SimpleNamespace(fetch_by_case_no=lambda _case_no: row)
    )


def test_query_returns_validated_calendar_detail() -> None:
    detail = _service({"case_no": "CASE-1", "service_mode": "週休2日"}).query("CASE-1")

    assert detail.case_no == "CASE-1"
    assert detail.service_mode == "週休2日"


@pytest.mark.parametrize("case_no", ["", " CASE-1", "CASE-1 ", "x" * 51])
def test_query_rejects_noncanonical_case_number(case_no: str) -> None:
    with pytest.raises(ValueError):
        _service(None).query(case_no)


def test_query_rejects_projection_identity_drift() -> None:
    with pytest.raises(OrderCalendarDetailContractError, match="case identity drift"):
        _service({"case_no": "CASE-2", "service_mode": "週休2日"}).query("CASE-1")


def test_query_rejects_unexpected_service_mode() -> None:
    with pytest.raises(OrderCalendarDetailContractError, match="unsupported service mode"):
        _service({"case_no": "CASE-1", "service_mode": "unknown"}).query("CASE-1")


def test_query_maps_missing_projection_to_not_found() -> None:
    with pytest.raises(OrderCalendarDetailNotFoundError):
        _service(None).query("CASE-1")
