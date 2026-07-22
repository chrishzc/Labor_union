"""
================================================================================
檔案名稱: ui/pages/04_edit_order.py
功能說明: 單筆訂單 36 全欄位動態試算與資料維護專頁 (EditOrderUI - 響應式試算與持久化修復版)
專案名稱: Lobar Union - 服務人員與訂單管理系統
建立日期: 2026-07-03
修改日期: 2026-07-06 (修復即時連動與 full_details 資料庫持久化儲存)
================================================================================
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import math
import importlib
import os
import requests
from services import db_service
importlib.reload(db_service)

title = "📄 訂單動態試算與維護"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

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


def safe_optional_date(val):
    """將可為空的資料庫日期轉為 Streamlit 可接受的日期或 None。"""
    if not val:
        return None
    return safe_date(val)


def render_editor(target_case_no, orders_data, payments_raw, key_prefix="v25"):
    """
    可重用的單筆訂單編輯器渲染函式 (EditOrderUI Core)。
    抽出此函式是為了讓 02_orders.py 分頁一的手風琴展開面板可以直接
    內嵌呼叫同一套試算/編輯邏輯，不需要再跳轉頁面或重複維護程式碼。

    參數:
      target_case_no: 欲編輯案件的正式案件編號 (必須已由呼叫端選定，此函式不再提供下拉選單)
      orders_data: db_service.get_order_details() 的完整結果
      payments_raw: 保留相容性的空白帳務資料；舊 payments 已停用
      key_prefix: Streamlit widget key 前綴，避免同頁面內多個展開面板的 key 互相衝突
    """
    assert isinstance(orders_data, list)
    target_order = next((o for o in orders_data if o['case_no'] == target_case_no), None)
    if not target_order:
        st.warning("找不到此訂單資料，可能已被刪除或狀態已變更，請重新整理頁面。")
        return

    st.write("🔒 **公式欄位安全鎖定**")
    is_unlocked = st.checkbox("🔓 強制解鎖自訂衍生公式欄位", value=False, key=f"{key_prefix}_unlock_toggle_{target_case_no}")

    curr_p = next((p for p in payments_raw if p.get('case_no') == target_order.get('case_no')), {})

    # 若開啟解鎖，跳出警告 Alert (INV-EDIT-04)
    if is_unlocked:
        st.warning("⚠️ **警告：您已開啟強制解鎖自訂模式！** 手動覆寫總時數、完工日或期款金額後，系統原本的自動試算連動公式將部分失效，請務必確認與客戶合約金額相符後再行儲存。")
    else:
        st.caption("🔒 提示：衍生金額與完工日目前由系統自動連動試算 (唯讀鎖定)。如需特例強制修正，請點選右上角「🔓 強制解鎖」開關。")

    st.markdown("---")

    # =========================================================================
    # 區塊一：📌 案件基本與時程排定 (含預產期與休假方式)
    # =========================================================================
    with st.container(border=True):
        st.markdown(f"### 📌 一、案件基本與時程排定 (案件編號: `{target_case_no}`)")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            w_client_name = st.text_input("客戶名稱", value=target_order['client_name'], key=f"{key_prefix}_client_{target_case_no}")
            w_due_date = st.date_input("預產期", value=safe_date(target_order.get('due_date')), key=f"{key_prefix}_due_{target_case_no}")
            
            client_identity_status = target_order.get('identity_status') or '未設定'
            st.text_input(
                "身分資格（唯讀）",
                value=client_identity_status,
                disabled=True,
                key=f"{key_prefix}_identity_{target_case_no}",
                help="身分資格由客戶主檔管理；訂單編輯不可修改。",
            )
        
        with c2:
            w_staff_name = st.text_input("服務人員", value=target_order.get('staff_name') or '尚未指派', disabled=True, key=f"{key_prefix}_staff_{target_case_no}")
            s_mode_opts = ["週休1日", "週休2日", "連續服務"]
            c_mode = target_order.get('service_mode', '週休1日')
            # 休假方式以客戶申請資料 clients.service_type 為準，僅供本頁計算。
            # 此欄位不屬於 orders，不能顯示成可編輯卻未被儲存的選單。
            w_service_mode = c_mode if c_mode in s_mode_opts else '週休1日'
            st.text_input("休假方式 (客戶申請)", value=w_service_mode, disabled=True, key=f"{key_prefix}_mode_{target_case_no}")
            w_start_date = st.date_input("預期服務開始日", value=safe_date(target_order.get('start_date')), key=f"{key_prefix}_st_{target_case_no}")
        
        with c3:
            w_act_start = st.date_input("服務開始 (實際開工)", value=safe_optional_date(target_order.get('actual_start_date')), key=f"{key_prefix}_act_st_{target_case_no}")
            w_service_days = st.number_input("希望服務天數 (天)", value=max(1, safe_int(target_order.get('service_days', 20))), min_value=1, max_value=60, step=1, key=f"{key_prefix}_days_{target_case_no}")
            
            # 只有已確認實際開始日才計算實際結束日，避免預期日期或今天被寫回。
            calc_act_end = None
            if w_act_start:
                calc_out = db_service.calculate_attendance_schedule(
                    actual_start_date=w_act_start,
                    target_service_days=w_service_days,
                    service_mode=w_service_mode
                )
                calc_act_end = calc_out.get('actual_end_date', w_act_start + timedelta(days=w_service_days-1))
            
            if not is_unlocked:
                end_text = calc_act_end.strftime('%Y-%m-%d') if calc_act_end else '尚未設定實際服務開始日'
                st.markdown(f"• ⚡ **服務結束 (🔒 自動精算)**: <b style='color:#2E7D32;'>{end_text}</b>", unsafe_allow_html=True)
                w_act_end = calc_act_end
            else:
                w_act_end = st.date_input("服務結束 (🔓 自訂)", value=safe_optional_date(target_order.get('actual_end_date')) or calc_act_end, key=f"{key_prefix}_act_end_custom_{target_case_no}")

    # =========================================================================
    # 區塊二：⏱️ 服務時數與請款天數統計區
    # =========================================================================
    with st.container(border=True):
        st.markdown("### ⏱️ 二、服務時數與請款天數統計區")
        
        hc1, hc2, hc3 = st.columns(3)
        with hc1:
            w_hours_per_day = st.number_input("服務時段 (小時/天)", value=max(1, safe_int(target_order.get('service_hours_per_day', 9))), min_value=1, max_value=24, step=1, key=f"{key_prefix}_hrs_{target_case_no}")
            calc_total_hours = w_service_days * w_hours_per_day
            display_total_h = calc_total_hours if not is_unlocked else safe_int(target_order.get('total_hours', calc_total_hours))
            w_total_hours = st.number_input("總時數 (小時)", value=display_total_h, disabled=not is_unlocked, key=f"{key_prefix}_total_h_{target_case_no}_{display_total_h}")
        
        with hc2:
            default_sub_hrs = 40 if client_identity_status == '一般市民' else 0
            w_subsidy_hours = st.number_input("補助時數 (小時)", value=safe_int(target_order.get('subsidy_hours', default_sub_hrs)), min_value=0, step=1, key=f"{key_prefix}_sub_h_{target_case_no}")
            calc_self_pay_hours = max(0, w_total_hours - w_subsidy_hours)
            display_self_h = calc_self_pay_hours if not is_unlocked else safe_int(target_order.get('self_pay_hours', calc_self_pay_hours))
            w_self_pay_hours = st.number_input("自費時數 (小時)", value=display_self_h, disabled=not is_unlocked, key=f"{key_prefix}_self_h_{target_case_no}_{display_self_h}")
            
        with hc3:
            w_claim_total_days = st.number_input("請款總日數 (天)", value=max(1, safe_int(target_order.get('claim_total_days', w_service_days))), min_value=1, step=1, key=f"{key_prefix}_claim_d_{target_case_no}")

    # =========================================================================
    # 區塊三：💰 費用與期款拆解試算區 (Formula Lock Guardrail)
    # =========================================================================
    with st.container(border=True):
        st.markdown("### 💰 三、費用與期款拆解試算區")
        
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            w_floor_fee = st.number_input("樓層費用 (元)", value=safe_int(target_order.get('floor_fee', 0)), step=100, key=f"{key_prefix}_fl_{target_case_no}")
            w_employer_rate = st.number_input("雇主單價 (元/天)", value=safe_int(target_order.get('employer_hourly_rate', 2000)), step=100, key=f"{key_prefix}_emp_rate_{target_case_no}")
            
            calc_base_pay = w_service_days * w_employer_rate
            calc_total_self_pay = calc_base_pay + w_floor_fee
            display_total_self = calc_total_self_pay if not is_unlocked else safe_int(target_order.get('total_employer_self_pay_payable', calc_total_self_pay))
            w_total_self_pay = st.number_input("雇主自費合計金額 (元)", value=display_total_self, disabled=not is_unlocked, step=100, key=f"{key_prefix}_total_self_{target_case_no}_{display_total_self}")

        with mc2:
            w_deposit_days = st.number_input("訂金天數", value=max(1, safe_int(target_order.get('deposit_days', 1))), min_value=1, step=1, key=f"{key_prefix}_dep_d_{target_case_no}")
            calc_deposit_amt = w_deposit_days * w_employer_rate
            display_dep_amt = calc_deposit_amt if not is_unlocked else safe_int(target_order.get('deposit_amount', calc_deposit_amt))
            w_deposit_amt = st.number_input("訂金 (元)", value=display_dep_amt, disabled=not is_unlocked, step=100, key=f"{key_prefix}_dep_amt_{target_case_no}_{display_dep_amt}")
            w_dep_due_date = st.date_input(
                "訂金應收日期",
                value=safe_optional_date(curr_p.get('deposit_due_date') or target_order.get('deposit_date')),
                key=f"{key_prefix}_dep_due_date_{target_case_no}",
                help="公會人員手動填寫；未填時維持空白。",
            )

        with mc3:
            half_days = safe_int(w_service_days / 2)
            w_first_pay_days = st.number_input("第一期款天數", value=safe_int(target_order.get('first_payment_days', half_days)), step=1, key=f"{key_prefix}_p1_days_{target_case_no}")
            calc_first_pay_amt = w_first_pay_days * w_employer_rate
            display_first_pay = calc_first_pay_amt if not is_unlocked else safe_int(target_order.get('first_payment_amount', calc_first_pay_amt))
            w_first_pay_amt = st.number_input("第一期金額 (元)", value=display_first_pay, disabled=not is_unlocked, step=100, key=f"{key_prefix}_p1_amt_{target_case_no}_{display_first_pay}")
            w_first_pay_due_date = st.date_input("第一期款應收日期", value=safe_date(curr_p.get('first_payment_due_date') or target_order.get('first_payment_date')), key=f"{key_prefix}_p1_due_date_{target_case_no}")

        st.markdown("---")
        m2_c1, m2_c2 = st.columns(2)
        with m2_c1:
            w_second_pay_days = st.number_input("第二期款天數", value=safe_int(target_order.get('second_payment_days', w_service_days - w_first_pay_days)), step=1, key=f"{key_prefix}_p2_days_{target_case_no}")
            calc_second_pay_amt = w_total_self_pay - (w_deposit_amt + w_floor_fee) - w_first_pay_amt
            display_second_pay = calc_second_pay_amt if not is_unlocked else safe_int(target_order.get('second_payment_amount', calc_second_pay_amt))
            w_second_pay_amt = st.number_input("第二期金額 (元)", value=display_second_pay, disabled=not is_unlocked, step=100, key=f"{key_prefix}_p2_amt_{target_case_no}_{display_second_pay}")
        with m2_c2:
            w_second_pay_due_date = st.date_input("第二期款應收日期", value=safe_date(curr_p.get('second_payment_due_date') or target_order.get('second_payment_date')), key=f"{key_prefix}_p2_due_date_{target_case_no}")

    # =========================================================================
    # 區塊四：💵 服務人員薪資與市府請款區
    # =========================================================================
    with st.container(border=True):
        st.markdown("### 💵 四、服務人員薪資與市府請款區")
        
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            w_caregiver_rate = st.number_input("服務單價 (元/天)", value=safe_int(target_order.get('caregiver_rate', 2000)), step=100, key=f"{key_prefix}_care_rate_{target_case_no}")
            w_salary_1_date = st.date_input("預計發薪日", value=safe_date(target_order.get('salary_payment_date_1')), key=f"{key_prefix}_p1_pay_date_{target_case_no}")
        with sc2:
            st.number_input("服務薪資 (元)", value=safe_int(target_order.get('service_salary')), disabled=True, step=100, key=f"{key_prefix}_service_salary_{target_case_no}")
            calc_sub_salary = safe_int(round((w_subsidy_hours / max(1, w_hours_per_day)) * w_caregiver_rate))
            display_sub_salary = calc_sub_salary if not is_unlocked else safe_int(target_order.get('subsidy_salary', calc_sub_salary))
            w_subsidy_salary = st.number_input("補助薪資 (元)", value=display_sub_salary, disabled=not is_unlocked, step=100, key=f"{key_prefix}_sub_sal_{target_case_no}_{display_sub_salary}")
        with sc3:
            w_govt_claim = st.date_input("市府請款 (請款送件日)", value=safe_date(target_order.get('govt_claim_date')), key=f"{key_prefix}_govt_date_{target_case_no}")

    # =========================================================================
    # 區塊五：📝 實收對帳、狀態與備註登錄區
    # =========================================================================
    with st.container(border=True):
        st.markdown("### 📝 五、實收對帳、狀態與備註登錄區")
        
        # ponytail: Show the 14-digit virtual account corresponding to the current case
        va_val = db_service.generate_virtual_account(target_order.get('case_no'))
        if va_val:
            st.markdown(f"**🔗 專屬虛擬帳號**: `{va_val}`")

        rc1, rc2 = st.columns(2)
        with rc1:
            w_dep_rec = st.number_input("已收訂金 (元)", value=safe_int(curr_p.get('deposit_received')), step=100, key=f"{key_prefix}_dep_rec_{target_case_no}")
            w_dep_rec_date = st.date_input("訂金實收日期", value=safe_date(curr_p.get('deposit_received_at')), key=f"{key_prefix}_dep_rec_date_{target_case_no}")
            w_p1_rec = st.number_input("已收第一期款 (元)", value=safe_int(curr_p.get('first_payment_received')), step=100, key=f"{key_prefix}_p1_rec_{target_case_no}")
            w_p1_rec_date = st.date_input("第一期款收取日期", value=safe_date(curr_p.get('first_payment_received_at')), key=f"{key_prefix}_p1_rec_date_{target_case_no}")
            w_p2_rec = st.number_input("已收第二期款 (元)", value=safe_int(curr_p.get('second_payment_received')), step=100, key=f"{key_prefix}_p2_rec_{target_case_no}")
            w_p2_rec_date = st.date_input("第二期款收取日期", value=safe_date(curr_p.get('second_payment_received_at')), key=f"{key_prefix}_p2_rec_date_{target_case_no}")
            
            status_list = ["洽談中", "訂單成立", "服務中", "訂單完成", "訂單取消"]
            c_status = target_order['order_status']
            st_idx = status_list.index(c_status) if c_status in status_list else 0
            w_order_status = st.selectbox("訂單成立狀態", status_list, index=st_idx, key=f"{key_prefix}_status_{target_case_no}")
        
        with rc2:
            stage_receivable_total = w_deposit_amt + w_floor_fee + w_first_pay_amt + w_second_pay_amt
            stage_received_total = w_dep_rec + w_p1_rec + w_p2_rec
            st.metric("應收總額", f"{stage_receivable_total:,.0f} 元")
            st.metric("實收總額", f"{stage_received_total:,.0f} 元")
            w_notes = st.text_area("備註 (注意事項/備忘)", value=target_order.get('notes') or "", key=f"{key_prefix}_notes_{target_case_no}")
            w_cancel_reason = ""
            if w_order_status == "訂單取消":
                w_cancel_reason = st.text_area("取消原因 (選取訂單取消時強制填寫)", value=target_order.get('cancel_reason') or "", key=f"{key_prefix}_cancel_rea_{target_case_no}")

    st.markdown("---")
    st.markdown("### 🔄 訂單、月嫂指派與行事曆同步")
    st.caption("服務天數、日期或時數變更必須先預覽，再明確確認排班移除後套用；本頁不會直接寫入訂單、指派或帳務資料。")

    if w_order_status != target_order["order_status"]:
        st.warning("訂單狀態／取消流程不屬於本次排班同步；請先還原狀態後再套用同步變更。")
        return
    if not w_act_start or not w_act_end:
        st.warning("請先提供實際開工日與服務結束日，才能建立可驗證的同步計畫。")
        return

    def api_request(path, *, method="GET", payload=None):
        response = requests.request(
            method,
            f"{API_BASE_URL}{path}",
            json=payload,
            timeout=15,
        )
        try:
            body = response.json()
        except ValueError:
            body = {"detail": response.text}
        if not response.ok:
            raise ValueError(f"HTTP {response.status_code}: {body.get('detail') or body.get('message') or body}")
        if not body.get("success", False):
            raise ValueError(body.get("error") or body.get("message") or "同步 API 請求失敗")
        return body.get("data") or {}

    try:
        current_assignments = api_request(
            f"/api/v1/cases/{target_case_no}/assignment-schedules"
        ).get("assignments", [])
        staff_records = api_request("/api/v1/staff")
    except (requests.RequestException, ValueError) as error:
        st.error(f"無法讀取正式指派或服務人員：{error}")
        return

    staff_options = {"請明確選擇月嫂": None}
    for staff in staff_records:
        staff_id = staff.get("id")
        staff_name = staff.get("name")
        if isinstance(staff_id, int) and staff_name:
            staff_options[f"#{staff_id}｜{staff_name}"] = staff_id

    st.markdown("#### 完整正式服務指派計畫")
    st.caption("減少既有列會把未列出的正式指派列為取消候選；預覽會顯示其受影響日排班，套用前仍須明確確認。")
    assignment_count = st.number_input(
        "指派區段數", min_value=1, max_value=8,
        value=max(1, len(current_assignments)), step=1,
        key=f"{key_prefix}_assignment_count_{target_case_no}",
    )
    assignment_plan = []
    for index in range(assignment_count):
        current = current_assignments[index] if index < len(current_assignments) else {}
        current_staff_id = current.get("staff_id")
        labels = list(staff_options)
        selected_index = next(
            (position for position, label in enumerate(labels) if staff_options[label] == current_staff_id),
            0,
        )
        with st.container(border=True):
            left, middle, right = st.columns(3)
            with left:
                selected_label = st.selectbox(
                    f"第 {index + 1} 段月嫂", labels, index=selected_index,
                    key=f"{key_prefix}_assignment_staff_{target_case_no}_{index}",
                )
            with middle:
                assigned_start = st.date_input(
                    f"第 {index + 1} 段開始日",
                    value=safe_date(current.get("assigned_start_date") or w_act_start),
                    key=f"{key_prefix}_assignment_start_{target_case_no}_{index}",
                )
            with right:
                assigned_end = st.date_input(
                    f"第 {index + 1} 段結束日",
                    value=safe_date(current.get("assigned_end_date") or w_act_end),
                    key=f"{key_prefix}_assignment_end_{target_case_no}_{index}",
                )
        selected_staff_id = staff_options[selected_label]
        if selected_staff_id is not None:
            assignment_plan.append({
                "assignment_id": current.get("id"),
                "staff_id": selected_staff_id,
                "assignment_sequence": index + 1,
                "assigned_start_date": assigned_start.isoformat(),
                "assigned_end_date": assigned_end.isoformat(),
            })

    missing_staff_rows = assignment_count - len(assignment_plan)
    order_change = {
        "client_name": w_client_name,
        "service_days": int(w_service_days),
        "service_hours_per_day": int(w_hours_per_day),
        "floor_fee": int(w_floor_fee),
        "deposit_date": w_dep_due_date.isoformat() if w_dep_due_date else None,
        "start_date": w_start_date.isoformat(),
        "end_date": w_act_end.isoformat(),
        "actual_start_date": w_act_start.isoformat(),
        "actual_end_date": w_act_end.isoformat(),
    }
    preview_request = {"order_change": order_change, "assignment_plan": assignment_plan}
    preview_state_key = f"{key_prefix}_assignment_sync_preview_{target_case_no}"

    if st.button("🔍 預覽訂單與指派同步", key=f"{key_prefix}_assignment_sync_preview_button_{target_case_no}", type="primary"):
        if missing_staff_rows:
            st.error("每一個指派區段都必須明確選擇月嫂，不能使用預設或推測值。")
        else:
            try:
                preview = api_request(
                    f"/api/v1/orders/{target_case_no}/assignment-synchronization/preview",
                    method="POST", payload=preview_request,
                )
                st.session_state[preview_state_key] = {"request": preview_request, "preview": preview}
                st.rerun()
            except (requests.RequestException, ValueError) as error:
                st.error(f"同步預覽失敗：{error}")

    preview_state = st.session_state.get(preview_state_key)
    if not preview_state:
        return
    if preview_state["request"] != preview_request:
        st.info("訂單或指派計畫已變更；請重新執行同步預覽。")
        return

    preview = preview_state["preview"]
    st.markdown("#### 預覽結果")
    preview_left, preview_middle, preview_right = st.columns(3)
    preview_left.metric("目標時數", preview.get("target_hours", 0))
    preview_middle.metric("提議時數", preview.get("proposed_actual_hours", 0))
    preview_right.metric("差額", preview.get("difference", 0))
    if preview.get("blocking_reasons"):
        st.error(f"無法直接套用：{preview['blocking_reasons']}")
    required_removals = preview.get("required_schedule_removals", [])
    removal_options = {
        f"排班 #{item['schedule_id']}｜指派 #{item['assignment_id']}｜{item['work_date']}": item["schedule_id"]
        for item in required_removals
    }
    selected_removal_labels = st.multiselect(
        "明確確認要移除的日排班", list(removal_options),
        key=f"{key_prefix}_assignment_sync_removals_{target_case_no}",
    )
    selected_removal_ids = [removal_options[label] for label in selected_removal_labels]
    applied_by = st.text_input(
        "操作識別", key=f"{key_prefix}_assignment_sync_applied_by_{target_case_no}",
        help="請輸入實際執行確認的人員識別。",
    )
    confirmed = st.checkbox(
        "我已確認以上完整指派、時數差額與所有排班移除。",
        key=f"{key_prefix}_assignment_sync_confirm_{target_case_no}",
    )
    can_apply = preview.get("sync_status") == "in_sync"
    if st.button(
        "💾 確定儲存並套用同步", key=f"{key_prefix}_assignment_sync_apply_button_{target_case_no}",
        disabled=not can_apply,
    ):
        if set(selected_removal_ids) != {item["schedule_id"] for item in required_removals}:
            st.error("必須逐筆且完整確認預覽要求移除的日排班。")
        elif not confirmed:
            st.error("請先確認完整指派與排班移除計畫。")
        elif not applied_by.strip():
            st.error("操作識別不可空白。")
        else:
            try:
                api_request(
                    f"/api/v1/orders/{target_case_no}/assignment-synchronization/apply",
                    method="POST",
                    payload={
                        **preview_request,
                        "schedule_change_plan": {"remove_schedule_ids": selected_removal_ids},
                        "applied_by": applied_by.strip(),
                    },
                )
                st.session_state.pop(preview_state_key, None)
                st.success("訂單、正式指派與日排班已在同一交易中套用；行事曆重新開啟時會讀取最新正式排班。")
                st.rerun()
            except (requests.RequestException, ValueError) as error:
                st.error(f"同步套用失敗：{error}")


def show():
    """EditOrderUI 獨立頁面進入點 (自行下拉選單挑選訂單，再呼叫共用的 render_editor)"""
    st.title("📄 單筆訂單 36 欄位動態試算與維護單據")

    try:
        orders_data = db_service.get_order_details()
        payments_raw = []
    except Exception as e:
        st.error(f"讀取資料庫失敗: {e}")
        return

    if not orders_data:
        st.info("目前系統尚無任何訂單資料可供試算。")
        return

    order_opts = {
        f"案件 #{o['case_no']} - 客戶: {o['client_name']} [{o['order_status']}] (月嫂: {o.get('staff_name') or '尚未指派'})": o['case_no']
        for o in orders_data
    }
    selected_label = st.selectbox("🎯 選擇欲查看或試算的訂單", list(order_opts.keys()), key="guardrail_order_picker")
    target_case_no = order_opts[selected_label]

    render_editor(target_case_no, orders_data, payments_raw, key_prefix="v25")
