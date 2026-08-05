"""
================================================================================
檔案名稱: ui/pages/order/tab2_assign.py
功能說明: Tab 2 月嫂配對中心 REST API 遷移版 (OrderUI_Tab2_Assign)
================================================================================
"""

from datetime import date, datetime, timedelta
import os
import requests
import streamlit as st
from ui.api_clients.assignment_plan_api_client import AssignmentPlanApiClient
from ui.api_clients.case_architecture_bootstrap_api_client import (
    CaseArchitectureBootstrapApiClient,
)
from ui.pages.order.case_architecture_bootstrap_panel import (
    ensure_case_architecture_ready,
)
from ui.pages.scheduling.assignment_plan_panel import (
    render_assignment_plan_panel,
)
from ui.pages.order.shared import safe_int
from ui.pages.shared import (
    build_admin_headers,
    resolve_api_base_url,
)


def _api_request(path, *, method="GET", payload=None, headers=None):
    request_headers = headers if headers is not None else build_admin_headers()
    response = requests.request(
        method,
        f"{resolve_api_base_url()}{path}",
        headers=request_headers,
        json=payload,
        timeout=15,
    )
    try:
        payload_body = response.json()
    except ValueError:
        payload_body = {"detail": response.text}
    if not response.ok:
        raise ValueError(f"HTTP {response.status_code}: {payload_body.get('detail') or payload_body.get('message') or payload_body}")
    if not payload_body.get("success", False):
        raise ValueError(payload_body.get("error") or payload_body.get("message") or "API 回應失敗")
    return payload_body.get("data") or {}


def _development_preview_is_enabled() -> bool:
    app_env = (os.getenv("APP_ENV", "development") or "development").strip().lower()
    return app_env in {"development", "dev", "local", "test"}


def _parse_iso_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        clean_value = value.split(" ")[0].strip()
        if not clean_value:
            return None
        return datetime.strptime(clean_value, "%Y-%m-%d").date()
    return None


def _iso_date_text(value, *, required=True, field_name="日期"):
    parsed = _parse_iso_date(value)
    if parsed is None:
        if required:
            raise ValueError(f"{field_name} 需提供 YYYY-MM-DD 日期")
        return None
    return parsed.isoformat()


def _single_caregiver_covers_service_period(order, *, headers):
    start_date = _iso_date_text(
        order.get("actual_start_date") or order.get("start_date"),
        required=True,
        field_name="服務開始日",
    )
    raw_end = order.get("actual_end_date") or order.get("end_date")
    if raw_end:
        end_date = _iso_date_text(raw_end, required=True, field_name="服務結束日")
    else:
        service_days = int(safe_int(order.get("service_days")))
        if service_days <= 0:
            raise ValueError("服務天數必須為正整數")
        end_date = (
            datetime.strptime(start_date, "%Y-%m-%d").date()
            + timedelta(days=service_days - 1)
        ).isoformat()
    availability = _api_request(
        f"/api/v1/orders/{order['case_no']}/caregiver-single-eligibility/check",
        method="POST",
        headers=headers,
        payload={
            "start_date": start_date,
            "end_date": end_date,
            "as_of": date.today().isoformat(),
        },
    )
    return bool(availability.get("complete_combinations"))


def _render_tab2_assign(
    orders_data,
    clients,
    staff_list,
    *,
    multi_segment_renderer=None,
    multi_segment_preview_renderer=None,
    preferred_case_no=None,
):
    """Tab 2: 月嫂配對中心 (OrderUI_Tab2_MatchingCenter) - 僅處理「洽談中」待配對案件"""
    st.subheader("🤝 月嫂配對中心 (Clients, Orders & Matching)")
    success_message = st.session_state.pop("tab2_assignment_sync_success", None)
    if success_message:
        st.success(success_message)
        st.toast(success_message)

    pending_orders = [o for o in orders_data if o['order_status'] == '洽談中']

    if not pending_orders:
        st.info("目前系統沒有處於「洽談中」且待配對指派的案件。")
        return

    target_case_options = {
        f"案件 #{o['case_no']} - 客戶: {o['client_name']} ({o.get('identity_status') or '未設定'}, {o['service_days']}天)": o['case_no']
        for o in pending_orders
    }

    st.markdown("### ⚙️ 單筆待配對案件控制面板")
    preferred_label = next(
        (
            label
            for label, case_no in target_case_options.items()
            if preferred_case_no is not None
            and str(case_no) == str(preferred_case_no)
        ),
        None,
    )
    if preferred_label is not None:
        st.session_state["tab2_case_picker"] = preferred_label
    selected_case_label = st.selectbox("🎯 選擇待配對與指派之案件", list(target_case_options.keys()), key="tab2_case_picker")
    target_case_no = target_case_options[selected_case_label]
    target_order = next((o for o in pending_orders if o['case_no'] == target_case_no), None)

    if not target_order:
        return

    try:
        admin_headers = build_admin_headers()
    except Exception as err:
        st.error(f"未完成管理員授權設定：{err}")
        return

    # 單筆案件 3 大子選單標籤
    sub_tab1, sub_tab2 = st.tabs(
        ["👁️ 檢視案件詳情", "⚡ 4步智慧配對與指派"]
    )

    with sub_tab1:
        st.markdown(f"#### 案件基本資訊 (案件編號: `{target_case_no}`)")
        cd1, cd2 = st.columns(2)
        with cd1:
            st.write(f"- **客戶姓名**: {target_order['client_name']}")
            st.write(f"- **聯絡電話**: {target_order.get('phone', '未提供')}")
            st.write(f"- **身分資格（唯讀）**: {target_order.get('identity_status') or '未設定'}")
            st.write(f"- **預計服務開始日**: {target_order.get('start_date', '未定')}")
            st.write(f"- **預計服務結束日**: {target_order.get('end_date', '未定')}")
        with cd2:
            st.write(f"- **訂單狀態**: `{target_order['order_status']}`")
            st.write(f"- **目前服務人員**: {target_order.get('staff_name') or '尚未指派'}")
            st.write(f"- **樓層費**: {safe_int(target_order.get('floor_fee')):,} 元")
            st.write(f"- **自費預估合計**: {safe_int(target_order.get('total_employer_self_pay_payable')):,} 元")
            if target_order['order_status'] == '訂單取消':
                st.error(f"- **取消原因**: {target_order.get('cancel_reason') or '未註明'}")

    with sub_tab2:
        st.markdown(f"#### ⚡ 4步智慧配對與指派 (案件 #{target_case_no})")
        if multi_segment_renderer is None:
            from ui.pages.scheduling.matching_center import _render_multi_segment_matching
            multi_segment_renderer = _render_multi_segment_matching

        if _development_preview_is_enabled():
            preview_key = f"matching_multi_preview_{target_case_no}"
            preview_enabled = bool(st.session_state.get(preview_key))
            button_label = (
                "關閉多月嫂測試預覽"
                if preview_enabled
                else "測試顯示多月嫂配對"
            )
            if st.button(
                button_label,
                key=f"matching_multi_preview_button_{target_case_no}",
            ):
                st.session_state[preview_key] = not preview_enabled
                st.rerun()
        else:
            preview_enabled = False

        if preview_enabled and multi_segment_preview_renderer is not None:
            st.info(
                "開發測試預覽：只查詢多人檔期並顯示介面，不建立配對方案、不聯繫月嫂。"
            )
            multi_segment_preview_renderer(target_order, staff_list)
            return

        if not staff_list:
            st.warning("請先在服務人員資料表中建立服務人員。")
            return

        multi_segment_renderer(
            target_order,
            staff_list,
            preview_only=False,
        )
