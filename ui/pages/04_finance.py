"""帳務作業中心的薄 UI 入口。"""

from datetime import date

import streamlit as st

from ui.pages.shared import build_admin_headers, resolve_api_base_url


title = "💰 帳務作業中心"
FINANCE_WORKSPACES = (
    "銀行流水匯入",
    "應付帳款查詢／輸出",
    "補助核銷清冊",
    "客戶收款核銷",
    "月嫂薪資調整",
    "月嫂付款核銷",
)


def show() -> None:
    st.title(title)
    st.caption("建立或查詢帳務明細；會計匯款仍以產生的應付明細及後續銀行流水為準。")
    workspace = st.radio(
        "帳務作業",
        FINANCE_WORKSPACES,
        horizontal=True,
        label_visibility="collapsed",
        key="finance_workspace",
    )
    _render_workspace(workspace)


def _render_workspace(workspace: str) -> None:
    if workspace == "銀行流水匯入":
        _render_finance_import_workspace()
        return
    if workspace == "應付帳款查詢／輸出":
        _render_accounts_payable_workspace()
        return
    if workspace == "補助核銷清冊":
        _render_subsidy_reconciliation_workspace()
        return
    if workspace == "客戶收款核銷":
        _render_client_receipt_workspace()
        return
    if workspace == "月嫂薪資調整":
        _render_payroll_adjustment_workspace()
        return
    _render_staff_payout_workspace()


def _render_finance_import_workspace() -> None:
    try:
        from ui.api_clients.finance_import_api_client import FinanceImportApiClient
        from ui.pages.finance_import.panel import render_finance_import_panel

        render_finance_import_panel(
            FinanceImportApiClient(
                base_url=resolve_api_base_url(),
                headers=build_admin_headers(),
            )
        )
    except Exception as error:
        st.error(f"銀行流水工作區載入失敗：{error}")


def _render_accounts_payable_workspace() -> None:
    from ui.pages.order.tab4_accounts_payable import _render_tab4_accounts_payable

    _render_tab4_accounts_payable()


def _render_subsidy_reconciliation_workspace() -> None:
    from ui.pages.order.tab5_subsidy_reconciliation import _render_tab5_subsidy_reconciliation

    reconciliation_tab, claim_tab = st.tabs(("核銷清冊查詢", "政府補助申請批次"))
    with reconciliation_tab:
        _render_tab5_subsidy_reconciliation()
    with claim_tab:
        _render_government_subsidy_claim_workspace()


def _render_government_subsidy_claim_workspace() -> None:
    try:
        from ui.api_clients.government_subsidy_api_client import GovernmentSubsidyApiClient
        from ui.pages.government_subsidy.claim_panel import render_government_subsidy_claim_panel

        render_government_subsidy_claim_panel(
            GovernmentSubsidyApiClient(
                base_url=resolve_api_base_url(),
                headers=build_admin_headers(),
            )
        )
    except Exception as error:
        _render_workspace_error(error)


def _render_client_receipt_workspace() -> None:
    case_no = _select_case_number("client_receipt_case")
    if case_no is None:
        return
    try:
        from ui.api_clients.client_receipt_reconciliation_api_client import ClientReceiptReconciliationApiClient
        from ui.pages.order.client_receipt_reconciliation_panel import render_client_receipt_reconciliation_panel

        render_client_receipt_reconciliation_panel(
            case_no,
            ClientReceiptReconciliationApiClient(
                base_url=resolve_api_base_url(),
                headers=build_admin_headers(),
            ),
        )
    except Exception as error:
        _render_workspace_error(error)


def _render_payroll_adjustment_workspace() -> None:
    case_no = _select_case_number("payroll_adjustment_case")
    if case_no is None:
        return
    try:
        from ui.api_clients.payroll_api_client import PayrollApiClient
        from ui.api_clients.payroll_rebuild_api_client import PayrollRebuildApiClient
        from ui.pages.payroll.adjustment_panel import render_payroll_adjustment_panel
        from ui.pages.payroll.rebuild_panel import render_payroll_rebuild_panel

        base_url = resolve_api_base_url()
        headers = build_admin_headers()
        rebuild_client = PayrollRebuildApiClient(base_url=base_url, headers=headers)
        render_payroll_rebuild_panel(case_no, rebuild_client)
        st.divider()
        render_payroll_adjustment_panel(case_no, PayrollApiClient(base_url=base_url, headers=headers))
        st.divider()
        _render_staff_monthly_summary(_load_staff_summaries(), rebuild_client)
    except Exception as error:
        _render_workspace_error(error)


def _render_staff_payout_workspace() -> None:
    staff_options = _staff_options(_load_staff_summaries())
    if not staff_options:
        st.info("目前沒有可選擇的月嫂。")
        return
    try:
        from ui.api_clients.staff_payout_api_client import StaffPayoutApiClient
        from ui.pages.staff_payables.staff_payout_panel import render_staff_payout_panel

        _apply_pending_staff_payout_selection(staff_options)
        selected_label = st.selectbox("選擇月嫂", tuple(staff_options), key="staff_payout_staff_selector")
        render_staff_payout_panel(
            staff_options[selected_label],
            StaffPayoutApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers()),
        )
    except Exception as error:
        _render_workspace_error(error)


def _select_case_number(widget_key: str) -> str | None:
    case_numbers = tuple(
        sorted({str(order.case_no).strip() for order in _load_order_summaries() if str(order.case_no).strip()})
    )
    if not case_numbers:
        st.info("目前沒有可選擇的訂單。")
        return None
    return st.selectbox("選擇案件", case_numbers, key=widget_key)


def _load_order_summaries():
    from ui.api_clients.order_summary_api_client import OrderSummaryApiClient

    result = OrderSummaryApiClient(
        base_url=resolve_api_base_url(),
        headers=build_admin_headers(),
    ).query(page_size=200)
    if result.page is None:
        return ()
    return result.page.items


def _load_staff_summaries():
    from ui.api_clients.staff_summary_api_client import StaffSummaryApiClient

    return StaffSummaryApiClient(
        base_url=resolve_api_base_url(),
        headers=build_admin_headers(),
    ).query(page_size=200).items


def _staff_options(staff_list) -> dict[str, int]:
    return {
        f"{staff.name or '未命名月嫂'}（#{staff.id}）": staff.id
        for staff in staff_list
        if isinstance(staff.id, int) and not isinstance(staff.id, bool)
    }


def _apply_pending_staff_payout_selection(staff_options: dict[str, int]) -> None:
    pending_staff_id = st.session_state.pop("pending_staff_payout_staff_id", None)
    selected_label = next((label for label, staff_id in staff_options.items() if staff_id == pending_staff_id), None)
    if selected_label is not None:
        st.session_state["staff_payout_staff_selector"] = selected_label


def _render_staff_monthly_summary(staff_list, client) -> None:
    from ui.pages.payroll.rebuild_panel import render_staff_monthly_payroll_panel

    staff_options = _staff_options(staff_list)
    if not staff_options:
        return
    selected_label = st.selectbox("月份加總月嫂", tuple(staff_options), key="payroll_monthly_staff")
    current_date = date.today()
    year_column, month_column = st.columns(2)
    year = int(year_column.number_input("年份", min_value=2020, max_value=2100, value=current_date.year))
    month = int(month_column.number_input("月份", min_value=1, max_value=12, value=current_date.month))
    render_staff_monthly_payroll_panel(staff_options[selected_label], year, month, client)


def _render_workspace_error(error: Exception) -> None:
    st.warning(f"帳務工作區載入失敗：{error}")
