"""
================================================================================
檔案名稱: ui/pages/form_management/tab3_contract_management.py
功能說明: Tab 3 制式定型化契約管理 (EPPP 變數代理引擎) (FormManagementUI_Tab3_ContractManagement)
================================================================================
"""

import streamlit as st
from ui.pages.form_management.shared import (
    load_contract_templates,
    render_excel_contract_mirror,
)
from ui.api_clients.full_contract_preview_api_client import (
    FullContractPreviewApiClient,
    FullContractPreviewApiError,
)
from ui.api_clients.leave_substitution_api_client import (
    LeaveSubstitutionApiClient,
    LeaveSubstitutionApiError,
)
from ui.pages.shared import build_admin_headers, resolve_api_base_url


def _case_assignment_options(case_no, *, base_url, headers):
    """Return exact Scheduling assignment targets for the selected case."""
    cache_key = f"full_contract_assignments::{case_no}"
    cached = st.session_state.get(cache_key)
    if isinstance(cached, list):
        return cached
    assignments = LeaveSubstitutionApiClient(
        base_url=base_url,
        headers=headers,
    ).assignments(case_no)
    st.session_state[cache_key] = assignments
    return assignments


def _render_full_contract_preview(*, case_no, scope, assignment_id, base_url, headers):
    """Load exact typed values for the existing browser print view."""
    target_key = f"{case_no}::{scope}::{assignment_id or 'client'}"
    state_key = f"full_contract_preview::{target_key}"
    previous_key = st.session_state.get("full_contract_preview_active_key")
    if previous_key != state_key:
        if previous_key:
            st.session_state.pop(previous_key, None)
        st.session_state["full_contract_preview_active_key"] = state_key

    st.markdown("#### 📄 自動完整契約預覽")
    st.caption("欄位由正式資料來源自動套用；預覽後可直接在瀏覽器列印或另存 PDF。")
    preview_client = FullContractPreviewApiClient(base_url=base_url, headers=headers)
    if st.button(
        "讀取客戶完整契約" if scope == "client" else "讀取服務人員完整契約",
        key=f"full_contract_preview_button::{target_key}",
        type="primary",
        disabled=scope == "staff" and assignment_id is None,
    ):
        with st.spinner("正在讀取最新契約 owner projection…"):
            try:
                result = (
                    preview_client.preview_client(case_no)
                    if scope == "client"
                    else preview_client.preview_staff(case_no, assignment_id)
                )
                if result.case_no != case_no or (
                    scope == "staff" and result.assignment_id != assignment_id
                ):
                    raise FullContractPreviewApiError("契約預覽對象識別不一致。")
                st.session_state[state_key] = result
            except FullContractPreviewApiError as error:
                st.session_state[state_key] = error

    result = st.session_state.get(state_key)
    if isinstance(result, FullContractPreviewApiError):
        st.error(str(result))
        return None
    if result is None:
        st.info("請先讀取此案件的完整契約預覽。")
        return None
    if result.blockers:
        st.error("目前資料不足，系統不會顯示不完整契約。")
        for blocker in result.blockers:
            st.write(f"- {blocker}")
        return None
    if not result.ready_to_print:
        st.error("契約預覽尚未具備列印條件。")
        return None
    st.success("正式欄位已自動套用；請使用預覽內的列印按鈕另存 PDF。")
    return dict(result.field_values)


def _render_tab3_contract_management(form_db_table_fields, form_table_for_key, global_stats, target_order):
    """Show approved contracts with automatic typed values and browser printing."""
    st.markdown("### 📜 定型化契約預覽與列印")
    st.caption("契約欄位對照已由正式規格鎖定；系統會自動套用案件資料，不需人工調整欄位值。")
    st.markdown("---")

    contracts = load_contract_templates()
    if not contracts:
        st.warning("目前尚無任何定型化契約範本。已自動為您建立預設標準契約！")
        return

    c_names = {c['name']: c['id'] for c in contracts}

    c_pick_col, c_view_mode_col = st.columns([2.2, 1.8])
    with c_pick_col:
        sel_c_name = st.selectbox("選取契約範本", list(c_names.keys()), key="eppp_contract_picker")
        curr_contract = next((c for c in contracts if c['name'] == sel_c_name), contracts[0])
        curr_cid = curr_contract['id']

    contract_target_order = target_order
    staff_assignment_id = None
    if curr_cid == "contract_staff_service":
        if not target_order:
            contract_target_order = None
            st.info("請先選擇案件，再載入服務人員契約資料。")
        else:
            try:
                assignments = _case_assignment_options(
                    target_order["case_no"],
                    base_url=resolve_api_base_url(),
                    headers=build_admin_headers(),
                )
                if not assignments:
                    st.warning("此案件目前沒有可選的正式服務人員指派。")
                else:
                    labels = {
                        f"指派 #{item.assignment_id}｜{item.assigned_start_date}～{item.assigned_end_date}": item.assignment_id
                        for item in assignments
                    }
                    selected_label = st.selectbox(
                        "選擇服務人員正式指派（exact assignment）",
                        list(labels),
                        key=f"staff_contract_assignment::{target_order['case_no']}",
                    )
                    staff_assignment_id = labels[selected_label]
            except (LeaveSubstitutionApiError, ValueError) as error:
                st.error(f"服務人員指派清單目前無法載入：{error}")

    with c_view_mode_col:
        view_mode = st.radio(
            "預覽方式",
            ["🌓 欄位來源與契約", "🔍 100% 全寬預覽"],
            horizontal=True,
            key=f"v_mode_{curr_cid}",
        )

    st.markdown("---")

    mapped_values = None
    if target_order:
        mapped_values = _render_full_contract_preview(
            case_no=target_order["case_no"],
            scope="staff" if curr_cid == "contract_staff_service" else "client",
            assignment_id=staff_assignment_id,
            base_url=resolve_api_base_url(),
            headers=build_admin_headers(),
        )
        st.markdown("---")

    if curr_contract.get('template_filename', '').lower().endswith('.xlsx'):
        contract_html = render_excel_contract_mirror(
            curr_contract,
            contract_target_order,
            global_stats,
            mapped_values=mapped_values if target_order else None,
        )
    else:
        contract_html = "<div>預設範本</div>"

    if view_mode == "🔍 100% 全寬預覽":
        st.markdown("#### 👁️ 完整 A4 契約預覽")
        st.iframe(contract_html, height=1100)
        return

    col_c_left, col_c_right = st.columns([1, 1])
    with col_c_left:
        st.markdown("#### 🔒 已核准欄位來源")
        st.info("欄位對照為唯讀；如正式規格變更，應由版本化模板更新。")
        for cell, descriptor in curr_contract.get('param_mappings', {}).items():
            with st.container(border=True):
                st.markdown(f"**{cell}｜{descriptor.get('label', '填空欄位')}**")
                status = descriptor.get('status')
                if status == 'not_applicable':
                    st.caption("現行模型不適用，列印時自動留白")
                else:
                    st.caption(
                        f"來源：{descriptor.get('db_table', '未設定')} → "
                        f"{descriptor.get('db_key', '未設定')}"
                    )
    with col_c_right:
        st.markdown("#### 👁️ 契約預覽與套印")
        st.iframe(contract_html, height=750)
