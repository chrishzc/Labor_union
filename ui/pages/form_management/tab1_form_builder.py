"""
================================================================================
檔案名稱: ui/pages/form_management/tab1_form_builder.py
功能說明: Tab 1 手動創建與設計新表單 (UX 實驗室) (FormManagementUI_Tab1_FormBuilder)
================================================================================
"""

import json
import time
import streamlit as st
from datetime import date
from ui.pages.form_management.shared import (
    generate_field_id,
    get_table_for_key,
    format_db_value,
    save_single_template,
)


def _render_tab1_form_builder(form_db_table_fields, field_types, field_widths, global_stats, target_order):
    """TAB 1: 手動創建與設計新表單 (UX 實驗室)"""
    st.markdown("### 🛠️ 步驟一：表單基本資訊與用途設定")
    c_title, c_desc = st.columns([1.5, 2.5])
    with c_title:
        builder_title = st.text_input("表單名稱", value="自訂母嬰照顧合約證明", key="sbs_title_input")
    with c_desc:
        builder_desc = st.text_input("表單用途說明", value="供客戶申報補助與工會備查之標準單據", key="sbs_desc_input")

    st.markdown("---")
    st.markdown("### ⚙️ 步驟二：動態新增與設計表單欄位 (支援 [⬆️上移] [⬇️下移] 順序平移)")

    if 'builder_fields' not in st.session_state:
        st.session_state['builder_fields'] = [
            {"id": generate_field_id(), "label": "客戶姓名", "type": "db_link", "db_key": "client_name", "width": "half"},
            {"id": generate_field_id(), "label": "案件編號", "type": "db_link", "db_key": "case_no", "width": "half"},
            {"id": generate_field_id(), "label": "服務薪資", "type": "db_link", "db_key": "service_salary", "width": "half"},
            {"id": generate_field_id(), "label": "樓層費", "type": "db_link", "db_key": "floor_fee", "width": "half"},
            {"id": generate_field_id(), "label": "預計發薪日", "type": "db_link", "db_key": "salary_payment_date_1", "width": "half"},
            {"id": generate_field_id(), "label": "服務地址", "type": "db_link", "db_key": "address", "width": "full"},
            {"id": generate_field_id(), "label": "注意事項與簽名聲明", "type": "textarea", "db_key": "", "width": "full"}
        ]

    col_add, _ = st.columns([1, 4])
    with col_add:
        if st.button("➕ 新增一個新欄位", key="btn_add_sbs_field"):
            st.session_state['builder_fields'].append({
                "id": generate_field_id(),
                "label": f"新自訂欄位 {len(st.session_state['builder_fields']) + 1}",
                "type": "text",
                "db_key": "client_name",
                "width": "half"
            })
            st.rerun()

    seen_b_ids = set()
    for idx, f in enumerate(st.session_state['builder_fields']):
        fid = f.get('id')
        if not fid or fid in seen_b_ids:
            f['id'] = generate_field_id()
        seen_b_ids.add(f['id'])

    for idx, f in enumerate(st.session_state['builder_fields']):
        fid = f['id']
        with st.container(border=True):
            fc1, fc2, fc3, fc4, fc_up, fc_dn, fc_del = st.columns([2, 1.8, 2.2, 1.6, 0.5, 0.5, 0.6])
            with fc1:
                f['label'] = st.text_input(f"欄位 #{idx+1} 名稱", value=f['label'], key=f"sbs_fl_lbl_{fid}")
            with fc2:
                type_keys = list(field_types.keys())
                curr_t_idx = type_keys.index(f['type']) if f['type'] in type_keys else 0
                f['type'] = st.selectbox(f"資料型態", type_keys, index=curr_t_idx, format_func=lambda x: field_types[x], key=f"sbs_fl_type_{fid}")
            with fc3:
                if f['type'] == "db_link":
                    curr_db_k = f.get('db_key', 'client_name')
                    curr_tbl = get_table_for_key(curr_db_k)
                    tbl_list = list(form_db_table_fields.keys())
                    c_t_idx = tbl_list.index(curr_tbl) if curr_tbl in tbl_list else 0

                    sel_tbl = st.selectbox("1️⃣ 資料表來源", tbl_list, index=c_t_idx, key=f"sbs_tbl_t1_{fid}")

                    tbl_fmap = form_db_table_fields[sel_tbl]
                    f_keys = list(tbl_fmap.keys())
                    c_k_idx = f_keys.index(curr_db_k) if curr_db_k in f_keys else 0
                    f['db_key'] = st.selectbox("2️⃣ 綁定目標欄位", f_keys, index=c_k_idx, format_func=lambda x, labels=tbl_fmap: labels.get(x, x), key=f"sbs_fl_db_t1_{fid}")
                else:
                    st.caption("（手動填寫欄位）")
            with fc4:
                w_keys = list(field_widths.keys())
                f_w = f.get('width', 'half')
                curr_w_idx = w_keys.index(f_w) if f_w in w_keys else 0
                f['width'] = st.selectbox("排版寬度", w_keys, index=curr_w_idx, format_func=lambda x: field_widths[x], key=f"sbs_fl_w_{fid}")

            with fc_up:
                st.write("")
                if st.button("⬆️", key=f"btn_up_t1_{fid}", disabled=(idx == 0)):
                    st.session_state['builder_fields'][idx], st.session_state['builder_fields'][idx-1] = st.session_state['builder_fields'][idx-1], st.session_state['builder_fields'][idx]
                    st.rerun()
            with fc_dn:
                st.write("")
                if st.button("⬇️", key=f"btn_dn_t1_{fid}", disabled=(idx == len(st.session_state['builder_fields']) - 1)):
                    st.session_state['builder_fields'][idx], st.session_state['builder_fields'][idx+1] = st.session_state['builder_fields'][idx+1], st.session_state['builder_fields'][idx]
                    st.rerun()
            with fc_del:
                st.write("")
                if st.button("🗑️", key=f"btn_del_t1_{fid}"):
                    st.session_state['builder_fields'] = [x for x in st.session_state['builder_fields'] if x.get('id') != fid]
                    st.rerun()

    st.markdown("---")
    st.markdown("### 👁️ 步驟三：實時 UI 渲染預覽與 UX 測試區")

    with st.container(border=True):
        st.markdown(f"## 📋 【預覽】{builder_title}")
        st.caption(f"📝 說明：{builder_desc}")
        st.markdown("---")

        prev_cols = st.columns(2)
        for i, f in enumerate(st.session_state['builder_fields']):
            with prev_cols[i % 2]:
                lbl = f['label']
                f_type = f['type']

                if f_type == "db_link":
                    db_k = f.get('db_key', 'client_name')
                    if db_k in global_stats:
                        val_raw = global_stats[db_k]
                        val_disp = format_db_value(db_k, val_raw)
                        st.text_input(f"⚡ {lbl} (全域連動)", value=val_disp, disabled=True, key=f"pv_sbs_gdb_{i}")
                    else:
                        val_raw = target_order.get(db_k, '—') if target_order else '— (需選取單筆案件)'
                        val_disp = format_db_value(db_k, val_raw) if target_order else val_raw
                        st.text_input(f"⚡ {lbl} (單筆 DB 連動)", value=val_disp, disabled=True, key=f"pv_sbs_sdb_{i}")
                elif f_type == "text":
                    st.text_input(lbl, value="", key=f"pv_sbs_txt_{i}")
                elif f_type == "textarea":
                    st.text_area(lbl, value="", key=f"pv_sbs_area_{i}")
                elif f_type == "number":
                    st.number_input(lbl, value=0, step=1, key=f"pv_sbs_num_{i}")
                elif f_type == "date":
                    st.date_input(lbl, value=date.today(), key=f"pv_sbs_date_{i}")

        st.markdown("---")
        if st.button("💾 確定儲存為新表單模板", key="btn_save_sbs_tpl", type="primary"):
            if not builder_title.strip():
                st.error("請輸入表單名稱！")
            else:
                new_tpl = {
                    "id": f"tpl_{len(st.session_state.get('custom_form_templates', []))+1:02d}_{int(time.time())}",
                    "name": builder_title.strip(),
                    "desc": builder_desc.strip(),
                    "fields": json.loads(json.dumps(st.session_state['builder_fields']))
                }
                st.session_state.setdefault('custom_form_templates', []).append(new_tpl)
                save_single_template(new_tpl)
                st.success(f"🎉 新表單模板【{builder_title}】已成功寫入 `db/templates/{new_tpl['id']}.json` 保存！")
