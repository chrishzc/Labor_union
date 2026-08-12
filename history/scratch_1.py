"""Runtime acceptance tests for the 5-tab Order UI shell."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


APP_TEST_TIMEOUT_SECONDS = 15


def _run_order_page_with_mock_data(orders_data, clients=None, staff=None):
    clients = clients or []
    staff = staff or []

    def _app():
        import importlib
        import os as _os
        import pathlib
        import streamlit as st_local
        import sys as _sys

        _sys.path.insert(0, str(pathlib.Path(_os.getcwd()).resolve()))
        page = importlib.import_module("ui.pages.02_orders")
        from api.schemas.order_summary import OrderSummaryPageView
        from ui.api_clients.order_summary_api_client import (
            OrderSummaryQueryResult,
        )

        class Response:
            def __init__(self, data):
                self._data = data

            def raise_for_status(self):
                return None

            def json(self):
                return {"success": True, "data": self._data}

        def get(url, **kwargs):
            if url.endswith("/api/v1/staff"):
                return Response(staff)
            raise AssertionError(f"unexpected initial API request: {url}")

        class FakeOrderSummaryClient:
            def __init__(self, **_kwargs):
                pass

            def query(self, **_kwargs):
                items = [_summary_item(order) for order in orders_data]
                summary_page = OrderSummaryPageView(
                    items=items,
                    next_cursor=None,
                    etag="a" * 64,
                )
                return OrderSummaryQueryResult(
                    summary_page,
                    '"fake-etag"',
                    False,
                )

        def _summary_item(order):
            start_date = order.get("start_date") or "2026-07-01"
            return {
                "case_no": str(order.get("case_no")),
                "client_name": str(order.get("client_name") or "未命名"),
                "order_status": str(order.get("order_status") or "洽談中"),
                "staff_name": order.get("staff_name") or None,
                "identity_status": order.get("identity_status") or "未設定",
                "start_date": start_date,
                "end_date": order.get("end_date") or start_date,
                "actual_start_date": order.get("actual_start_date"),
                "actual_end_date": order.get("actual_end_date"),
                "service_days": int(order.get("service_days") or 1),
                "total_employer_self_pay_payable": int(
                    order.get("total_employer_self_pay_payable") or 0
                ),
            }

        page.requests.get = get
        page.OrderSummaryApiClient = FakeOrderSummaryClient
        page._request_list.clear()
        page.show()

    app = AppTest.from_function(_app)
    app.run(timeout=APP_TEST_TIMEOUT_SECONDS)
    return app


def test_order_ui_runtime_no_data_shows_shell_without_exception():
    app = _run_order_page_with_mock_data([])

    assert not app.exception
    rendered = [m.value for m in app.markdown]
    assert (
        "本系統串接了 `v_order_details` 整合計算檢視表，提供訂單生命週期、指派配對以及帳務實收狀態的管理。"
        in rendered
    )


def test_order_ui_runtime_single_case_shows_shell():
    minimal_order = [
        {
            "case_no": "A1",
            "client_name": "Alice",
            "order_status": "洽談中",
            "staff_name": "",
            "start_date": "2026-07-01",
            "actual_start_date": "2026-07-01",
            "service_days": 1,
            "identity_status": "",
            "service_mode": "週休1日",
            "client_id": 101,
            "total_employer_self_pay_payable": 1000,
        }
    ]

    app = _run_order_page_with_mock_data(minimal_order)

    assert not app.exception
    rendered = [m.value for m in app.markdown]
    assert (
        "本系統串接了 `v_order_details` 整合計算檢視表，提供訂單生命週期、指派配對以及帳務實收狀態的管理。"
        in rendered
    )


def test_order_tab_renderers_handle_empty_and_single_record():
    def run_tab1_empty():
        import importlib
        import streamlit as st_local

        tab1 = importlib.import_module("ui.pages.order.tab1_overview")
        tab1._render_tab1_overview([])

    app = AppTest.from_function(run_tab1_empty)
    app.run(timeout=APP_TEST_TIMEOUT_SECONDS)
    assert not app.exception

    def run_tab2_empty():
        import importlib
        import streamlit as st_local

        tab2 = importlib.import_module("ui.pages.order.tab2_assign")
        tab2._render_tab2_assign([], [], [])

    app = AppTest.from_function(run_tab2_empty)
    app.run(timeout=APP_TEST_TIMEOUT_SECONDS)
    assert not app.exception

    def run_tab3():
        import importlib
        import streamlit as st_local

        tab3 = importlib.import_module("ui.pages.order.tab3_finance")

        def _mock_payment_api_request(path, method="GET", payload=None):
            if path in ("/client-payments", "/staff-payments"):
                return []
            return {}

        tab3._payment_api_request = _mock_payment_api_request
        tab3._render_tab3_finance([])

    app = AppTest.from_function(run_tab3)
    app.run(timeout=APP_TEST_TIMEOUT_SECONDS)
    assert not app.exception

    def run_tab4():
        import importlib
        import streamlit as st_local

        tab4 = importlib.import_module("ui.pages.order.tab4_accounts_payable")

        class FakeAccountsPayableClient:
            def query(self, target_month):
                return {
                    "rows": [],
                    "row_count": 0,
                    "total_amount_ntd": 0,
                }

            def query_archive(self, year):
                return {"year": year, "records": []}

        tab4.AccountsPayableExportApiClient = FakeAccountsPayableClient
        tab4._render_tab4_accounts_payable()

    app = AppTest.from_function(run_tab4)
    app.run(timeout=APP_TEST_TIMEOUT_SECONDS)
    assert not app.exception

    def run_tab5():
        import importlib
        import streamlit as st_local

        tab5 = importlib.import_module("ui.pages.order.tab5_subsidy_reconciliation")
        def _mock_finance_report_request(path, params=None, download=False):
            if download:
                return b""
            return {"general_citizen_rows": [], "subsidized_citizen_rows": [], "summary_rows": []}

        tab5._finance_report_request = _mock_finance_report_request
        tab5._render_tab5_subsidy_reconciliation()

    app = AppTest.from_function(run_tab5)
    app.run(timeout=APP_TEST_TIMEOUT_SECONDS)
    assert not app.exception
