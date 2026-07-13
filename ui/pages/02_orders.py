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
    st.caption("💡 點選任一筆訂單標題列即可原地展開，進行 36 欄位編輯 (手風琴模式：同時只會展開一筆，點開其他筆會自動收合前一筆)；欄位內容與「📄 訂單動態試算與維護」頁面完全共用同一套邏輯，修改後請記得點擊「💾 確定儲存」按鈕。")

    df_filtered = df_filtered.copy()
    try:
        payments_raw = db_service.get_table_data('payments')
    except Exception as e:
        st.error(f"讀取財務帳務資料失敗，暫時無法展開編輯面板: {e}")
        return

    # 依篩選/搜尋後的結果排序，逐筆訂單以 expander 呈現 (取代原本 st.dataframe 的完整表格)
    filtered_order_ids = df_filtered['order_id'].tolist() if 'order_id' in df_filtered.columns else []
    ordered_rows = [o for oid in filtered_order_ids for o in orders_data if o['order_id'] == oid]

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
    # 搭配 session_state 記錄「目前展開中」的唯一訂單 ID，點別筆時前一筆會自動收合。
    ACCORDION_STATE_KEY = "tab1_accordion_open_order_id"
    if ACCORDION_STATE_KEY not in st.session_state:
        st.session_state[ACCORDION_STATE_KEY] = None

    currently_open_id = st.session_state[ACCORDION_STATE_KEY]

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
        oid = o['order_id']
        is_open = (currently_open_id == oid)

        row_label = (
            f"{'🔻' if is_open else '▶️'} 案件 #{o.get('case_no') or oid} ｜ {o['client_name']} ｜ "
            f"[{o['order_status']}] ｜ 月嫂: {o.get('staff_name') or '尚未指派'} ｜ "
            f"預期開始: {o.get('start_date') or '未定'} ｜ "
            f"天數: {safe_int(o.get('service_days'))} ｜ "
            f"雇主自費合計: {safe_int(o.get('total_employer_self_pay_payable')):,} 元"
        )

        if st.button(row_label, key=f"tab1_row_btn_{oid}"):
            st.session_state[ACCORDION_STATE_KEY] = None if is_open else oid
            st.rerun()

        # 展開內容緊接在這一列的按鈕之後渲染，下一輪 for 迴圈才會畫下一列的按鈕，
        # 因此視覺上內容會直接出現在被點選的那一列正下方，而不是整份清單的最後面。
        if is_open:
            with st.container(border=True):
                _edit_order_mod.render_editor(
                    target_oid=oid,
                    orders_data=orders_data,
                    payments_raw=payments_raw,
                    key_prefix=f"tab1_acc_{oid}"
                )


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
                    order_id=target_order_id,
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
                        match_id = db_service.create_or_get_match_record(target_order_id, sid)
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
                            match_id = db_service.create_or_get_match_record(target_order_id, sid)
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
                        db_service.assign_staff_to_order(target_order_id, final_staff_id)
                        st.success("錄用成功！訂單已成立並生成初始檔期記錄。")
                        st.rerun()
                    except Exception as err:
                        st.error(f"指派失敗: {err}")
            else:
                st.info("⚠️ 提示：需待至少一位月嫂回覆「願意接案」後，方可進行傳送履歷與定案指派。")

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
        f"案件 #{p['case_no']} - 客戶: {p['client_name']} [狀態: {p['payment_status']}]": p['case_no']
        for p in payments_raw if p.get('case_no')
    }

    if not pay_options:
        st.info("目前沒有關聯訂單的帳務紀錄。")
        return

    selected_pay_label = st.selectbox("選擇欲更新帳務的訂單", list(pay_options.keys()), key="fin_pay_picker")
    pay_case_no = pay_options[selected_pay_label]

    current_pay = next((p for p in payments_raw if p.get('case_no') == pay_case_no), None)
    current_view_order = next((o for o in orders_data if o.get('case_no') == pay_case_no), None)

    if not (current_pay and current_view_order):
        return

    st.markdown(f"### 案件資訊：案件編號 `{pay_case_no}` - 客戶 **{current_view_order['client_name']}** (狀態: `{current_view_order['order_status']}`)")

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
                    case_no=pay_case_no,
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
                    db_service.update_order_status(current_view_order['order_id'], '訂單成立')
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
