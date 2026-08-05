"""
================================================================================
檔案名稱: ui/pages/order/tab2_assign.py
功能說明: Tab 2 月嫂配對中心 REST API 遷移版 (OrderUI_Tab2_Assign)
================================================================================
"""

import os
from datetime import date, datetime, timedelta
import requests
import streamlit as st
from ui.pages.order.editor import explain_assignment_sync_preview
from ui.pages.order.shared import safe_int

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


def _api_request(path, *, method="GET", payload=None):
    response = requests.request(
        method,
        f"{API_BASE_URL}{path}",
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


def _build_sync_request(order):
    service_days = int(safe_int(order.get("service_days")))
    if service_days <= 0:
        raise ValueError("服務天數必須為正整數")

    service_hours_per_day = float(order.get("service_hours_per_day", 0) or 0)
    if service_hours_per_day <= 0:
        raise ValueError("每小時時數必須大於 0")

    floor_fee = safe_int(order.get("floor_fee"))
    if floor_fee < 0:
        raise ValueError("樓層費不可為負")

    start_date = _iso_date_text(order.get("actual_start_date"), required=False, field_name="實際開始日")
    if start_date is None:
        start_date = _iso_date_text(order.get("start_date"), required=True, field_name="開始日")
    end_date = _iso_date_text(order.get("end_date"), required=False, field_name="結束日")
    if end_date is None and service_days:
        end_date = (datetime.strptime(start_date, "%Y-%m-%d").date() + timedelta(days=service_days - 1)).isoformat()

    actual_start_date = _iso_date_text(order.get("actual_start_date"), required=False, field_name="實際開始日")
    if actual_start_date is None:
        actual_start_date = start_date
    actual_end_date = _iso_date_text(order.get("actual_end_date"), required=False, field_name="實際結束日")
    if actual_end_date is None:
        actual_end_date = end_date

    return {
        "client_name": order.get("client_name") or "",
        "service_days": service_days,
        "service_hours_per_day": service_hours_per_day,
        "floor_fee": floor_fee,
        "deposit_date": _iso_date_text(order.get("deposit_date"), required=False, field_name="訂金日期"),
        "start_date": start_date,
        "end_date": end_date,
        "actual_start_date": actual_start_date,
        "actual_end_date": actual_end_date,
    }


def _render_identity_status_guard(target_order):
    identity_status = str(target_order.get("identity_status") or "").strip()
    if identity_status in {"一般市民", "補助市民", "非市民"}:
        return True

    client_id = target_order.get("client_id")
    st.warning("此案件尚未設定客戶身分資格，需先補齊後才能預覽指派同步。")
    selected_identity = st.selectbox(
        "客戶身分資格",
        ["一般市民", "補助市民", "非市民"],
        key=f"identity_status_fix_{target_order.get('case_no')}",
    )
    if st.button(
        "儲存身分資格",
        key=f"identity_status_save_{target_order.get('case_no')}",
    ):
        if not client_id:
            st.error("此案件缺少客戶識別，無法更新身分資格。")
        else:
            try:
                _api_request(
                    f"/api/v1/clients/{client_id}/identity-status",
                    method="PUT",
                    payload={"identity_status": selected_identity},
                )
                st.success("已更新客戶身分資格，請重新整理後再預覽指派同步。")
                st.rerun()
            except ValueError as err:
                st.error(f"儲存身分資格失敗：{err}")
    return False


def _render_line_matching_workflow(target_case_no, staff_list, match_records):
    st.markdown("##### LINE 媒合作業")
    if not staff_list:
        st.info("目前沒有可選月嫂。")
        return

    staff_options = {
        f"{s.get('name') or '未命名月嫂'}｜ID {s.get('id')}｜{s.get('phone') or '無電話'}": s
        for s in staff_list
        if s.get("id")
    }
    selected_staff_label = st.selectbox(
        "選擇月嫂",
        list(staff_options.keys()),
        key=f"line_staff_{target_case_no}",
    )
    selected_staff = staff_options[selected_staff_label]
    selected_staff_id = int(selected_staff["id"])

    default_staff_uid = str(selected_staff.get("line_user_id") or "").strip()
    existing_client_uid = ""
    try:
        order_detail = _api_request(f"/api/v1/orders/{target_case_no}")
        existing_client_uid = str(order_detail.get("line_user_id") or "").strip()
    except ValueError:
        order_detail = {}

    col_client, col_staff = st.columns(2)
    with col_client:
        client_uid = st.text_input(
            "客戶 LINE userId",
            value=existing_client_uid,
            placeholder="U 開頭的 LINE userId",
            key=f"line_client_uid_{target_case_no}",
        ).strip()
    with col_staff:
        staff_uid = st.text_input(
            "月嫂 LINE userId",
            value=default_staff_uid,
            placeholder="U 開頭的 LINE userId",
            key=f"line_staff_uid_{target_case_no}",
        ).strip()

    existing_match = next(
        (
            m for m in match_records
            if int(m.get("staff_id") or 0) == selected_staff_id
        ),
        None,
    )
    if existing_match:
        match_id = existing_match.get("match_id") or existing_match.get("id")
        acc = existing_match.get("caregiver_accepted")
        status = "願意接案" if acc == 1 else ("拒絕接案" if acc == 0 else "待回覆")
        st.info(f"媒合紀錄：#{match_id}，月嫂回覆：{status}")
    else:
        match_id = None
        st.info("尚未建立此月嫂的媒合紀錄。")

    bind_col, invite_col = st.columns(2)
    if bind_col.button("儲存 LINE 身分綁定", key=f"line_bind_{target_case_no}", use_container_width=True):
        if not client_uid or not staff_uid:
            st.error("請填入客戶與月嫂的 LINE userId。")
        else:
            try:
                _api_request(
                    f"/api/v1/orders/{target_case_no}/line-bindings",
                    method="POST",
                    payload={
                        "client_line_user_id": client_uid,
                        "staff_id": selected_staff_id,
                        "staff_line_user_id": staff_uid,
                    },
                )
                st.success("已儲存 LINE 身分綁定。")
                st.rerun()
            except ValueError as err:
                st.error(f"儲存失敗：{err}")

    if invite_col.button("發送接案邀請給月嫂", key=f"send_order_{target_case_no}", use_container_width=True):
        try:
            if match_id is None:
                created = _api_request(
                    f"/api/v1/orders/{target_case_no}/matches",
                    method="POST",
                    payload={"staff_id": selected_staff_id},
                )
                match_id = created.get("match_id") if isinstance(created, dict) else created
            _api_request(f"/api/v1/matches/{match_id}/send-info-1", method="POST")
            st.success("已建立接案邀請，系統將發送 LINE 給月嫂。")
            st.rerun()
        except ValueError as err:
            st.error(f"發送失敗：{err}")

    st.markdown("###### 月嫂回覆登錄")
    response_options = {"待回覆": None, "願意接案": True, "拒絕接案": False}
    response_index = 0
    if existing_match and existing_match.get("caregiver_accepted") == 1:
        response_index = 1
    elif existing_match and existing_match.get("caregiver_accepted") == 0:
        response_index = 2
    selected_response = st.radio(
        "回覆狀態",
        list(response_options.keys()),
        index=response_index,
        horizontal=True,
        key=f"caregiver_response_{target_case_no}_{selected_staff_id}",
    )
    response_col, resume_col = st.columns(2)
    if response_col.button(
        "更新月嫂回覆",
        key=f"update_response_{target_case_no}",
        disabled=match_id is None,
        use_container_width=True,
    ):
        try:
            _api_request(
                f"/api/v1/matches/{match_id}/reply",
                method="PUT",
                payload={"accepted": response_options[selected_response]},
            )
            st.success("已更新月嫂回覆。")
            st.rerun()
        except ValueError as err:
            st.error(f"更新失敗：{err}")

    can_send_resume = match_id is not None and existing_match and existing_match.get("caregiver_accepted") == 1
    if resume_col.button(
        "發送履歷給客戶",
        key=f"send_resume_{target_case_no}",
        disabled=not can_send_resume,
        use_container_width=True,
    ):
        try:
            _api_request(f"/api/v1/matches/{match_id}/send-resume", method="POST")
            st.success("已建立履歷推薦，系統將發送 LINE 給客戶。")
            st.rerun()
        except ValueError as err:
            st.error(f"發送失敗：{err}")


def _render_tab2_assign(orders_data, clients, staff_list):
    """Tab 2: 月嫂配對中心 (OrderUI_Tab2_MatchingCenter) - 僅處理「洽談中」待配對案件"""
    st.subheader("月嫂媒合與指派")
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

    st.markdown("### 待媒合案件")
    selected_case_label = st.selectbox("選擇案件", list(target_case_options.keys()), key="tab2_case_picker")
    target_case_no = target_case_options[selected_case_label]
    target_order = next((o for o in pending_orders if o['case_no'] == target_case_no), None)

    if not target_order:
        return

    # 單筆案件 3 大子選單標籤
    sub_tab1, sub_tab2, sub_tab3 = st.tabs(["案件資訊", "媒合與通知", "取消訂單"])

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
        st.markdown(f"#### 媒合與通知 (案件 #{target_case_no})")
        try:
            resp_m = requests.get(f"{API_BASE_URL}/api/v1/orders/{target_case_no}/matches", timeout=10)
            resp_m.raise_for_status()
            match_records = resp_m.json().get("data") or []
        except Exception as e:
            st.error(f"❌ 讀取媒合記錄 API 失敗: {e}")
            match_records = []

        _render_line_matching_workflow(target_case_no, staff_list, match_records)
        st.markdown("---")

        # 僅顯示至少有一項發送紀錄或意願已更新的媒合紀錄
        valid_matches = [
            m for m in match_records
            if m.get('sent_info_1_at') or m.get('sent_info_2_at') or m.get('caregiver_accepted') is not None
        ]
        if valid_matches:
            st.write("目前媒合紀錄")
            for m in valid_matches:
                acc = m.get('caregiver_accepted')
                acc_lbl = "🟢 願意接案" if acc == 1 else ("🔴 拒絕" if acc == 0 else "🟡 待回覆")
                s1_val = m.get('sent_info_1_at')
                s2_val = m.get('sent_info_2_at')
                s1 = f"已於 {s1_val}" if s1_val else "未發送"
                s2 = f"已於 {s2_val}" if s2_val else "未發送"
                st.markdown(f"**{m.get('staff_name', '月嫂')}** - 回覆：`{acc_lbl}`（接案邀請：{s1}｜補充通知：{s2}）")
            st.markdown("---")

        if not staff_list:
            st.warning("請先在服務人員資料表中建立服務人員。")
        else:
            with st.expander("月嫂篩選條件", expanded=False):
                fc1, fc2 = st.columns(2)
                with fc1:
                    f_region = st.checkbox("服務區域符合", value=True, key="f_reg_toggle")
                    f_schedule = st.checkbox("檔期可配合", value=True, key="f_sch_toggle")
                with fc2:
                    f_babies = st.checkbox("照護胎數符合", value=True, key="f_bab_toggle")
                    f_time = st.checkbox("服務時段符合", value=True, key="f_time_toggle")

            try:
                resp_rec = requests.get(
                    f"{API_BASE_URL}/api/v1/matches/recommend-staff",
                    params={
                        "case_no": target_case_no,
                        "filter_region": f_region,
                        "filter_schedule": f_schedule,
                        "filter_babies": f_babies,
                        "filter_time": f_time,
                    },
                    timeout=10,
                )
                resp_rec.raise_for_status()
                rec_staff = resp_rec.json().get("data") or []
            except Exception as err:
                st.error(f"讀取推薦月嫂失敗：{err}")
                rec_staff = []

            if not rec_staff:
                st.warning("依據目前條件，暫無符合的月嫂。可放寬篩選條件後再確認。")
                staff_options = {f"{s['name']} ({s['phone']})": s['id'] for s in staff_list if s.get('name')}
            else:
                staff_options = {r['display_label']: r['staff_id'] for r in rec_staff}

            # ---------------------------------------------------------------
            # 步驟 1：粗篩發送 (多選)
            # ---------------------------------------------------------------
            st.markdown("##### 批次發送接案邀請")
            selected_staff_labels = st.multiselect(
                "選擇月嫂",
                list(staff_options.keys()),
                key="match_staff_multipicker"
            )
            selected_staff_ids = [staff_options[label] for label in selected_staff_labels]

            if st.button("發送接案邀請", key="btn_send_1_batch", disabled=not selected_staff_ids):
                try:
                    for sid in selected_staff_ids:
                        resp_post = requests.post(
                            f"{API_BASE_URL}/api/v1/orders/{target_case_no}/matches",
                            json={"staff_id": sid},
                            timeout=10,
                        )
                        resp_post.raise_for_status()
                        m_data = resp_post.json().get("data") or {}
                        match_id = m_data.get("match_id") if isinstance(m_data, dict) else m_data
                        if match_id:
                            resp_s1 = requests.post(f"{API_BASE_URL}/api/v1/matches/{match_id}/send-info-1", timeout=10)
                            resp_s1.raise_for_status()
                    st.success(f"已對 {len(selected_staff_ids)} 位月嫂發送接案邀請。")
                    st.rerun()
                except Exception as e:
                    st.error(f"發送失敗：{e}")

            st.markdown("---")

            # ---------------------------------------------------------------
            # 步驟 2：意願狀態更新 ＆ 發送 訂單資訊-2
            # ---------------------------------------------------------------
            sent1_matches = [m for m in match_records if m.get('sent_info_1_at')]

            st.markdown("##### 回覆管理與補充通知")

            if not sent1_matches:
                st.info("尚未發送接案邀請。")
            else:
                resp_opts = ["待回覆", "願意接案", "拒絕接案"]
                staff_ids_for_step2 = []

                for m in sent1_matches:
                    m_staff_id = m['staff_id']
                    acc_val = m.get('caregiver_accepted')
                    c_idx = 1 if acc_val == 1 else (2 if acc_val == 0 else 0)

                    col_name, col_resp, col_chk = st.columns([2, 2, 1.2])
                    with col_name:
                        s2_val = m.get('sent_info_2_at')
                        s2_lbl = f"補充通知已於 {s2_val}" if s2_val else "尚未發送補充通知"
                        st.write(f"**{m.get('staff_name', '月嫂')}**\n\n({s2_lbl})")
                    with col_resp:
                        new_resp = st.selectbox(
                            "意願狀態", resp_opts, index=c_idx,
                            key=f"resp_select_{m['match_id'] if 'match_id' in m else m.get('id')}", label_visibility="collapsed"
                        )
                        new_accepted_val = True if new_resp == "願意接案" else (False if new_resp == "拒絕接案" else None)
                        if new_accepted_val != (True if acc_val == 1 else (False if acc_val == 0 else None)):
                            try:
                                m_id = m.get('match_id') or m.get('id')
                                resp_rep = requests.put(
                                    f"{API_BASE_URL}/api/v1/matches/{m_id}/reply",
                                    json={"accepted": new_accepted_val},
                                    timeout=10,
                                )
                                resp_rep.raise_for_status()
                                st.rerun()
                            except Exception as e:
                                st.error(f"回覆更新失敗：{e}")
                    with col_chk:
                        m_id = m.get('match_id') or m.get('id')
                        checked = st.checkbox("補充通知", key=f"send2_chk_{m_id}")
                        if checked:
                            staff_ids_for_step2.append(m_staff_id)

                if st.button("發送補充通知", key="btn_send_2_batch", disabled=not staff_ids_for_step2):
                    try:
                        for sid in staff_ids_for_step2:
                            resp_post = requests.post(
                                f"{API_BASE_URL}/api/v1/orders/{target_case_no}/matches",
                                json={"staff_id": sid},
                                timeout=10,
                            )
                            resp_post.raise_for_status()
                            m_data = resp_post.json().get("data") or {}
                            match_id = m_data.get("match_id") if isinstance(m_data, dict) else m_data
                            if match_id:
                                resp_s2 = requests.post(f"{API_BASE_URL}/api/v1/matches/{match_id}/send-info-2", timeout=10)
                                resp_s2.raise_for_status()
                        st.success(f"已對 {len(staff_ids_for_step2)} 位月嫂發送補充通知。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"發送失敗：{e}")

            st.markdown("---")
            st.markdown("##### 客戶推薦與正式指派")
            can_continue_assignment = _render_identity_status_guard(target_order)

            accepted_matches = [m for m in match_records if m.get('caregiver_accepted') == 1]
            if not can_continue_assignment:
                st.info("補齊身分資格後即可繼續推薦履歷與正式指派。")
            elif not accepted_matches:
                st.info("需至少一位月嫂回覆願意接案，才能推薦履歷給客戶。")
            else:
                final_options = {}
                for index, match in enumerate(accepted_matches):
                    staff_name = match.get('staff_name', '月嫂')
                    match_id = match.get('match_id') or match.get('id')
                    final_options[f"{index + 1}. {staff_name} (match #{match_id})"] = match

                final_match_label = st.selectbox(
                    "選擇願意接案的月嫂",
                    list(final_options.keys()),
                    key=f"final_match_picker_{target_case_no}",
                )
                final_match = final_options[final_match_label]
                final_staff_id = final_match.get('staff_id')
                final_match_id = final_match.get('match_id') or final_match.get('id')

                if not isinstance(final_staff_id, int) or final_staff_id <= 0:
                    st.error("✅ 擷取到無效的月嫂識別，請重新整理後再試。")
                elif final_match_id is None:
                    st.error("⚠️ 找不到對應配對紀錄 id，無法傳送履歷。")
                else:
                    st.success(f"已選定月嫂：{final_match.get('staff_name', '月嫂')}")

                    if st.button("發送履歷給客戶", key=f"btn_send_resume_{target_case_no}"):
                        try:
                            _api_request(
                                f"/api/v1/matches/{final_match_id}/send-resume",
                                method="POST",
                            )
                            st.success("履歷已傳送到客戶 LINE，等待回饋。")
                        except (requests.RequestException, ValueError) as err:
                            st.error(f"傳送履歷失敗：{err}")

                    preview_state_key = f"tab2_assignment_sync_preview_{target_case_no}"
                    if st.button(
                        "預覽指派同步",
                        key=f"btn_sync_preview_{target_case_no}",
                    ):
                        try:
                            order_change = _build_sync_request(target_order)
                            assignment_plan = [{
                                "assignment_id": None,
                                "staff_id": final_staff_id,
                                "assignment_sequence": 1,
                                "assigned_start_date": order_change["actual_start_date"],
                                "assigned_end_date": order_change["actual_end_date"],
                            }]
                            preview_request = {"order_change": order_change, "assignment_plan": assignment_plan}
                            sync_preview = _api_request(
                                f"/api/v1/orders/{target_case_no}/assignment-synchronization/preview",
                                method="POST",
                                payload=preview_request,
                            )
                            st.session_state[preview_state_key] = {
                                "request": preview_request,
                                "preview": sync_preview,
                                "match_id": final_match_id,
                                "match_label": final_match_label,
                            }
                            st.rerun()
                        except (requests.RequestException, ValueError) as err:
                            st.error(f"同步預覽失敗：{err}")

                    sync_state = st.session_state.get(preview_state_key)
                    if not sync_state:
                        st.info("請先點擊「預覽指派同步」查看結果。")
                    elif sync_state.get("match_label") != final_match_label:
                        st.info("⚠️ 已切換候選月嫂，請重新進行步驟 4 預覽。")
                    else:
                        preview_request = sync_state["request"]
                        sync_preview = sync_state["preview"]

                        st.markdown("#### 同步預覽結果")
                        c1, c2, c3 = st.columns(3)
                        c1.metric("目標時數", sync_preview.get("target_hours", 0))
                        c2.metric("提議時數", sync_preview.get("proposed_actual_hours", 0))
                        c3.metric("差額", sync_preview.get("difference", 0))

                        explain_assignment_sync_preview(sync_preview)

                        required_removals = sync_preview.get("required_schedule_removals", [])
                        removal_options = {
                            f"排班 #{item['schedule_id']}｜指派 #{item['assignment_id']}｜{item['work_date']}": item["schedule_id"]
                            for item in required_removals
                        }
                        selected_removal_labels = st.multiselect(
                            "逐筆確認要移除的原始日排班",
                            list(removal_options.keys()),
                            key=f"remove_schedule_{target_case_no}",
                        )
                        selected_removal_ids = [removal_options[label] for label in selected_removal_labels]
                        applied_by = st.text_input(
                            "操作識別（人員）",
                            key=f"assignment_sync_applied_by_{target_case_no}",
                            help="請輸入實際執行同步套用的識別。",
                        )
                        confirmed = st.checkbox(
                            "我已確認同步預覽結果、差額與排班移除項目。",
                            key=f"assignment_sync_confirm_{target_case_no}",
                        )

                        if st.button(
                            "套用正式指派",
                            key=f"btn_sync_apply_{target_case_no}",
                            disabled=sync_preview.get("sync_status") != "in_sync",
                        ):
                            if set(selected_removal_ids) != {item["schedule_id"] for item in required_removals}:
                                st.error("請完整勾選預覽要求移除的所有日排班。")
                            elif not confirmed:
                                st.error("請先勾選完整確認條件。")
                            elif not applied_by.strip():
                                st.error("請填寫操作識別。")
                            else:
                                try:
                                    _api_request(
                                        f"/api/v1/orders/{target_case_no}/assignment-synchronization/apply",
                                        method="POST",
                                        payload={
                                            **preview_request,
                                            "schedule_change_plan": {"remove_schedule_ids": selected_removal_ids},
                                            "applied_by": applied_by.strip(),
                                        },
                                    )
                                    st.session_state.pop(f"remove_schedule_{target_case_no}", None)
                                    st.session_state.pop(f"assignment_sync_applied_by_{target_case_no}", None)
                                    st.session_state.pop(f"assignment_sync_confirm_{target_case_no}", None)
                                    st.session_state.pop(preview_state_key, None)
                                    st.session_state["tab2_assignment_sync_success"] = "訂單成立並同步套用完成；正式指派與日排班已更新。"
                                    st.rerun()
                                except (requests.RequestException, ValueError) as err:
                                    st.error(f"指派同步套用失敗：{err}")

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
                    resp_cancel = requests.put(
                        f"{API_BASE_URL}/api/v1/orders/{target_case_no}/status",
                        json={"status": "訂單取消", "cancel_reason": cancel_reason_input.strip()},
                        timeout=10,
                    )
                    resp_cancel.raise_for_status()
                    st.success("訂單已標記為「訂單取消」，取消原因已儲存！")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 取消訂單 API 失敗: {e}")
