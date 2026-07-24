"""
================================================================================
檔案名稱: ui/pages/order/tab2_assign.py
功能說明: Tab 2 月嫂配對中心 (OrderUI_Tab2_Assign)
================================================================================
"""

import streamlit as st
from services import db_service
from ui.pages.order.shared import safe_int


def _render_tab2_assign(orders_data, clients, staff_list):
    """Tab 2: 月嫂配對中心 (OrderUI_Tab2_MatchingCenter) - 僅處理「洽談中」待配對案件"""
    st.subheader("🤝 月嫂配對中心 (Clients, Orders & Matching)")

    pending_orders = [o for o in orders_data if o['order_status'] == '洽談中']

    if not pending_orders:
        st.info("目前系統沒有處於「洽談中」且待配對指派的案件。")
        return

    target_case_options = {
        f"案件 #{o['case_no']} - 客戶: {o['client_name']} ({o.get('identity_status') or '未設定'}, {o['service_days']}天)": o['case_no']
        for o in pending_orders
    }

    st.markdown("### ⚙️ 單筆待配對案件控制面板")
    selected_case_label = st.selectbox("🎯 選擇待配對與指派之案件", list(target_case_options.keys()), key="tab2_case_picker")
    target_case_no = target_case_options[selected_case_label]
    target_order = next((o for o in pending_orders if o['case_no'] == target_case_no), None)

    if not target_order:
        return

    # 單筆案件 3 大子選單標籤
    sub_tab1, sub_tab2, sub_tab3 = st.tabs(["👁️ 檢視案件詳情", "⚡ 4步智慧配對與指派", "❌ 取消訂單與紀錄原因"])

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
        try:
            match_records = db_service.get_order_matches(target_case_no)
        except Exception as e:
            st.error(f"讀取媒合記錄失敗: {e}")
            match_records = []

        # 僅顯示至少有一項發送紀錄或意願已更新的媒合紀錄
        valid_matches = [
            m for m in match_records
            if m['sent_info_1_at'] or m['sent_info_2_at'] or m['caregiver_accepted'] is not None
        ]
        if valid_matches:
            st.write("📋 當前月嫂意願詢問紀錄：")
            for m in valid_matches:
                acc_lbl = "🟢 願意接案" if m['caregiver_accepted'] == 1 else ("🔴 拒絕" if m['caregiver_accepted'] == 0 else "🟡 待回覆")
                s1 = f"已於 {m['sent_info_1_at'].strftime('%Y-%m-%d %H:%M')}" if m['sent_info_1_at'] else "未發送"
                s2 = f"已於 {m['sent_info_2_at'].strftime('%Y-%m-%d %H:%M')}" if m['sent_info_2_at'] else "未發送"
                st.markdown(f"**{m['staff_name']}** - 意願: `{acc_lbl}` (粗篩: {s1} | 精篩: {s2})")
            st.markdown("---")

        if not staff_list:
            st.warning("請先在服務人員資料表中建立服務人員。")
        else:
            with st.expander("🎯 智慧粗篩條件控制面板 (可自訂開啟/關閉，預設全選)", expanded=True):
                fc1, fc2 = st.columns(2)
                with fc1:
                    f_region = st.checkbox("☑️ 比對服務區域 (city/address 區域如香山/東區)", value=True, key="f_reg_toggle")
                    f_schedule = st.checkbox("☑️ 排除檔期時間衝突 (含 7 天預留備用期)", value=True, key="f_sch_toggle")
                with fc2:
                    f_babies = st.checkbox("☑️ 比對照顧胎數上限 (單/雙胞胎)", value=True, key="f_bab_toggle")
                    f_time = st.checkbox("☑️ 比對服務時段需求", value=True, key="f_time_toggle")

            try:
                rec_staff = db_service.get_recommended_staff_for_order(
                    case_no=target_case_no,
                    filter_region=f_region,
                    filter_schedule=f_schedule,
                    filter_babies=f_babies,
                    filter_time=f_time
                )
            except Exception as err:
                st.error(f"智慧粗篩比對計算失敗: {err}")
                rec_staff = []

            if not rec_staff:
                st.warning("⚠️ 依據當前勾選條件，暫無符合之月嫂。建議取消部分勾選以展開搜尋範圍。")
                staff_options = {f"{s['name']} ({s['phone']})": s['id'] for s in staff_list if s.get('name')}
            else:
                staff_options = {r['display_label']: r['staff_id'] for r in rec_staff}

            # ---------------------------------------------------------------
            # 步驟 1：粗篩發送 (多選) - 一次勾選多位候選月嫂批次發送 訂單資訊-1
            # ---------------------------------------------------------------
            st.markdown("##### 步驟 1: 發送 訂單資訊-1 (粗篩，可複選多位月嫂)")
            selected_staff_labels = st.multiselect(
                "選擇服務人員/月嫂進行粗篩發送 (已自動依匹配度與檔期排序)",
                list(staff_options.keys()),
                key="match_staff_multipicker"
            )
            selected_staff_ids = [staff_options[label] for label in selected_staff_labels]

            if st.button("1️⃣ 發送 訂單資訊-1 給已勾選月嫂 (粗篩)", key="btn_send_1_batch", disabled=not selected_staff_ids):
                try:
                    for sid in selected_staff_ids:
                        match_id = db_service.create_or_get_match_record(target_case_no, sid)
                        db_service.update_matching_info_sent(match_id, 1)
                    st.success(f"已對 {len(selected_staff_ids)} 位月嫂發送 訂單資訊-1！")
                    st.rerun()
                except Exception as e:
                    st.error(f"發送失敗: {e}")

            st.markdown("---")

            # ---------------------------------------------------------------
            # 步驟 2：意願狀態更新 + 精篩發送對象勾選 (合併為單一清單)
            # 清單來源＝所有「已發送過訂單資訊-1」的月嫂 (曾經粗篩發送過的名單)
            # ---------------------------------------------------------------
            sent1_matches = [m for m in match_records if m['sent_info_1_at']]

            st.markdown("##### 步驟 2: 更新月嫂意願 ＆ 發送 訂單資訊-2 (精篩，可複選多位月嫂)")

            if not sent1_matches:
                st.info("⚠️ 尚無月嫂收到 訂單資訊-1，請先完成步驟 1 的粗篩發送。")
            else:
                resp_opts = ["待回覆 (NULL)", "願意接案 (1)", "拒絕接案 (0)"]
                staff_ids_for_step2 = []

                for m in sent1_matches:
                    m_staff_id = m['staff_id']
                    c_idx = 1 if m['caregiver_accepted'] == 1 else (2 if m['caregiver_accepted'] == 0 else 0)

                    col_name, col_resp, col_chk = st.columns([2, 2, 1.2])
                    with col_name:
                        s2_lbl = "已於 " + m['sent_info_2_at'].strftime('%Y-%m-%d %H:%M') if m['sent_info_2_at'] else "尚未發送-2"
                        st.write(f"**{m['staff_name']}**\n\n({s2_lbl})")
                    with col_resp:
                        new_resp = st.selectbox(
                            "意願狀態", resp_opts, index=c_idx,
                            key=f"resp_select_{m['id']}", label_visibility="collapsed"
                        )
                        new_accepted_val = True if new_resp == "願意接案 (1)" else (False if new_resp == "拒絕接案 (0)" else None)
                        if new_accepted_val != (True if m['caregiver_accepted'] == 1 else (False if m['caregiver_accepted'] == 0 else None)):
                            try:
                                db_service.reply_matching_inquiry(m['id'], new_accepted_val)
                                st.rerun()
                            except Exception as e:
                                st.error(f"意願更新失敗: {e}")
                    with col_chk:
                        checked = st.checkbox("發送-2", key=f"send2_chk_{m['id']}")
                        if checked:
                            staff_ids_for_step2.append(m_staff_id)

                if st.button("2️⃣ 發送 訂單資訊-2 給已勾選月嫂 (精篩)", key="btn_send_2_batch", disabled=not staff_ids_for_step2):
                    try:
                        for sid in staff_ids_for_step2:
                            match_id = db_service.create_or_get_match_record(target_case_no, sid)
                            db_service.update_matching_info_sent(match_id, 2)
                        st.success(f"已對 {len(staff_ids_for_step2)} 位月嫂發送 訂單資訊-2！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"發送失敗: {e}")

            st.markdown("---")
            st.markdown("##### 步驟 3 & 4: 傳送履歷與定案指派")

            accepted_matches = [m for m in match_records if m['caregiver_accepted'] == 1]
            if accepted_matches:
                final_options = {m['staff_name']: m['staff_id'] for m in accepted_matches}
                final_staff_label = st.selectbox(
                    "選擇要成立訂單的月嫂 (僅列出已願意接案者)",
                    list(final_options.keys()),
                    key="final_assign_staff_picker"
                )
                final_staff_id = final_options[final_staff_label]

                st.success(f"🎉 月嫂 {final_staff_label} 已表達願意接案！")
                if st.button("🤝 3️⃣ 傳送履歷給客戶", key="btn_send_resume"):
                    st.info("已模擬將月嫂履歷與去識別化資料傳送給客戶備查。")

                if st.button("✍️ 4️⃣ 成立訂單並定案指派", key="btn_assign_confirm"):
                    try:
                        db_service.assign_staff_to_order(target_case_no, final_staff_id)
                        st.success("錄用成功！訂單已成立並生成初始檔期記錄。")
                        st.rerun()
                    except Exception as err:
                        st.error(f"指派失敗: {err}")
            else:
                st.info("⚠️ 提示：需待至少一位月嫂回覆「願意接案」後，方可進行傳送履歷與定案指派。")

    with sub_tab3:
        st.markdown(f"#### ❌ 取消訂單與紀錄原因 (案件編號: `{target_case_no}`)")
        if target_order['order_status'] == '訂單取消':
            st.warning(f"此案件先前已標記為「訂單取消」。原因：{target_order.get('cancel_reason') or '未註明'}")

        cancel_reason_input = st.text_area("請輸入取消訂單原因與說明 (強制紀錄)", value=target_order.get('cancel_reason') or "", key="cancel_reason_area")

        if st.button("🚨 確認取消此訂單", key="btn_cancel_order_confirm"):
            if not cancel_reason_input.strip():
                st.error("請務必填寫取消原因後再提交！")
            else:
                try:
                    db_service.update_order_status(target_case_no, '訂單取消', cancel_reason_input.strip())
                    st.success("訂單已標記為「訂單取消」，取消原因已儲存！")
                    st.rerun()
                except Exception as e:
                    st.error(f"取消訂單失敗: {e}")
