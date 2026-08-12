"""Acceptance coverage for the isolated Page 2 payment-management UI."""

from __future__ import annotations

import ast
from pathlib import Path


SHARED_MODULE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "order" / "shared.py"
TAB3_MODULE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "order" / "tab3_finance.py"
TAB4_MODULE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "order" / "tab4_accounts_payable.py"
TAB5_MODULE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "order" / "tab5_subsidy_reconciliation.py"
ORDERS_PAGE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "02_orders.py"


def _function_source(name: str) -> str:
    for filepath in (SHARED_MODULE, TAB3_MODULE, TAB4_MODULE, TAB5_MODULE, ORDERS_PAGE):
        if not filepath.exists():
            continue
        text = filepath.read_text(encoding="utf-8")
        tree = ast.parse(text)
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if name in functions:
            source = ast.get_source_segment(text, functions[name])
            assert source is not None
            return source
    raise AssertionError(f"missing payment UI source function: {name}")


def test_payment_ui_uses_a_single_fastapi_gateway():
    gateway = _function_source("_payment_api_request")

    assert "requests.request(" in gateway
    assert 'f"{base_url}/api/v1{path}"' in gateway
    assert "response.raise_for_status()" in gateway
    assert 'response.json().get("data")' in gateway


def test_client_receipt_form_is_traceable_and_cannot_write_staff_payments():
    client_ledger = _function_source("_render_client_payment_ledger")
    tab3_finance = _function_source("_render_tab3_finance")

    assert 'st.form(f"client_payment_transaction_{case_no}")' in client_ledger
    assert '"/client-payments/transaction"' in client_ledger
    for field in (
        '"case_no": case_no',
        '"stage": stage',
        '"transaction_type": transaction_type',
        '"transaction_status": "succeeded"',
        '"amount": amount',
        '"occurred_at": occurred_at.isoformat()',
        '"external_reference": external_reference.strip()',
        '"notes": notes.strip()',
    ):
        assert field in client_ledger
    assert "if not external_reference.strip() or not notes.strip():" in client_ledger
    assert 'transaction.get("stage") == stage' in client_ledger
    assert 'transaction.get("transaction_type") == "receipt"' in client_ledger
    assert 'transaction.get("transaction_status") == "succeeded"' in client_ledger
    assert '"reversal_of_transaction_id"' in client_ledger
    assert 'payload["reversal_of_transaction_id"]' in client_ledger
    assert 'payload["lifecycle_expected_version"] = lifecycle_version' in client_ledger
    assert "訂單版本資料缺失，請重新整理頁面" in client_ledger
    assert "err.response.status_code in {400, 409}" in client_ledger
    assert (
        "lifecycle_version=order_by_case.get(selected_case_no, {}).get("
        in tab3_finance
    )
    assert "/staff-payments/" not in client_ledger
    assert "staff_payment_id" not in client_ledger


def test_staff_transfer_form_is_traceable_and_cannot_write_client_payments():
    staff_ledger = _function_source("_render_staff_payment_ledger")

    assert 'st.form(f"staff_payment_transaction_{payment_id}")' in staff_ledger
    assert '"/staff-payments/transaction"' in staff_ledger
    for field in (
        '"staff_payment_id": payment_id',
        '"transaction_type": transaction_type',
        '"amount": amount',
        '"occurred_at": occurred_at.isoformat()',
        '"external_reference": external_reference.strip()',
        '"notes": notes.strip()',
    ):
        assert field in staff_ledger
    assert "if not external_reference.strip() or not notes.strip():" in staff_ledger
    assert "/client-payments/" not in staff_ledger
    assert '"case_no": case_no' not in staff_ledger


def test_legacy_tab3_is_not_mounted_and_typed_finance_tabs_are_separate():
    tab3 = _function_source("_render_tab3_finance")
    tab4 = _function_source("_render_tab4_accounts_payable")
    tab5 = _function_source("_render_tab5_subsidy_reconciliation")
    page_shell = _function_source("_render_order_page_shell")
    accounts_workspace = _function_source("_render_accounts_payable_workspace")
    subsidy_workspace = _function_source(
        "_render_subsidy_reconciliation_workspace"
    )

    assert 'st.tabs(["客戶收款總覽", "月嫂應付總覽"])' in tab3
    assert "_render_client_payment_ledger(" in tab3
    assert "selected_case_no,\n            client_detail," in tab3
    assert 'order_by_case.get(selected_case_no, {}).get(\n                "lifecycle_version"' in tab3
    assert "_render_staff_payment_ledger(selected_case_no, staff_detail)" in tab3
    assert "_render_tab3_finance" not in page_shell
    assert "_render_client_receipt_tab(orders_data)" in page_shell
    assert "_render_payroll_adjustment_tab(orders_data, staff_list)" in page_shell
    assert '"載入應付帳款查詢／輸出"' in accounts_workspace
    assert "_render_tab4_accounts_payable()" in accounts_workspace
    assert '"載入核銷補助清冊"' in subsidy_workspace
    assert "_render_tab5_subsidy_reconciliation()" in subsidy_workspace

    assert '"POST"' not in tab4
    assert "_payment_api_request(" not in tab4
    assert "AccountsPayableExportApiClient()" in tab4
    assert '"POST"' not in tab5
    assert "_payment_api_request(" not in tab5
    assert "_finance_report_request(" in tab5
