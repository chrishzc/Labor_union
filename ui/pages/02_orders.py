"""
================================================================================
檔案名稱: ui/pages/02_orders.py
功能說明: 訂單與帳務管理系統頁面殼層 (OrderUI)
專案名稱: Lobar Union - 服務人員與訂單管理系統
建立日期: 2026-07-03
架構規範: ADAD Version 18 (完全拆分解耦，僅保留訂單與帳務 Tab)
================================================================================
職責與業務規則:
1. 讀取初始化資料 (orders, clients, staff)，分發渲染三大 Tab:
   - Tab 1: 📊 訂單總覽與計算對帳 (對齊《訂單系統.csv》，展示 case_no, start_date, end_date, cancel_reason)
   - Tab 2: 🤝 案件與配對中心 (對齊規格書頁面三，一站式檢視、4步智慧配對、取消訂單，取消手動建立訂單需求)
   - Tab 3: 💰 更新實收財務 (實收與轉帳欄位登錄，帳務狀態推進)
2. 服務人員行事曆與檔期調控功能已完全抽離至 ui/pages/03_calendar.py。
================================================================================
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import math
import importlib
from services import db_service
importlib.reload(db_service)

title = "📦 訂單與帳務管理系統"

def safe_float(val) -> float:
    if val is None:
        return 0.0
    try:
        f = float(val)
        return 0.0 if math.isnan(f) or math.isinf(f) else f
    except:
        return 0.0

def safe_int(val) -> int:
    """安全轉換整數，防護 None, NaN, Inf 及無效字串 (ADR-v18-03)"""
    if val is None:
        return 0
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return 0
        return int(round(f))
    except:
        return 0

def safe_date(val):
    if not val:
        return datetime.today().date()
    if isinstance(val, datetime):
        return val.date()
    if hasattr(val, "date"):
        return val
    if isinstance(val, (str, bytes)):
        try:
            clean_str = str(val).split(" ")[0].strip()
            return datetime.strptime(clean_str, "%Y-%m-%d").date()
        except:
            return datetime.today().date()
    return val


def _render_tab1_overview(orders_data):
    """Tab 1: 訂單期款與月嫂薪資預估總覽 (OrderUI_Tab1_Overview)"""
    st.subheader("訂單期款與月嫂薪資預估總覽")
    if not orders_data:
        st.info("目前尚無任何訂單資料。")
        return

    df_orders = pd.DataFrame(orders_data)

    status_filter = st.multiselect(
        "篩選訂單狀態",
        options=["洽談中", "訂單成立", "服務中", "訂單完成", "訂單取消"],
        default=["洽談中", "訂單成立", "服務中", "訂單完成"]
    )

    df_filtered = df_orders[df_orders['order_status'].isin(status_filter)] if status_filter else df_orders

    search_name = st.text_input("搜尋案件編號、客戶或服務人員姓名", "")
    if search_name:
        df_filtered = df_filtered[
            df_filtered['case_no'].astype(str).str.contains(search_name, case=False, na=False) |
            df_filtered['client_name'].str.contains(search_name, case=False, na=False) |
            df_filtered['staff_name'].str.contains(search_name, case=False, na=False)
        ]

    st.write(f"顯示 {len(df_filtered)} 筆訂單：")

    display_cols = {
        "notes": "備註",
        "case_no": "訂單編號",
        "service_hours_per_day": "服務時段",
        "start_date": "預期服務開始日",
        "client_name": "客戶名稱",
        "service_days": "希望服務天數",
        "subsidy_eligibility": "補助資格",
        "total_hours": "總時數",
        "subsidy_hours": "補助時數",
        "self_pay_hours": "自費時數",
        "claim_total_days": "請款總日數",
        "floor_fee": "樓層費用",
        "deposit_received_at": "訂金日期",
        "employer_hourly_rate": "雇主單價",
        "deposit_days": "訂金天數",
        "deposit_amount": "訂金",
        "first_payment_date": "第一期款入帳日",
        "first_payment_days": "第一期款天數",
        "first_payment_amount": "第一期金額",
        "second_payment_date": "第二期款入帳日",
        "second_payment_days": "第二期款天數",
        "second_payment_amount": "第二期金額",
        "total_employer_self_pay_payable": "雇主自費合計金額",
        "order_status": "訂單成立狀態",
        "staff_name": "服務人員",
        "service_salary": "服務單價",
        "salary_payment_date_1": "付款日-1",
        "subsidy_salary": "補助薪資",
        "salary_payment_date_2": "付款日-2",
        "govt_claim_date": "市府請款",
        "actual_start_date": "服務開始",
        "actual_end_date": "服務結束",
        "custom_leave_dates": "特殊休假",
        "service_mode": "休假方式",
        "due_date": "預產期",
        "cancel_reason": "取消原因"
    }

    df_filtered = df_filtered.copy()
    if 'actual_end_date' not in df_filtered.columns or df_filtered['actual_end_date'].isnull().all():
        if 'end_date' in df_filtered.columns:
            df_filtered['actual_end_date'] = df_filtered['end_date']

    existing_cols = [col for col in display_cols.keys() if col in df_filtered.columns]
    df_display = df_filtered[existing_cols].copy()
    
    # 統一將所有費用與金額欄位轉換為整數 (防範 NaN)
    money_cols = [
        "floor_fee", "deposit_amount", "initial_payment_payable", 
        "first_payment_amount", "second_payment_amount", 
        "total_employer_self_pay_payable", "service_salary", "subsidy_salary",
        "employer_hourly_rate", "caregiver_rate"
    ]
    for col in money_cols:
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(safe_int)

    df_display = df_display.rename(columns=display_cols)
    st.dataframe(df_display, width='stretch', hide_index=True)


def _render_tab2_assign(orders_data, clients, staff_list):
    """Tab 2: 案件與配對中心 (OrderUI_Tab2_MatchingCenter) - 僅處理「洽談中」待配對案件"""
    st.subheader("🤝 案件與配對中心 (Clients, Orders & Matching)")
    
    pending_orders = [o for o in orders_data if o['order_status'] == '洽談中']

    if not pending_orders:
        st.info("目前系統沒有處於「洽談中」且待配對指派的案件。")
        return

    target_case_options = {
        f"案件 #{o.get('case_no') or o['order_id']} - 客戶: {o['client_name']} ({o['subsidy_eligibility']}, {o['service_days']}天)": o['order_id']
        for o in pending_orders
    }

    st.markdown("### ⚙️ 單筆待配對案件控制面板")
    selected_case_label = st.selectbox("🎯 選擇待配對與指派之案件", list(target_case_options.keys()), key="tab2_case_picker")
    target_order_id = target_case_options[selected_case_label]
    target_order = next((o for o in pending_orders if o['order_id'] == target_order_id), None)

    if not target_order:
        return

    # 單筆案件 3 大子選單標籤
    sub_tab1, sub_tab2, sub_tab3 = st.tabs(["👁️ 檢視案件詳情", "⚡ 4步智慧配對與指派", "❌ 取消訂單與紀錄原因"])

    with sub_tab1:
        st.markdown(f"#### 案件基本資訊 (案件編號: `{target_order.get('case_no') or target_order['order_id']}`)")
        cd1, cd2 = st.columns(2)
        with cd1:
            st.write(f"- **客戶姓名**: {target_order['client_name']}")
            st.write(f"- **聯絡電話**: {target_order.get('phone', '未提供')}")
            st.write(f"- **身分資格**: {target_order['subsidy_eligibility']}")
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
        st.markdown(f"#### ⚡ 4步智慧配對與指派 (案件 #{target_order.get('case_no') or target_order['order_id']})")
        try:
            match_records = db_service.get_order_matches(target_order_id)
        except Exception as e:
            st.error(f"讀取媒合記錄失敗: {e}")
            match_records = []

        if match_records:
            st.write("📋 當前月嫂意願詢問紀錄：")
            for m in match_records:
                acc_lbl = "🟢 願意接案" if m['caregiver_accepted'] == 1 else ("🔴 拒絕" if m['caregiver_accepted'] == 0 else "🟡 待回覆")
                s1 = f"已於 {m['sent_info_1_at'].strftime('%Y-%m-%d %H:%M')}" if m['sent_info_1_at'] else "未發送"
                s2 = f"已於 {m['sent_info_2_at'].strftime('%Y-%m-%d %H:%M')}" if m['sent_info_2_at'] else "未發送"
                st.markdown(f"**{m['staff_name']}** - 意願: `{acc_lbl}` (粗篩: {s1} | 精篩: {s2})")
            st.markdown("---")

        if not staff_list:
            st.warning("請先在服務人員資料表中建立服務人員。")
        else:
            staff_options = {f"{s['name']} ({s['phone']})": s['id'] for s in staff_list if s.get('name')}
            selected_staff_label = st.selectbox("選擇服務人員/月嫂進行操作", list(staff_options.keys()), key="match_staff_picker")
            staff_id_to_assign = staff_options[selected_staff_label]

            try:
                match_id = db_service.create_or_get_match_record(target_order_id, staff_id_to_assign)
                match_records_updated = db_service.get_order_matches(target_order_id)
                curr_match = next((m for m in match_records_updated if m['staff_id'] == staff_id_to_assign), None)
            except Exception as e:
                st.error(f"建立配對記錄失敗: {e}")
                curr_match = None

            if curr_match:
                st.markdown("##### 步驟 1 & 2: 發送需求與詢問意願")
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    btn_t1 = "再次發送 訂單資訊-1" if curr_match['sent_info_1_at'] else "1️⃣ 發送 訂單資訊-1 (粗篩)"
                    if st.button(btn_t1, key="btn_send_1"):
                        db_service.update_matching_info_sent(match_id, 1)
                        st.success("已發送 訂單資訊-1！")
                        st.rerun()

                with col_f2:
                    btn_t2 = "再次發送 訂單資訊-2" if curr_match['sent_info_2_at'] else "2️⃣ 發送 訂單資訊-2 (精篩)"
                    if st.button(btn_t2, key="btn_send_2"):
                        db_service.update_matching_info_sent(match_id, 2)
                        st.success("已發送 訂單資訊-2！")
                        st.rerun()

                resp_opts = ["待回覆 (NULL)", "願意接案 (1)", "拒絕接案 (0)"]
                c_idx = 1 if curr_match['caregiver_accepted'] == 1 else (2 if curr_match['caregiver_accepted'] == 0 else 0)
                selected_resp = st.selectbox("更新月嫂意願狀態", resp_opts, index=c_idx, key="select_caregiver_resp")

                if st.button("更新意願", key="btn_update_resp"):
                    accepted_val = True if selected_resp == "願意接案 (1)" else (False if selected_resp == "拒絕接案 (0)" else None)
                    db_service.reply_matching_inquiry(match_id, accepted_val)
                    st.success("月嫂意願狀態已更新！")
                    st.rerun()

                st.markdown("---")
                st.markdown("##### 步驟 3 & 4: 傳送履歷與定案指派")
                if curr_match['caregiver_accepted'] == 1:
                    st.success(f"🎉 月嫂 {curr_match['staff_name']} 已表達願意接案！")
                    if st.button("🤝 3️⃣ 傳送履歷給客戶", key="btn_send_resume"):
                        st.info("已模擬將月嫂履歷與去識別化資料傳送給客戶備查。")

                    if st.button("✍️ 4️⃣ 成立訂單並定案指派", key="btn_assign_confirm"):
                        try:
                            db_service.assign_staff_to_order(target_order_id, staff_id_to_assign)
                            st.success("錄用成功！訂單已成立並生成初始檔期記錄。")
                            st.rerun()
                        except Exception as err:
                            st.error(f"指派失敗: {err}")
                else:
                    st.info("⚠️ 提示：需待月嫂回覆「願意接案」後，方可進行傳送履歷與定案指派。")

    with sub_tab3:
        st.markdown(f"#### ❌ 取消訂單與紀錄原因 (案件編號: `{target_order.get('case_no') or target_order['order_id']}`)")
        if target_order['order_status'] == '訂單取消':
            st.warning(f"此案件先前已標記為「訂單取消」。原因：{target_order.get('cancel_reason') or '未註明'}")
        
        cancel_reason_input = st.text_area("請輸入取消訂單原因與說明 (強制紀錄)", value=target_order.get('cancel_reason') or "", key="cancel_reason_area")
        
        if st.button("🚨 確認取消此訂單", key="btn_cancel_order_confirm"):
            if not cancel_reason_input.strip():
                st.error("請務必填寫取消原因後再提交！")
            else:
                try:
                    db_service.update_order_status(target_order_id, '訂單取消', cancel_reason_input.strip())
                    st.success("訂單已標記為「訂單取消」，取消原因已儲存！")
                    st.rerun()
                except Exception as e:
                    st.error(f"取消訂單失敗: {e}")


def _render_tab3_finance(orders_data):
    """Tab 3: 更新實收財務 (OrderUI_Tab3_Finance)"""
    st.subheader("更新實收財務欄位與日期")
    st.write("在收到訂金、尾款，或向月嫂轉帳後，可在此更新實際金額與入帳日期。")

    try:
        payments_raw = db_service.get_table_data('payments')
    except Exception as e:
        st.error(f"無法讀取財務帳務原始資料: {e}")
        return

    if not payments_raw:
        st.info("目前沒有帳務紀錄。")
        return

    pay_options = {
        f"案件 #{p['case_no']} - 客戶: {p['client_name']} [狀態: {p['payment_status']}]": p['order_id']
        for p in payments_raw if p['order_id'] is not None
    }

    if not pay_options:
        st.info("目前沒有關聯訂單的帳務紀錄。")
        return

    selected_pay_label = st.selectbox("選擇欲更新帳務的訂單", list(pay_options.keys()), key="fin_pay_picker")
    pay_order_id = pay_options[selected_pay_label]

    current_pay = next((p for p in payments_raw if p['order_id'] == pay_order_id), None)
    current_view_order = next((o for o in orders_data if o['order_id'] == pay_order_id), None)

    if not (current_pay and current_view_order):
        return

    st.markdown(f"### 案件資訊：案件編號 `{current_view_order.get('case_no') or pay_order_id}` - 客戶 **{current_view_order['client_name']}** (狀態: `{current_view_order['order_status']}`)")

    col_calc, col_input = st.columns(2)

    with col_calc:
        st.markdown("#### 📐 系統計算應收預估")
        st.write(f"- **樓層費**: {safe_int(current_view_order['floor_fee']):,} 元")
        st.write(f"- **預估訂金**: {safe_int(current_view_order['deposit_amount']):,} 元")
        st.write(f"- **首筆應收 (訂金+樓層)**: {safe_int(current_view_order['initial_payment_payable']):,} 元")
        st.write(f"- **第一期款**: {safe_int(current_view_order['first_payment_amount']):,} 元")
        st.write(f"- **第二期款**: {safe_int(current_view_order['second_payment_amount']):,} 元")
        st.write(f"- **雇主自費合計**: {safe_int(current_view_order['total_employer_self_pay_payable']):,} 元")
        st.write(f"- **應付月嫂薪資**: {safe_int(current_view_order['service_salary']):,} 元")

    with col_input:
        st.markdown("#### ✍️ 實收與轉帳欄位登錄")

        amount_receivable = st.number_input(
            "應收總金額 (系統自費總額)",
            value=safe_int(current_pay['amount_receivable']) if safe_int(current_pay['amount_receivable']) > 0 else safe_int(current_view_order['total_employer_self_pay_payable']),
            step=100,
            key="fin_amount_rec"
        )

        col_dep_val, col_dep_date = st.columns(2)
        with col_dep_val:
            deposit_received = st.number_input("已收訂金", value=safe_int(current_pay['deposit_received']), step=100, key="fin_dep_rec")
        with col_dep_date:
            deposit_received_at = st.date_input("訂金收取日期", value=safe_date(current_pay['deposit_received_at']), key="fin_dep_date")

        col_bal_val, col_bal_date = st.columns(2)
        with col_bal_val:
            balance_received = st.number_input("已收尾款", value=safe_int(current_pay['balance_received']), step=100, key="fin_bal_rec")
        with col_bal_date:
            balance_received_at = st.date_input("尾款收取日期", value=safe_date(current_pay['balance_received_at']), key="fin_bal_date")

        col_care_val, col_care_date = st.columns(2)
        with col_care_val:
            caregiver_fee = st.number_input(
                "實際付給月嫂費用",
                value=safe_int(current_pay['caregiver_fee']) if safe_int(current_pay['caregiver_fee']) > 0 else safe_int(current_view_order['service_salary']),
                step=100,
                key="fin_care_fee"
            )
        with col_care_date:
            caregiver_paid_at = st.date_input("月嫂轉帳日期", value=safe_date(current_pay['caregiver_paid_at']), key="fin_care_date")

        payment_status = st.selectbox(
            "帳務狀態",
            ["待收訂金", "已收訂金", "已收尾款", "已結案"],
            index=["待收訂金", "已收訂金", "已收尾款", "已結案"].index(current_pay['payment_status']),
            key="fin_status_select"
        )

        notes = st.text_area("對帳備註", value=current_pay['notes'] or "", key="fin_notes_area")

        if st.button("更新財務記錄", key="btn_update_finance"):
            try:
                db_service.update_payment_details(
                    order_id=pay_order_id,
                    amount_receivable=amount_receivable,
                    deposit_received=deposit_received,
                    balance_received=balance_received,
                    caregiver_fee=caregiver_fee,
                    payment_status=payment_status,
                    notes=notes,
                    deposit_received_at=deposit_received_at if deposit_received > 0 else None,
                    balance_received_at=balance_received_at if balance_received > 0 else None,
                    caregiver_paid_at=caregiver_paid_at if caregiver_fee > 0 else None
                )
                if payment_status == '已收訂金' and current_view_order['order_status'] == '洽談中':
                    db_service.update_order_status(pay_order_id, '訂單成立')
                    st.info("檢測到已收訂金，訂單狀態已自動標記為「訂單成立」！")
                st.success("財務資料更新成功！")
                st.rerun()
            except Exception as e:
                st.error(f"更新失敗: {e}")


def show():
    """殼層：讀取初始資料並分發至各 Tab 渲染函數 (OrderUI)"""
    st.title("📦 訂單與帳務管理系統")
    st.write("本系統串接了 `v_order_details` 整合計算檢視表，提供訂單生命週期、指派配對以及帳務實收狀態的管理。")

    try:
        orders_data = db_service.get_order_details()
        clients = db_service.get_table_data('clients')
        staff_list = db_service.get_table_data('staff')
    except Exception as e:
        st.error(f"初始化載入資料失敗: {e}")
        return

    tab1, tab2, tab3 = st.tabs(["📊 訂單總覽與計算對帳", "🤝 案件與配對中心", "💰 更新實收財務"])

    with tab1:
        _render_tab1_overview(orders_data)

    with tab2:
        _render_tab2_assign(orders_data, clients, staff_list)

    with tab3:
        _render_tab3_finance(orders_data)
