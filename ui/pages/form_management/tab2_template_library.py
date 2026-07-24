"""
================================================================================
檔案名稱: ui/pages/form_management/tab2_template_library.py
功能說明: Tab 2 自訂表單模板庫與 5:5 雙視窗線上編輯預覽 (FormManagementUI_Tab2_TemplateLibrary)
================================================================================
"""

import json
import streamlit as st
from ui.pages.form_management.shared import (
    generate_field_id,
    get_table_for_key,
    delete_single_template,
    save_single_template,
    render_html_document,
)


def _render_tab2_template_library(form_db_table_fields, field_types, field_widths, global_stats, target_order):
    """TAB 2: 自訂表單模板庫 (5:5 雙視窗 Side-by-Side + 拖拉排序 + 二次確認刪除)"""
    st.markdown("### 🗄️ 所有已建立之表單模板庫 (支援 5:5 雙視窗實時預覽、順序平移與二次刪除確認)")

    custom_templates = st.session_state.get('custom_form_templates', [])
    if not custom_templates:
        st.info("目前尚無任何自訂表單模板。請至 Tab 1 手動創建新表單。")
        return

    tpl_names = {t['name']: t['id'] for t in custom_templates}
    sel_tpl_name = st.selectbox("選取要檢視或修改的表單模板", list(tpl_names.keys()), key="sbs_tpl_picker")
    curr_tpl_idx = next((i for i, t in enumerate(custom_templates) if t['name'] == sel_tpl_name), 0)
    curr_tpl = custom_templates[curr_tpl_idx]

    btn_col1, btn_col2, _ = st.columns([1.5, 1.5, 3])
    edit_key = f"editing_mode_{curr_tpl['id']}"
    if edit_key not in st.session_state:
        st.session_state[edit_key] = False

    draft_key = f"edit_draft_tpl_{curr_tpl['id']}"
    confirm_del_key = f"confirm_del_mode_{curr_tpl['id']}"
    if confirm_del_key not in st.session_state:
        st.session_state[confirm_del_key] = False

    with btn_col1:
        if st.button("✏️ 編輯修改此模板與欄位順序", key=f"btn_toggle_sbs_{curr_tpl['id']}", type="primary"):
            st.session_state[edit_key] = not st.session_state[edit_key]
            if st.session_state[edit_key]:
                d_copy = json.loads(json.dumps(curr_tpl))
                for idx, f in enumerate(d_copy.get('fields', [])):
                    if not f.get('id'):
                        f['id'] = generate_field_id()
                st.session_state[draft_key] = d_copy
            else:
                st.session_state.pop(draft_key, None)
            st.rerun()

    with btn_col2:
        if st.button("🗑️ 刪除此表單模板", key=f"btn_trigger_del_{curr_tpl['id']}"):
            st.session_state[confirm_del_key] = True
            st.rerun()

    if st.session_state[confirm_del_key]:
        with st.container(border=True):
            st.warning(f"⚠️ **確定要永久刪除【{curr_tpl['name']}】表單模板嗎？** 此動作無法復原！")
            c_del1, c_del2, _ = st.columns([1.5, 1.5, 4])
            with c_del1:
                if st.button("💥 確定永久刪除", key=f"btn_do_del_{curr_tpl['id']}", type="primary"):
                    del_target_id = curr_tpl['id']
                    st.session_state['custom_form_templates'].pop(curr_tpl_idx)
                    delete_single_template(del_target_id)
                    st.session_state[confirm_del_key] = False
                    st.success(f"已成功永久刪除模板實體檔案：{curr_tpl['name']}")
                    st.rerun()
            with c_del2:
                if st.button("✖️ 取消刪除", key=f"btn_cancel_del_{curr_tpl['id']}"):
                    st.session_state[confirm_del_key] = False
                    st.rerun()

    if st.session_state[edit_key] and draft_key in st.session_state:
        st.markdown("---")
        draft_tpl = st.session_state[draft_key]
        st.markdown(f"### ✏️ 5:5 雙視窗線上編輯【{draft_tpl['name']}】草稿 (左側編輯，右側 0.1秒實時同步預覽)")

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown("#### ⚙️ 左側：編輯名稱與欄位順序平移")
            ed_name = st.text_input("表單名稱", value=draft_tpl['name'], key=f"ed_sbs_name_{draft_tpl['id']}")
            ed_desc = st.text_input("用途說明", value=draft_tpl['desc'], key=f"ed_sbs_desc_{draft_tpl['id']}")
            draft_tpl['name'] = ed_name
            draft_tpl['desc'] = ed_desc

            col_add_e, _ = st.columns([1, 2])
            with col_add_e:
                if st.button("➕ 追加一個新欄位", key=f"btn_add_sbs_e_{draft_tpl['id']}"):
                    draft_tpl['fields'].append({
                        "id": generate_field_id(),
                        "label": f"新自訂欄位 {len(draft_tpl['fields']) + 1}",
                        "type": "text",
                        "db_key": "",
                        "width": "half"
                    })
                    st.rerun()

            seen_d_ids = set()
            for idx, f in enumerate(draft_tpl['fields']):
                fid = f.get('id')
                if not fid or fid in seen_d_ids:
                    f['id'] = generate_field_id()
                seen_d_ids.add(f['id'])

            for idx, f in enumerate(draft_tpl['fields']):
                fid = f['id']
                with st.container(border=True):
                    st.caption(f"📌 欄位 #{idx+1}")
                    e_c1, e_c2 = st.columns([1.5, 1.5])
                    with e_c1:
                        f['label'] = st.text_input("欄位名稱", value=f['label'], key=f"se_lbl_{draft_tpl['id']}_{fid}")
                    with e_c2:
                        type_keys = list(field_types.keys())
                        c_t_idx = type_keys.index(f['type']) if f['type'] in type_keys else 0
                        f['type'] = st.selectbox("資料型態", type_keys, index=c_t_idx, format_func=lambda x: field_types[x], key=f"se_type_{draft_tpl['id']}_{fid}")

                    e_c3, e_c4 = st.columns([1.5, 1.5])
                    with e_c3:
                        if f['type'] == "db_link":
                            curr_db_k = f.get('db_key', 'client_name')
                            curr_tbl = get_table_for_key(curr_db_k)
                            tbl_list = list(form_db_table_fields.keys())
                            c_t_idx = tbl_list.index(curr_tbl) if curr_tbl in tbl_list else 0

                            sel_tbl = st.selectbox("1️⃣ 資料表來源", tbl_list, index=c_t_idx, key=f"se_tbl_{draft_tpl['id']}_{fid}")

                            tbl_fmap = form_db_table_fields[sel_tbl]
                            f_keys = list(tbl_fmap.keys())
                            c_k_idx = f_keys.index(curr_db_k) if curr_db_k in f_keys else 0
                            f['db_key'] = st.selectbox("2️⃣ 綁定目標欄位", f_keys, index=c_k_idx, format_func=lambda x, labels=tbl_fmap: labels.get(x, x), key=f"se_db_{draft_tpl['id']}_{fid}")
                        else:
                            st.caption("（手動填寫）")
                    with e_c4:
                        w_keys = list(field_widths.keys())
                        f_w = f.get('width', 'half')
                        c_w_idx = w_keys.index(f_w) if f_w in w_keys else 0
                        f['width'] = st.selectbox("排版寬度", w_keys, index=c_w_idx, format_func=lambda x: field_widths[x], key=f"se_w_{draft_tpl['id']}_{fid}")

                    b_u, b_d, b_x, _ = st.columns([1, 1, 1, 3])
                    with b_u:
                        if st.button("⬆️ 上移", key=f"b_up_{draft_tpl['id']}_{fid}", disabled=(idx == 0)):
                            draft_tpl['fields'][idx], draft_tpl['fields'][idx-1] = draft_tpl['fields'][idx-1], draft_tpl['fields'][idx]
                            st.rerun()
                    with b_d:
                        if st.button("⬇️ 下移", key=f"b_dn_{draft_tpl['id']}_{fid}", disabled=(idx == len(draft_tpl['fields']) - 1)):
                            draft_tpl['fields'][idx], draft_tpl['fields'][idx+1] = draft_tpl['fields'][idx+1], draft_tpl['fields'][idx]
                            st.rerun()
                    with b_x:
                        if st.button("🗑️ 刪除", key=f"b_del_{draft_tpl['id']}_{fid}"):
                            draft_tpl['fields'] = [x for x in draft_tpl['fields'] if x.get('id') != fid]
                            st.rerun()

            st.markdown("---")
            es1, es2 = st.columns([1.5, 2])
            with es1:
                if st.button("💾 確定更新此模板 (寫入獨立 JSON 檔)", key=f"btn_save_sbs_tpl_chg_{draft_tpl['id']}", type="primary"):
                    if not ed_name.strip():
                        st.error("表單名稱不能為空！")
                    else:
                        updated_tpl = json.loads(json.dumps(draft_tpl))
                        st.session_state['custom_form_templates'][curr_tpl_idx] = updated_tpl
                        save_single_template(updated_tpl)
                        st.session_state[edit_key] = False
                        st.session_state.pop(draft_key, None)
                        st.success(f"🎉 模板【{ed_name}】已成功更新寫入 `db/templates/{updated_tpl['id']}.json`！")
                        st.rerun()
            with es2:
                if st.button("✖️ 取消編輯 (丟棄草稿)", key=f"btn_cancel_sbs_edit_{draft_tpl['id']}"):
                    st.session_state[edit_key] = False
                    st.session_state.pop(draft_key, None)
                    st.info("已取消編輯，草稿已丟棄。")
                    st.rerun()

        with col_right:
            st.markdown("#### 👁️ 右側：實時單據與 PDF 即時預覽")
            live_html = render_html_document(draft_tpl, target_order, global_stats)
            st.iframe(live_html, height=620)

    else:
        st.markdown("---")
        doc_html = render_html_document(curr_tpl, target_order, global_stats)
        st.iframe(doc_html, height=580)
