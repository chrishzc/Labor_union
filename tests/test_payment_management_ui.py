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

    assert 'st.form(f"client_payment_transaction_{case_no}")' in client_ledger
    assert '"/client-payments/transaction"' in client_ledger
    for field in (
        '"case_no": case_no',
        '"stage": stage',
        '"transaction_type": transaction_type',
        '"amount": amount',
        '"occurred_at": occurred_at.isoformat()',
        '"external_reference": external_reference.strip()',
        '"notes": notes.strip()',
    ):
        assert field in client_ledger
    assert "if not external_reference.strip() or not notes.strip():" in client_ledger
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


def test_frozen_tab3_and_read_only_tab4_tab5_boundaries_remain_separate():
    tab3 = _function_source("_render_tab3_finance")
    tab4 = _function_source("_render_tab4_accounts_payable")
    tab5 = _function_source("_render_tab5_subsidy_reconciliation")
    page_shell = _function_source("_render_order_page_shell")

    assert 'st.tabs(["客戶收款總覽", "月嫂應付總覽"])' in tab3
    assert "_render_client_payment_ledger(selected_case_no, client_detail)" in tab3
    assert "_render_staff_payment_ledger(selected_case_no, staff_detail)" in tab3
    assert 'with tab3:\n        _render_tab3_finance(orders_data)' in page_shell
    assert 'with tab4:\n        _render_tab4_accounts_payable()' in page_shell
    assert 'with tab5:\n        _render_tab5_subsidy_reconciliation()' in page_shell

    for source in (tab4, tab5):
        assert '"POST"' not in source
        assert "_payment_api_request(" not in source
        assert "_finance_report_request(" in source
