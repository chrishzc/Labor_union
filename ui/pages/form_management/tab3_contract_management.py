"""
================================================================================
檔案名稱: ui/pages/form_management/tab3_contract_management.py
功能說明: Tab 3 制式定型化契約管理 (EPPP 變數代理引擎) (FormManagementUI_Tab3_ContractManagement)
================================================================================
"""

import os
import streamlit as st
from ui.pages.form_management.shared import (
    CONTRACTS_DIR,
    load_contract_templates,
    save_contract_template,
    fetch_staff_contract_context,
    flatten_staff_contract_context,
    format_db_value,
    render_excel_contract_mirror,
)


def _render_tab3_contract_management(form_db_table_fields, form_table_for_key, global_stats, target_order):
    """TAB 3: 制式定型化契約管理 (EPPP 變數代理引擎 - INV-UI-FORM-16/17/18)"""
    st.markdown("### 📜 定型化契約變數代理管理引擎 (EPPP Engine)")
    st.caption("輕鬆將 Excel 範本與系統 SQL 資料庫欄位動態綁定，支援 1:1 CSS A4 紙本鏡像視窗、全滿版預覽與全套範本生命週期管理。")
    st.markdown("---")

    contracts = load_contract_templates()
    if not contracts:
        st.warning("目前尚無任何定型化契約範本。已自動為您建立預設標準契約！")
        return

    c_names = {c['name']: c['id'] for c in contracts}

    c_pick_col, c_view_mode_col, c_btn_edit, c_btn_del = st.columns([2.2, 1.8, 1, 1])
    with c_pick_col:
        sel_c_name = st.selectbox("選取要檢視與設定的定型化契約範本", list(c_names.keys()), key="eppp_contract_picker")
        curr_contract = next((c for c in contracts if c['name'] == sel_c_name), contracts[0])
        curr_cid = curr_contract['id']

    contract_target_order = target_order
    if curr_cid == "contract_staff_service":
        if not target_order:
            contract_target_order = None
            st.info("請先選擇案件，再載入服務人員契約資料。")
        else:
            cache_key = f"contract_ctx_{target_order['case_no']}"
            assignment_text = st.text_input(
                "服務人員指派 ID（同案有多位月嫂時必填）",
                key=f"staff_contract_assignment_{target_order['case_no']}",
            ).strip()
            try:
                assignment_id = int(assignment_text) if assignment_text else None
                if assignment_id is not None and assignment_id < 1:
                    raise ValueError("指派 ID 必須為正整數")

                cached = st.session_state.get(cache_key)
                cached_case_no = cached.get("case_no") if isinstance(cached, dict) else None
                cached_assignment_id = cached.get("assignment_id") if isinstance(cached, dict) else None
                if cached is None or cached_case_no != target_order["case_no"] or cached_assignment_id != assignment_id:
                    contract_target_order = flatten_staff_contract_context(
                        fetch_staff_contract_context(target_order["case_no"], assignment_id)
                    )
                    st.session_state[cache_key] = {
                        "case_no": target_order["case_no"],
                        "assignment_id": assignment_id,
                        "data": contract_target_order,
                    }
                else:
                    contract_target_order = cached.get("data") if isinstance(cached, dict) else None
            except ValueError as error:
                contract_target_order = None
                st.warning(f"服務人員契約資料未載入：{error}")

    with c_view_mode_col:
        view_mode = st.radio("畫面排版視角 (INV-UI-FORM-28)", ["🌓 5:5 左右對照維護", "🔍 100% 全寬滿版預覽"], horizontal=True, key=f"v_mode_{curr_cid}")

    contract_edit_key = f"c_editing_{curr_cid}"
    contract_draft_key = f"c_draft_{curr_cid}"
    contract_del_modal_key = f"c_del_modal_{curr_cid}"

    is_contract_editing = st.session_state.get(contract_edit_key, False)

    with c_btn_edit:
        st.write("")
        if not is_contract_editing:
            if st.button("✏️ 編輯對照", key=f"btn_c_edit_{curr_cid}", use_container_width=True):
                st.session_state[contract_edit_key] = True
                st.session_state[contract_draft_key] = json.loads(json.dumps(curr_contract))
                st.rerun()
        else:
            if st.button("✖️ 取消編輯", key=f"btn_c_cancel_{curr_cid}", use_container_width=True):
                st.session_state[contract_edit_key] = False
                st.session_state.pop(contract_draft_key, None)
                st.rerun()

    with c_btn_del:
        st.write("")
        if st.button("🗑️ 刪除範本", key=f"btn_c_del_{curr_cid}", type="secondary", use_container_width=True):
            st.session_state[contract_del_modal_key] = True

    if st.session_state.get(contract_del_modal_key, False):
        with st.container(border=True):
            st.error(f"⚠️ **確定要永久刪除契約範本【{curr_contract['name']}】嗎？**")
            st.caption(f"此操作將從 `db/templates/contracts/{curr_cid}.json` 硬碟檔案中徹底移除！")

            dm_col1, dm_col2 = st.columns([1, 1])
            with dm_col1:
                if st.button("💥 確定永久刪除", key=f"btn_c_confirm_del_{curr_cid}", type="primary"):
                    fpath = os.path.join(CONTRACTS_DIR, f"{curr_cid}.json")
                    try:
                        if os.path.exists(fpath):
                            os.remove(fpath)
                    except Exception:
                        pass
                    st.session_state[contract_del_modal_key] = False
                    st.success(f"🗑️ 已成功刪除契約範本【{curr_contract['name']}】！")
                    st.rerun()
            with dm_col2:
                if st.button("取消", key=f"btn_c_cancel_del_modal_{curr_cid}"):
                    st.session_state[contract_del_modal_key] = False
                    st.rerun()

    st.markdown("---")

    if view_mode == "🔍 100% 全寬滿版預覽":
        st.markdown("#### 👁️ 100% 全螢幕/全寬滿版 A4 沉浸契約預覽視窗")
        st.info("💡 目前已進入全寬滿版預覽視角，文字更清晰大方！切換回【🌓 5:5 左右對照維護】即可邊改邊看！")

        param_values = {}
        for p_tag, p_info in curr_contract.get('param_mappings', {}).items():
            db_k = p_info.get('db_key', '')
            if db_k in global_stats:
                val_raw = global_stats[db_k]
                param_values[p_tag] = format_db_value(db_k, val_raw)
            elif target_order and db_k in target_order:
                val_raw = target_order.get(db_k, '')
                param_values[p_tag] = format_db_value(db_k, val_raw)
            else:
                param_values[p_tag] = f"<span style='color:#D32F2F; text-decoration:underline;'>___{p_info.get('label')}___</span>"

        if curr_contract.get('template_filename', '').lower().endswith('.xlsx'):
            contract_html = render_excel_contract_mirror(curr_contract, contract_target_order, global_stats)
        else:
            contract_html = f"<div>預設範本</div>"

        st.iframe(contract_html, height=1100)
    else:
        col_c_left, col_c_right = st.columns([1, 1])

        with col_c_left:
            if is_contract_editing:
                st.markdown("#### 🛠️ 編輯模式：{P1}~{PN} 變數代理草稿區")
                contract_draft = st.session_state.get(contract_draft_key, curr_contract)

                c_name_val = st.text_input("契約範本顯示名稱", value=contract_draft.get('name', ''), key=f"c_name_in_{curr_cid}")
                contract_draft['name'] = c_name_val

                mappings = contract_draft.get('param_mappings', {})
                updated_mappings = {}

                for p_tag, p_info in mappings.items():
                    with st.container(border=True):
                        st.markdown(f"**📌 參數標籤 `{{{p_tag}}}`** — `{p_info.get('label', '填空欄位')}`")

                        curr_db_k = p_info.get('db_key', 'client_name')
                        curr_tbl = form_table_for_key(curr_db_k)

                        tbl_list = list(form_db_table_fields.keys())
                        c_t_idx = tbl_list.index(curr_tbl) if curr_tbl in tbl_list else 0

                        c_col1, c_col2 = st.columns([1.5, 1.5])
                        with c_col1:
                            sel_tbl = st.selectbox("1️⃣ 選取 DB 資料表", tbl_list, index=c_t_idx, key=f"eppp_tbl_{curr_cid}_{p_tag}")
                        with c_col2:
                            tbl_fmap = form_db_table_fields[sel_tbl]
                            f_keys = list(tbl_fmap.keys())
                            c_k_idx = f_keys.index(curr_db_k) if curr_db_k in f_keys else 0
                            sel_fkey = st.selectbox("2️⃣ 綁定目標欄位", f_keys, index=c_k_idx, format_func=lambda x, labels=tbl_fmap: labels.get(x, x), key=f"eppp_fkey_{curr_cid}_{p_tag}")

                        updated_mappings[p_tag] = {
                            "label": p_info.get('label', '填空欄位'),
                            "db_table": sel_tbl,
                            "db_key": sel_fkey
                        }

                st.markdown("---")
                if st.button("💾 確定更新此契約範本 (寫入 JSON 檔)", key=f"btn_save_c_draft_{curr_cid}", type="primary"):
                    contract_draft['param_mappings'] = updated_mappings
                    save_contract_template(contract_draft)
                    st.session_state[contract_edit_key] = False
                    st.session_state.pop(contract_draft_key, None)
                    st.success(f"🎉 契約【{contract_draft['name']}】變數綁定設定已成功寫入硬碟 JSON 保存！")
                    st.rerun()
            else:
                st.markdown("#### ⚙️ 左側：{P1}~{PN} 變數代理標籤綁定卡片 (瀏覽模式)")
                st.info("💡 點擊上方【✏️ 編輯此契約對照】按鈕即可進入靈活編輯草稿模式！")

                mappings = curr_contract.get('param_mappings', {})
                for p_tag, p_info in mappings.items():
                    with st.container(border=True):
                        st.markdown(f"**📌 參數標籤 `{{{p_tag}}}`** — `{p_info.get('label', '填空欄位')}`")
                        st.caption(f"目前綁定: `{p_info.get('db_table', '未設定')}` $\rightarrow$ **`{p_info.get('db_key', '未設定')}`**")

        with col_c_right:
            st.markdown("#### 👁️ 右側：1:1 完整定型化契約預覽與套印區")

            param_values = {}
            for p_tag, p_info in curr_contract.get('param_mappings', {}).items():
                db_k = p_info.get('db_key', '')
                if db_k in global_stats:
                    val_raw = global_stats[db_k]
                    param_values[p_tag] = format_db_value(db_k, val_raw)
                elif target_order and db_k in target_order:
                    val_raw = target_order.get(db_k, '')
                    param_values[p_tag] = format_db_value(db_k, val_raw)
                else:
                    param_values[p_tag] = f"<span style='color:#D32F2F; text-decoration:underline;'>___{p_info.get('label')}___</span>"

            if curr_contract.get('template_filename', '').lower().endswith('.xlsx'):
                contract_html = render_excel_contract_mirror(curr_contract, contract_target_order, global_stats)
            else:
                contract_html = f"<div>預設範本</div>"

            st.iframe(contract_html, height=750)

            st.markdown("---")
            pdf_col1, pdf_col2 = st.columns([1, 1])
            with pdf_col1:
                st.download_button(
                    "📄 一鍵導出為 PDF / 印表機套印",
                    data=contract_html.encode('utf-8'),
                    file_name=f"{curr_contract['name']}_{contract_target_order.get('case_no', 'SAMPLE') if contract_target_order else 'DEMO'}.html",
                    mime="text/html",
                    key=f"dl_c_pdf_{curr_cid}",
                    use_container_width=True
                )
            with pdf_col2:
                st.download_button(
                    "📊 匯出實體 .xlsx 填空檔",
                    data=b"",
                    file_name=f"{curr_contract['name']}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_c_xlsx_{curr_cid}",
                    use_container_width=True,
                    disabled=True
                )
