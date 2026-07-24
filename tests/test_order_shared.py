"""Tests for ui.pages.order.shared helper signatures and behaviors."""

from datetime import date
from ui.pages.order.shared import (
    safe_float,
    safe_int,
    safe_date,
    _parse_date,
    _month_index,
    _derive_service_end_date,
    _derive_staff_payment_date,
    _derive_subsidy_refund_date,
    _payment_api_request,
    _finance_report_request,
)
import inspect


def test_shared_helper_signatures_and_positional_args():
    sig_pay = inspect.signature(_payment_api_request)
    params_pay = list(sig_pay.parameters.keys())
    assert params_pay[:3] == ["path", "method", "payload"]
    assert sig_pay.parameters["method"].default == "GET"
    assert sig_pay.parameters["payload"].default is None

    sig_fin = inspect.signature(_finance_report_request)
    params_fin = list(sig_fin.parameters.keys())
    assert params_fin[:3] == ["path", "params", "download"]
    assert sig_fin.parameters["params"].default is None
    assert sig_fin.parameters["download"].default is False


def test_derived_date_helpers():
    order_sub = {
        "actual_start_date": "2026-05-01",
        "service_days": 20,
        "identity_status": "補助市民",
    }
    assert _derive_service_end_date(order_sub) == date(2026, 5, 20)
    assert _derive_staff_payment_date(order_sub) == "2026-07-15"
    assert _derive_subsidy_refund_date(order_sub) == "2026-06-05"

    order_non_sub = {
        "actual_start_date": "2026-05-01",
        "service_days": 20,
        "identity_status": "一般市民",
    }
    assert _derive_staff_payment_date(order_non_sub) == "2026-06-15"
    assert _derive_subsidy_refund_date(order_non_sub) == "2026-06-05"
