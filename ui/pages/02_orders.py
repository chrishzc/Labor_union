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
import os
import requests
from services import db_service
importlib.reload(db_service)

# 04_edit_order.py 檔名以數字開頭，無法用一般 import 語法載入，改用 importlib 動態載入
# 目的：重用其 render_editor() 共用編輯邏輯，讓分頁一的手風琴展開面板可直接內嵌顯示
_edit_order_mod = importlib.import_module("ui.pages.04_edit_order")
importlib.reload(_edit_order_mod)

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
    """Tab 1: 訂單資訊總覽 (OrderUI_Tab1_Overview)"""
    st.subheader("訂單資訊總覽")
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
    st.caption("💡 點選任一筆訂單標題列即可原地展開，進行 36 欄位編輯 (手風琴模式：同時只會展開一筆，點開其他筆會自動收合前一筆)；欄位內容與「📄 訂單動態試算與維護」頁面完全共用同一套邏輯，修改後請記得點擊「💾 確定儲存」按鈕。")

    df_filtered = df_filtered.copy()
    payments_raw = []

    # 依篩選/搜尋後的結果排序，逐筆訂單以 expander 呈現 (取代原本 st.dataframe 的完整表格)
    filtered_case_nos = df_filtered['case_no'].tolist() if 'case_no' in df_filtered.columns else []
    ordered_rows = [o for case_no in filtered_case_nos for o in orders_data if o['case_no'] == case_no]

    if not ordered_rows:
        st.info("沒有符合篩選/搜尋條件的訂單。")
        return

    # 手風琴核心邏輯說明 (重要限制)：
    # 1. st.expander 純粹是「畫面端」元件，使用者點開/收合它時瀏覽器不會通知 Python 端、
    #    也不會觸發 rerun，因此無法用它偵測「使用者剛剛點了哪一個」。
    # 2. st.radio 雖然能觸發 rerun，但它是「單一整塊」元件——所有選項畫在同一個 widget 裡，
    #    Streamlit 無法在某個選項中間插入其他內容，導致展開內容永遠只能出現在整份清單的最後面，
    #    無法緊接在被點選的那一列下方 (這正是前一版被使用者指出的問題)。
    # 為了做到「點哪一列，內容就緊接在那一列正下方展開」，改成逐列各自使用一個 st.button 作為
    # 該列的可點擊標題列 (按鈕點擊事件 Streamlit 能正確偵測並觸發 rerun)，
    # 並在該按鈕的下一行程式碼立刻判斷是否要渲染展開內容，
    # 如此展開內容自然會被畫在該列按鈕與下一列按鈕之間，而不是集中在清單最後。
    # 搭配 session_state 記錄「目前展開中」的唯一案件編號，點別筆時前一筆會自動收合。
    ACCORDION_STATE_KEY = "tab1_accordion_open_case_no"
    if ACCORDION_STATE_KEY not in st.session_state:
        st.session_state[ACCORDION_STATE_KEY] = None

    currently_open_case_no = st.session_state[ACCORDION_STATE_KEY]

    # 用 CSS 把按鈕外觀改造成一般清單列的橫條卡片樣式 (置左對齊、滿版寬度)，
    # 視覺上更接近可點擊的表格列，而不是預設置中的小按鈕。
    st.markdown(
        """
        <style>
        div[data-testid="stButton"] > button {
            width: 100%;
            text-align: left;
            justify-content: flex-start;
            border-radius: 6px;
            padding: 0.5rem 0.75rem;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    for o in ordered_rows:
        case_no = o['case_no']
        is_open = (currently_open_case_no == case_no)

        row_label = (
            f"{'🔻' if is_open else '▶️'} 案件 #{case_no} ｜ {o['client_name']} ｜ "
            f"[{o['order_status']}] ｜ 月嫂: {o.get('staff_name') or '尚未指派'} ｜ "
            f"預期開始: {o.get('start_date') or '未定'} ｜ "
            f"天數: {safe_int(o.get('service_days'))} ｜ "
            f"雇主自費合計: {safe_int(o.get('total_employer_self_pay_payable')):,} 元"
        )

        if st.button(row_label, key=f"tab1_row_btn_{case_no}"):
            st.session_state[ACCORDION_STATE_KEY] = None if is_open else case_no
            st.rerun()

        # 展開內容緊接在這一列的按鈕之後渲染，下一輪 for 迴圈才會畫下一列的按鈕，
        # 因此視覺上內容會直接出現在被點選的那一列正下方，而不是整份清單的最後面。
        if is_open:
            with st.container(border=True):
                _edit_order_mod.render_editor(
                    target_case_no=case_no,
                    orders_data=orders_data,
                    payments_raw=payments_raw,
                    key_prefix=f"tab1_acc_{case_no}"
                )


def _render_tab2_assign(orders_data, clients, staff_list):
    """Tab 2: 月嫂配對中心 (OrderUI_Tab2_MatchingCenter) - 僅處理「洽談中」待配對案件"""
    st.subheader("🤝 月嫂配對中心 (Clients, Orders & Matching)")
    
    pending_orders = [o for o in orders_data if o['order_status'] == '洽談中']

    if not pending_orders:
        st.info("目前系統沒有處於「洽談中」且待配對指派的案件。")
        return

    target_case_options = {
        f"案件 #{o['case_no']} - 客戶: {o['client_name']} ({o['subsidy_eligibility']}, {o['service_days']}天)": o['case_no']
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


def _render_legacy_mixed_payment_overview(orders_data):
    """Render a filterable payment overview; load transaction detail on demand."""
    st.subheader("帳務明細總覽")
    st.caption("先顯示全部案件的帳務摘要；展開並載入案件後，才會取得客戶與服務人員交易明細。")

    try:
        client_payments = _payment_api_request("/client-payments") or []
        staff_payments = _payment_api_request("/staff-payments") or []
    except requests.RequestException as err:
        st.error(f"讀取帳務總覽失敗：{err}")
        return

    orders_by_case = {
        str(order.get("case_no")): order
        for order in orders_data
        if order.get("case_no")
    }
    client_by_case = {
        str(payment.get("case_no")): payment
        for payment in client_payments
        if payment.get("case_no")
    }
    staff_by_case = {}
    for payment in staff_payments:
        case_no = str(payment.get("case_no") or "")
        if case_no:
            staff_by_case.setdefault(case_no, []).append(payment)

    case_numbers = sorted(set(orders_by_case) | set(client_by_case) | set(staff_by_case))
    if not case_numbers:
        st.info("目前沒有可顯示的案件。")
        return

    overview_rows = []
    for case_no in case_numbers:
        order = orders_by_case.get(case_no, {})
        client_payment = client_by_case.get(case_no, {})
        staff_rows = staff_by_case.get(case_no, [])
        client_receivable = sum(
            safe_float(client_payment.get(f"{stage}_receivable"))
            for stage in ("deposit", "first_payment", "second_payment")
        )
        client_received = sum(
            safe_float(client_payment.get(f"{stage}_received"))
            for stage in ("deposit", "first_payment", "second_payment")
        )
        staff_payable = sum(safe_float(row.get("total_payable")) for row in staff_rows)
        staff_paid = sum(safe_float(row.get("paid_amount")) for row in staff_rows)
        client_state = "尚未建立" if not client_payment else (
            "已收清" if client_received >= client_receivable else "待收款"
        )
        staff_state = "尚未建立" if not staff_rows else (
            "已付款" if staff_paid >= staff_payable else "待付款"
        )
        overview_rows.append({
            "案件編號": case_no,
            "訂單狀態": order.get("order_status") or order.get("status") or "—",
            "客戶應收總額": client_receivable,
            "客戶實收總額": client_received,
            "客戶未收餘額": client_receivable - client_received,
            "客戶付款狀態": client_state,
            "月嫂應付總額": staff_payable,
            "月嫂實付總額": staff_paid,
            "月嫂未付餘額": staff_payable - staff_paid,
            "月嫂付款狀態": staff_state,
        })

    overview_df = pd.DataFrame(overview_rows)
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        case_keyword = st.text_input("案件編號", key="payment_overview_case_filter").strip()
    with filter_col2:
        order_statuses = sorted(
            status for status in overview_df["訂單狀態"].dropna().unique() if status != "—"
        )
        selected_order_statuses = st.multiselect(
            "訂單狀態", order_statuses, key="payment_overview_order_status"
        )
    with filter_col3:
        payment_states = sorted(
            set(overview_df["客戶付款狀態"]) | set(overview_df["月嫂付款狀態"])
        )
        selected_payment_states = st.multiselect(
            "付款狀態", payment_states, key="payment_overview_payment_status"
        )

    filtered_df = overview_df.copy()
    if case_keyword:
        filtered_df = filtered_df[
            filtered_df["案件編號"].str.contains(case_keyword, case=False, na=False)
        ]
    if selected_order_statuses:
        filtered_df = filtered_df[filtered_df["訂單狀態"].isin(selected_order_statuses)]
    if selected_payment_states:
        filtered_df = filtered_df[
            filtered_df["客戶付款狀態"].isin(selected_payment_states)
            | filtered_df["月嫂付款狀態"].isin(selected_payment_states)
        ]

    st.caption(f"共 {len(filtered_df)} 筆案件")
    st.dataframe(filtered_df, width="stretch", hide_index=True)
    if filtered_df.empty:
        return

    selected_case_no = st.selectbox(
        "選擇案件查看明細",
        filtered_df["案件編號"].tolist(),
        key="payment_overview_selected_case",
    )
    with st.expander(f"案件 {selected_case_no} 帳務與交易明細", expanded=False):
        load_detail = st.button("載入／重新整理交易明細", key=f"load_payment_detail_{selected_case_no}")
        cache_key = f"payment_detail_{selected_case_no}"
        if load_detail:
            try:
                try:
                    client_payment = _payment_api_request(f"/client-payments/{selected_case_no}")
                except requests.HTTPError as err:
                    if err.response is None or err.response.status_code != 404:
                        raise
                    client_payment = None
                staff_detail = _payment_api_request(f"/staff-payments/{selected_case_no}") or []
            except requests.RequestException as err:
                st.error(f"讀取案件明細失敗：{err}")
                return
            st.session_state[cache_key] = (client_payment, staff_detail)

        detail = st.session_state.get(cache_key)
        if not detail:
            st.info("按下「載入／重新整理交易明細」後才會讀取交易紀錄。")
            return
        client_payment, staff_detail = detail
        client_tab, staff_tab = st.tabs(["客戶帳務與交易", "服務人員帳務與交易"])
        with client_tab:
            _render_client_payment_ledger(selected_case_no, client_payment)
        with staff_tab:
            _render_staff_payment_ledger(selected_case_no, staff_detail)


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
        client_rows.append({
            "案件編號": case_no,
            "訂單狀態": order_status_by_case.get(case_no, "—"),
            "訂金應收": safe_float(payment.get("deposit_receivable")),
            "訂金實收": safe_float(payment.get("deposit_received")),
            "訂金應收日": payment.get("deposit_due_date"),
            "訂金實收日": payment.get("deposit_received_at"),
            "第一期應收": safe_float(payment.get("first_payment_receivable")),
            "第一期實收": safe_float(payment.get("first_payment_received")),
            "第一期應收日": payment.get("first_payment_due_date"),
            "第一期實收日": payment.get("first_payment_received_at"),
            "第二期應收": safe_float(payment.get("second_payment_receivable")),
            "第二期實收": safe_float(payment.get("second_payment_received")),
            "第二期應收日": payment.get("second_payment_due_date"),
            "第二期實收日": payment.get("second_payment_received_at"),
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
        client_states = sorted(client_df["付款狀態"].dropna().unique()) if not client_df.empty else []
        selected_client_states = st.multiselect("客戶付款狀態", client_states, key="client_payment_state_filter")
        if selected_client_states:
            client_df = client_df[client_df["付款狀態"].isin(selected_client_states)]
        st.caption(f"共 {len(client_df)} 筆客戶帳務")
        st.dataframe(client_df, width="stretch", hide_index=True)
    with staff_tab:
        staff_df = pd.DataFrame(staff_rows)
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


def _payment_api_request(path, method="GET", payload=None):
    """Access payment ledgers only through FastAPI; never write summary columns directly."""
    base_url = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
    response = requests.request(
        method,
        f"{base_url}/api/v1{path}",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("data")


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
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    subsidy_return = safe_float(payment.get("subsidy_return_receivable"))
    if subsidy_return:
        st.markdown("#### 退還補助款")
        st.dataframe(pd.DataFrame([{
            "應退金額": subsidy_return,
            "已退金額": safe_float(payment.get("subsidy_return_refunded")),
            "應退日期": payment.get("subsidy_return_due_date"),
            "退還日期": payment.get("subsidy_return_at"),
        }]), width="stretch", hide_index=True)

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
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

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


def _finance_report_request(path, params=None, download=False):
    """Read finance reports exclusively through the FastAPI router."""
    base_url = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
    response = requests.get(
        f"{base_url}/api/v1/finance-reports{path}",
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.content if download else (response.json().get("data") or {})


def _render_tab4_accounts_payable():
    """唯讀查詢指定月份的應付帳款，並提供銀行匯款 Excel。"""
    st.subheader("應付帳款查詢／輸出")
    st.caption("本頁僅供查詢與下載，不會將任何帳款標記為已付款、已退款或已提交。")

    today = datetime.today()
    year_col, month_col = st.columns(2)
    with year_col:
        selected_year = st.selectbox("年份", list(range(today.year - 2, today.year + 3)), index=2, key="accounts_payable_year")
    with month_col:
        selected_month = st.selectbox("月份", list(range(1, 13)), index=today.month - 1, format_func=lambda month: f"{month:02d} 月", key="accounts_payable_month")
    target_month = f"{selected_year:04d}-{selected_month:02d}"
    try:
        preview = _finance_report_request("/accounts-payable", {"target_month": target_month})
    except requests.RequestException as err:
        st.error(f"讀取 {target_month} 應付帳款失敗：{err}")
        return
    fixed_columns = ["月份-銀行代碼-流水號", "銀行名稱", "客戶or服務人員姓名", "銀行帳號", "銀行代號(碼)", "金額", "身分證字號(匯款到永豐才要填)", "案件編號", "匯款日期"]
    preview_df = pd.DataFrame(preview.get("payable_rows") or []).reindex(columns=fixed_columns)
    bank_totals = preview.get("bank_totals") or {}
    total_col1, total_col2 = st.columns(2)
    total_col1.metric("永豐銀行月嫂款（31）", f"{safe_float(bank_totals.get('31', 0)):,.0f} 元")
    total_col2.metric("台新銀行退還補助款（633）", f"{safe_float(bank_totals.get('633', 0)):,.0f} 元")
    st.write(f"共 {len(preview_df)} 筆待匯款項")
    st.dataframe(preview_df, width="stretch", hide_index=True)
    try:
        xlsx_bytes = _finance_report_request("/accounts-payable/export", {"target_month": target_month}, download=True)
    except requests.RequestException as err:
        st.error(f"下載應付帳款 Excel 失敗：{err}")
        return
    st.download_button("下載應付帳款 Excel", data=xlsx_bytes, file_name=f"應付帳款_{target_month}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="download_accounts_payable_xlsx")


def _render_tab5_subsidy_reconciliation():
    """Render read-only quarterly subsidy registers and annual summaries."""
    st.subheader("核銷補助清冊")

    today = datetime.today()
    selected_year = st.selectbox("申請年度", list(range(today.year - 2, today.year + 3)), index=2, key="subsidy_reconciliation_year")
    quarterly_tab, annual_tab = st.tabs(["分季核銷", "年度總表"])
    with quarterly_tab:
        selected_quarter = st.selectbox("申請季度", [1, 2, 3, 4], format_func=lambda quarter: f"第 {quarter} 季", key="subsidy_reconciliation_quarter")
        params = {"application_year": selected_year, "quarter": selected_quarter}
        try:
            report = _finance_report_request("/subsidy-reconciliation/quarterly", params)
        except requests.RequestException as err:
            st.error(f"讀取季度核銷清冊失敗：{err}")
        else:
            st.markdown("#### 一般市民")
            st.dataframe(pd.DataFrame(report.get("general_citizen_rows") or []), width="stretch", hide_index=True)
            subsidized_rows = report.get("subsidized_citizen_rows") or []
            if subsidized_rows:
                st.markdown("#### 補助市民")
                st.dataframe(pd.DataFrame(subsidized_rows), width="stretch", hide_index=True)
            try:
                xlsx_bytes = _finance_report_request("/subsidy-reconciliation/quarterly/export", params, download=True)
            except requests.RequestException as err:
                st.error(f"下載分季核銷 Excel 失敗：{err}")
            else:
                st.download_button("下載分季核銷 Excel", data=xlsx_bytes, file_name=f"核銷補助清冊_{selected_year}_Q{selected_quarter}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="download_quarterly_subsidy_reconciliation")
    with annual_tab:
        params = {"application_year": selected_year}
        try:
            report = _finance_report_request("/subsidy-reconciliation/annual", params)
        except requests.RequestException as err:
            st.error(f"讀取年度補助總表失敗：{err}")
        else:
            st.markdown("#### 一般市民")
            st.dataframe(pd.DataFrame(report.get("general_citizen_rows") or []), width="stretch", hide_index=True)
            subsidized_rows = report.get("subsidized_citizen_rows") or []
            if subsidized_rows:
                st.markdown("#### 補助市民")
                st.dataframe(pd.DataFrame(subsidized_rows), width="stretch", hide_index=True)
            try:
                xlsx_bytes = _finance_report_request("/subsidy-reconciliation/annual/export", params, download=True)
            except requests.RequestException as err:
                st.error(f"下載年度補助 Excel 失敗：{err}")
            else:
                st.download_button("下載年度補助 Excel", data=xlsx_bytes, file_name=f"年度補助總表_{selected_year}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="download_annual_subsidy_summary")
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

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 訂單資訊總覽",
        "🤝 月嫂配對中心",
        "💰 訂單帳務總覽",
        "📤 應付帳款查詢/輸出",
        "核銷補助清冊",
    ])

    with tab1:
        _render_tab1_overview(orders_data)

    with tab2:
        _render_tab2_assign(orders_data, clients, staff_list)

    with tab3:
        _render_tab3_finance(orders_data)

    with tab4:
        _render_tab4_accounts_payable()

    with tab5:
        _render_tab5_subsidy_reconciliation()
