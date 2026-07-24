"""
================================================================================
檔案名稱: ui/pages/order/tab3_finance.py
功能說明: Tab 3 訂單帳務總覽 (OrderUI_Tab3_Finance)
================================================================================
"""

import os
import requests
import streamlit as st
import pandas as pd
from datetime import date, datetime
from ui.pages.order.shared import (
    safe_float,
    safe_int,
    _derive_staff_payment_date,
    _derive_subsidy_refund_date,
    _payment_api_request,
)


def _to_arrow_scalar(value):
    """Convert display values unsupported by Arrow to nullable scalars."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    return value


def _normalize_arrow_compatible_df(dataframe):
    """Return a display DataFrame whose date values Streamlit can serialize."""
    if dataframe.empty:
        return dataframe
    return dataframe.apply(lambda column: column.map(_to_arrow_scalar))


def _render_tab3_finance(orders_data):
    """Render separate client and staff payment overviews with on-demand detail."""
    st.subheader("帳務明細總覽")
    st.caption("客戶收款與月嫂應付分開顯示；展開案件後才讀取交易明細。")
    try:
        client_payments = _payment_api_request("/client-payments") or []
        staff_payments = _payment_api_request("/staff-payments") or []
    except requests.RequestException as err:
        st.error(f"讀取帳務總覽失敗：{err}")
        return

    order_status_by_case = {
        str(order.get("case_no")): order.get("order_status") or order.get("status") or "—"
        for order in orders_data
        if order.get("case_no")
    }
    order_by_case = {str(order.get("case_no")): order for order in orders_data if order.get("case_no")}
    order_payment_dates_by_case = {
        str(order.get("case_no")): {
            "deposit_due_date": order.get("deposit_date"),
            "first_payment_due_date": order.get("first_payment_date"),
            "second_payment_due_date": order.get("second_payment_date"),
        }
        for order in orders_data
        if order.get("case_no")
    }
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        case_keyword = st.text_input("案件編號", key="payment_overview_case_filter").strip()
    with filter_col2:
        status_options = sorted(set(order_status_by_case.values()) - {"—"})
        selected_order_statuses = st.multiselect(
            "訂單狀態", status_options, key="payment_overview_order_status"
        )

    def matches_order_filter(case_no):
        status = order_status_by_case.get(str(case_no), "—")
        return (
            (not case_keyword or case_keyword.lower() in str(case_no).lower())
            and (not selected_order_statuses or status in selected_order_statuses)
        )

    client_rows = []
    for payment in client_payments:
        case_no = str(payment.get("case_no") or "")
        if not case_no or not matches_order_filter(case_no):
            continue
        receivable = sum(safe_float(payment.get(f"{stage}_receivable")) for stage in ("deposit", "first_payment", "second_payment"))
        received = sum(safe_float(payment.get(f"{stage}_received")) for stage in ("deposit", "first_payment", "second_payment"))
        payment_dates = order_payment_dates_by_case.get(case_no, {})
        deposit_due_date = payment.get("deposit_due_date") or payment_dates.get("deposit_due_date")
        first_payment_due_date = payment.get("first_payment_due_date") or payment_dates.get("first_payment_due_date")
        second_payment_due_date = payment.get("second_payment_due_date") or payment_dates.get("second_payment_due_date")
        related_order = order_by_case.get(case_no, {})
        client_rows.append({
            "案件編號": case_no,
            "訂單狀態": order_status_by_case.get(case_no, "—"),
            "訂金應收": safe_float(payment.get("deposit_receivable")),
            "訂金實收": safe_float(payment.get("deposit_received")),
            "訂金應收日": deposit_due_date,
            "訂金實收日": payment.get("deposit_received_at"),
            "第一期應收": safe_float(payment.get("first_payment_receivable")),
            "第一期實收": safe_float(payment.get("first_payment_received")),
            "第一期應收日": first_payment_due_date,
            "第一期實收日": payment.get("first_payment_received_at"),
            "第二期應收": safe_float(payment.get("second_payment_receivable")),
            "第二期實收": safe_float(payment.get("second_payment_received")),
            "第二期應收日": second_payment_due_date,
            "第二期實收日": payment.get("second_payment_received_at"),
            "服務人員付款日（衍生公式）": _derive_staff_payment_date(related_order),
            "補助退款日（衍生公式）": _derive_subsidy_refund_date(related_order),
            "應收總額": receivable,
            "實收總額": received,
            "未收餘額": receivable - received,
            "付款狀態": "已收清" if received >= receivable else "待收款",
        })

    staff_rows = []
    for payment in staff_payments:
        case_no = str(payment.get("case_no") or "")
        if not case_no or not matches_order_filter(case_no):
            continue
        payable = safe_float(payment.get("total_payable"))
        paid = safe_float(payment.get("amount_paid"))
        staff_rows.append({
            "案件編號": case_no,
            "訂單狀態": order_status_by_case.get(case_no, "—"),
            "服務人員": payment.get("staff_id"),
            "指派序號": payment.get("assignment_id"),
            "服務時數": safe_float(payment.get("service_hours")),
            "服務單價": safe_float(payment.get("hourly_rate")),
            "服務薪資": safe_float(payment.get("service_salary")),
            "樓層費": safe_float(payment.get("floor_fee_amount")),
            "調整額": safe_float(payment.get("adjustment_amount")),
            "應付金額": payable,
            "實付金額": paid,
            "未付餘額": payable - paid,
            "應付日期": payment.get("due_date"),
            "實付日期": payment.get("paid_at"),
            "付款狀態": payment.get("payment_status"),
        })

    client_tab, staff_tab = st.tabs(["客戶收款總覽", "月嫂應付總覽"])
    with client_tab:
        client_df = pd.DataFrame(client_rows)
        client_df = _normalize_arrow_compatible_df(client_df)
        client_states = sorted(client_df["付款狀態"].dropna().unique()) if not client_df.empty else []
        selected_client_states = st.multiselect("客戶付款狀態", client_states, key="client_payment_state_filter")
        if selected_client_states:
            client_df = client_df[client_df["付款狀態"].isin(selected_client_states)]
        st.caption(f"共 {len(client_df)} 筆客戶帳務")
        st.dataframe(client_df, width="stretch", hide_index=True)
    with staff_tab:
        staff_df = pd.DataFrame(staff_rows)
        staff_df = _normalize_arrow_compatible_df(staff_df)
        staff_states = sorted(staff_df["付款狀態"].dropna().unique()) if not staff_df.empty else []
        selected_staff_states = st.multiselect("月嫂付款狀態", staff_states, key="staff_payment_state_filter")
        if selected_staff_states:
            staff_df = staff_df[staff_df["付款狀態"].isin(selected_staff_states)]
        st.caption(f"共 {len(staff_df)} 筆月嫂帳務")
        st.dataframe(staff_df, width="stretch", hide_index=True)

    detail_cases = sorted(set(client_df.get("案件編號", [])) | set(staff_df.get("案件編號", [])))
    if not detail_cases:
        return
    selected_case_no = st.selectbox("選擇案件查看交易明細", detail_cases, key="payment_overview_selected_case")
    with st.expander(f"案件 {selected_case_no} 客戶／月嫂交易明細", expanded=False):
        if selected_case_no:
            try:
                try:
                    client_detail = _payment_api_request(f"/client-payments/{selected_case_no}")
                except requests.HTTPError as err:
                    if err.response is None or err.response.status_code != 404:
                        raise
                    client_detail = None
                staff_detail = _payment_api_request(f"/staff-payments/{selected_case_no}") or []
            except requests.RequestException as err:
                st.error(f"讀取案件明細失敗：{err}")
                return
            st.session_state[f"payment_detail_{selected_case_no}"] = (client_detail, staff_detail)

        detail = st.session_state.get(f"payment_detail_{selected_case_no}")
        if not detail:
            st.info("按下「載入／重新整理交易明細」後才會讀取交易紀錄。")
            return
        client_detail, staff_detail = detail
        detail_client_tab, detail_staff_tab = st.tabs(["客戶帳務與交易", "月嫂帳務與交易"])
    with detail_client_tab:
        _render_client_payment_ledger(selected_case_no, client_detail)
    with detail_staff_tab:
        _render_staff_payment_ledger(selected_case_no, staff_detail)


def _render_legacy_mixed_payment_overview(orders_data):
    """相容 shim：委派至 _render_tab3_finance"""
    return _render_tab3_finance(orders_data)


def _render_client_payment_ledger(case_no, payment):
    if not payment:
        st.info("此案件尚未建立客戶帳務摘要。")
        return

    stages = [
        ("訂金", "deposit"),
        ("第一期", "first_payment"),
        ("第二期", "second_payment"),
    ]
    rows = []
    total_receivable = total_received = 0.0
    for label, key in stages:
        receivable = safe_float(payment.get(f"{key}_receivable"))
        received = safe_float(payment.get(f"{key}_received"))
        total_receivable += receivable
        total_received += received
        rows.append({
            "階段": label,
            "應收金額": receivable,
            "實收金額": received,
            "應收日期": payment.get(f"{key}_due_date"),
            "實收日期": payment.get(f"{key}_received_at"),
        })
    rows.append({"階段": "合計", "應收金額": total_receivable, "實收金額": total_received, "應收日期": None, "實收日期": None})
    client_rows_df = pd.DataFrame(rows)
    client_rows_df = _normalize_arrow_compatible_df(client_rows_df)
    st.dataframe(client_rows_df, width="stretch", hide_index=True)

    subsidy_return = safe_float(payment.get("subsidy_return_receivable"))
    if subsidy_return:
        st.markdown("#### 退還補助款")
        subsidy_df = pd.DataFrame([{
            "應退金額": subsidy_return,
            "已退金額": safe_float(payment.get("subsidy_return_refunded")),
            "應退日期": payment.get("subsidy_return_due_date"),
            "退還日期": payment.get("subsidy_return_at"),
        }])
        subsidy_df = _normalize_arrow_compatible_df(subsidy_df)
        st.dataframe(subsidy_df, width="stretch", hide_index=True)

    transactions = payment.get("transactions") or []
    with st.expander("客戶交易明細", expanded=False):
        if transactions:
            st.dataframe(pd.DataFrame(transactions), width="stretch", hide_index=True)
        else:
            st.info("尚無交易明細。")
        with st.form(f"client_payment_transaction_{case_no}"):
            st.markdown("補登／沖正交易")
            stage = st.selectbox("階段", ["deposit", "first_payment", "second_payment"], format_func={"deposit": "訂金", "first_payment": "第一期", "second_payment": "第二期"}.get)
            transaction_type = st.selectbox("交易類型", ["receipt", "reversal"], format_func={"receipt": "收款", "reversal": "沖正"}.get)
            amount = st.number_input("金額", min_value=0.01, step=1.0)
            occurred_at = st.date_input("交易日期", value=datetime.today().date())
            external_reference = st.text_input("銀行流水號／外部識別", key=f"client_reference_{case_no}")
            notes = st.text_area("調整原因（必填）", key=f"client_reason_{case_no}")
            submitted = st.form_submit_button("新增客戶交易")
        if submitted:
            if not external_reference.strip() or not notes.strip():
                st.error("請填寫銀行流水號／外部識別與調整原因。")
            else:
                try:
                    _payment_api_request("/client-payments/transaction", "POST", {"case_no": case_no, "stage": stage, "transaction_type": transaction_type, "amount": amount, "occurred_at": occurred_at.isoformat(), "external_reference": external_reference.strip(), "notes": notes.strip()})
                except requests.RequestException as err:
                    st.error(f"新增客戶交易失敗：{err}")
                else:
                    st.success("已新增交易，帳務摘要已由交易明細重新計算。")
                    st.rerun()


def _render_staff_payment_ledger(case_no, payments):
    if not payments:
        st.info("此案件尚無服務人員應付帳務。")
        return

    rows = []
    for payment in payments:
        payable = safe_float(payment.get("total_payable"))
        paid = safe_float(payment.get("amount_paid"))
        rows.append({
            "服務人員（ID）": payment.get("staff_id"), "指派序號": payment.get("assignment_id"),
            "服務時數": safe_float(payment.get("service_hours")), "單價": safe_float(payment.get("hourly_rate")),
            "服務薪資": safe_float(payment.get("service_salary")), "樓層費": safe_float(payment.get("floor_fee_amount")),
            "調整額": safe_float(payment.get("adjustment_amount")), "應付金額": payable,
            "實付金額": paid, "未付餘額": payable - paid, "應付日期": payment.get("due_date"),
            "實付日期": payment.get("paid_at"), "狀態": payment.get("payment_status"),
        })
    staff_rows_df = pd.DataFrame(rows)
    staff_rows_df = _normalize_arrow_compatible_df(staff_rows_df)
    st.dataframe(staff_rows_df, width="stretch", hide_index=True)

    for payment in payments:
        payment_id = payment.get("id")
        staff_id = payment.get("staff_id")
        with st.expander(f"服務人員 {staff_id}／指派 {payment.get('assignment_id')} 的交易明細", expanded=False):
            transactions = payment.get("transactions") or []
            if transactions:
                st.dataframe(pd.DataFrame(transactions), width="stretch", hide_index=True)
            else:
                st.info("尚無交易明細。")
            with st.form(f"staff_payment_transaction_{payment_id}"):
                st.markdown("補登／沖正交易")
                transaction_type = st.selectbox("交易類型", ["transfer", "reversal"], format_func={"transfer": "付款", "reversal": "沖正"}.get, key=f"staff_transaction_type_{payment_id}")
                amount = st.number_input("金額", min_value=0.01, step=1.0, key=f"staff_amount_{payment_id}")
                occurred_at = st.date_input("交易日期", value=datetime.today().date(), key=f"staff_date_{payment_id}")
                external_reference = st.text_input("銀行流水號／外部識別", key=f"staff_reference_{payment_id}")
                notes = st.text_area("調整原因（必填）", key=f"staff_reason_{payment_id}")
                submitted = st.form_submit_button("新增服務人員交易")
            if submitted:
                if not external_reference.strip() or not notes.strip():
                    st.error("請填寫銀行流水號／外部識別與調整原因。")
                else:
                    try:
                        _payment_api_request("/staff-payments/transaction", "POST", {"staff_payment_id": payment_id, "transaction_type": transaction_type, "amount": amount, "occurred_at": occurred_at.isoformat(), "external_reference": external_reference.strip(), "notes": notes.strip()})
                    except requests.RequestException as err:
                        st.error(f"新增服務人員交易失敗：{err}")
                    else:
                        st.success("已新增交易，帳務摘要已由交易明細重新計算。")
                        st.rerun()
