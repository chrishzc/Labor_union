"""Thin order editor composed only from typed backend workflows."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import streamlit as st

from api.schemas.orders import ClientNamePreviewView
from ui.api_clients.client_name_api_client import ClientNameApiClient, ClientNameApiError
from ui.pages.shared import build_admin_headers, resolve_api_base_url


def render_editor(
    target_case_no: str,
    orders_data: list[dict[str, Any]],
    payments_raw: list[dict[str, Any]],
    key_prefix: str = "v25",
) -> None:
    """Render basic client editing and authoritative backend workflows."""
    del payments_raw
    target_order = _target_order(target_case_no, orders_data)
    if target_order is None:
        st.warning("找不到此訂單資料，請重新整理頁面。")
        return
    headers = _load_admin_headers()
    if headers is None:
        return
    _render_basic_details(target_case_no, target_order, headers, key_prefix)
    _render_authoritative_workflows(target_case_no, target_order, headers)


def _target_order(case_no, orders_data):
    if not isinstance(orders_data, list):
        raise TypeError("orders_data must be a list")
    return next(
        (order for order in orders_data if order.get("case_no") == case_no),
        None,
    )


def _load_admin_headers():
    try:
        return build_admin_headers()
    except Exception as error:
        st.error(f"未完成管理員授權設定：{error}")
        return None


def _render_basic_details(case_no, order, headers, key_prefix):
    st.markdown(f"### 訂單基本資料 `{case_no}`")
    client_name = st.text_input(
        "客戶名稱",
        value=str(order.get("client_name") or ""),
        key=f"{key_prefix}_client_{case_no}",
    )
    _render_read_only_identity(order, key_prefix, case_no)
    if st.button(
        "儲存訂單基本資料",
        type="primary",
        key=f"{key_prefix}_save_order_details_{case_no}",
    ):
        _save_client_name(case_no, client_name, headers)
    preview = st.session_state.get(f"client_name_preview_{case_no}")
    if isinstance(preview, ClientNamePreviewView):
        st.info(f"預覽：客戶姓名將由「{preview.before_client_name or '未設定'}」改為「{preview.after_client_name}」；正式條款與排班不變。")
        reason = st.text_input("客戶姓名異動原因", key=f"{key_prefix}_client_name_reason_{case_no}")
        if st.button("確認套用客戶姓名", type="primary", key=f"{key_prefix}_apply_client_name_{case_no}"):
            _apply_client_name(case_no, headers, preview, reason)


def _render_read_only_identity(order, key_prefix, case_no):
    columns = st.columns(3)
    fields = (
        ("身分資格（唯讀）", order.get("identity_status") or "未設定", "identity"),
        ("服務人員（唯讀）", order.get("staff_name") or "請至多月嫂排班設定", "staff"),
        ("訂單狀態（後端推導）", order.get("order_status") or "", "status"),
    )
    for column, (label, value, field_key) in zip(columns, fields):
        _read_only_field(
            column,
            label,
            str(value),
            f"{key_prefix}_{field_key}_{case_no}",
        )


def _read_only_field(column, label, value, key):
    column.text_input(label, value=value, disabled=True, key=key)


def _save_client_name(case_no, client_name, headers):
    normalized_name = client_name.strip()
    if not normalized_name:
        st.error("客戶名稱不可空白。")
        return
    try:
        preview = ClientNameApiClient(
            base_url=resolve_api_base_url(),
            headers=headers,
        ).preview(case_no, normalized_name)
    except (ClientNameApiError, ValueError) as error:
        st.error(f"客戶姓名預覽失敗：{error}")
        return
    st.session_state[f"client_name_preview_{case_no}"] = preview


def _apply_client_name(case_no, headers, preview: ClientNamePreviewView, reason):
    if not reason.strip():
        st.error("請填寫客戶姓名異動原因。")
        return
    try:
        ClientNameApiClient(
            base_url=resolve_api_base_url(),
            headers=headers,
        ).apply(
            case_no,
            preview,
            reason=reason.strip(),
            idempotency_key=str(uuid4()),
        )
    except (ClientNameApiError, ValueError) as error:
        st.error(f"客戶姓名套用失敗：{error}")
        return
    st.session_state.pop(f"client_name_preview_{case_no}", None)
    st.success("客戶姓名已套用；正式條款與排班未變更。")
    st.rerun()


# Kept cohesive because the toggle owns one lazy cross-Domain workflow boundary.
def _render_authoritative_workflows(case_no, order, headers):
    from ui.pages.order.case_architecture_bootstrap_panel import (
        ensure_case_architecture_ready,
    )

    st.markdown("### 正式業務操作 (合約、開工、退款、取消)")
    base_url = resolve_api_base_url()
    
    try:
        clients = _workflow_clients(base_url, headers)
        if not ensure_case_architecture_ready(
            case_no,
            clients["bootstrap"],
            require_service_time_complete=False,
        ):
            return
        _render_common_workflows(case_no, clients, headers)

        st.markdown("---")
        _render_order_state_workflow(case_no, order, clients)
    except Exception as e:
        import traceback
        st.warning(f"⚠️ 進階功能載入中止（舊案件尚未初始化或架構遺失）：{e}")
        st.expander("查看詳細錯誤").code(traceback.format_exc())


# Kept cohesive so all advanced clients share one URL and authorization snapshot.
def _workflow_clients(base_url, headers):
    from ui.api_clients.case_architecture_bootstrap_api_client import (
        CaseArchitectureBootstrapApiClient,
    )
    from ui.api_clients.order_actual_start_api_client import ActualStartApiClient
    from ui.api_clients.order_reopen_api_client import OrderReopenApiClient
    from ui.api_clients.order_cancellation_api_client import OrderCancellationApiClient
    from ui.api_clients.order_terms_api_client import OrderTermsApiClient

    return {
        "bootstrap": CaseArchitectureBootstrapApiClient(
            base_url=base_url,
            headers=headers,
        ),
        "actual_start": ActualStartApiClient(base_url=base_url, headers=headers),
        "reopen": OrderReopenApiClient(base_url=base_url, headers=headers),
        "cancellation": OrderCancellationApiClient(base_url=base_url, headers=headers),
        "terms": OrderTermsApiClient(base_url=base_url, headers=headers),
    }


# Kept cohesive because this is the fixed advanced workflow composition root.
def _render_common_workflows(case_no, clients, headers):
    from ui.pages.order.contract_match_panel import render_contract_match_panel
    from ui.pages.order.terms_panel import render_order_terms_panel
    from ui.pages.order.actual_start_panel import render_actual_start_panel

    render_contract_match_panel(case_no, headers)
    
    render_order_terms_panel(
        case_no,
        clients["terms"],
    )

    from ui.pages.order.service_date_confirmation_panel import render_service_date_confirmation_panel
    render_service_date_confirmation_panel(case_no, resolve_api_base_url(), headers)

    render_actual_start_panel(
        case_no,
        clients["actual_start"],
    )


def _render_order_state_workflow(case_no, order, clients):
    if order.get("order_status") == "訂單取消":
        from ui.pages.order.reopen_panel import render_order_reopen_panel

        render_order_reopen_panel(
            case_no,
            clients["reopen"],
        )
        return
    
    if order.get("order_status") != "訂單完成":
        from ui.pages.order.cancellation_panel import render_order_cancellation_panel
        render_order_cancellation_panel(
            case_no,
            clients["cancellation"],
        )
