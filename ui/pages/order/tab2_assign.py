"""
================================================================================
檔案名稱: ui/pages/order/tab2_assign.py
功能說明: Tab 2 月嫂配對中心 REST API 遷移版 (OrderUI_Tab2_Assign)
================================================================================
"""

from datetime import date, datetime, timedelta
import os
import requests
import streamlit as st
from ui.api_clients.assignment_plan_api_client import AssignmentPlanApiClient
from ui.api_clients.case_architecture_bootstrap_api_client import (
    CaseArchitectureBootstrapApiClient,
)
from ui.pages.order.case_architecture_bootstrap_panel import (
    ensure_case_architecture_ready,
)
from ui.pages.scheduling.assignment_plan_panel import (
    render_assignment_plan_panel,
)
from ui.pages.order.shared import safe_int
from ui.pages.shared import (
    build_admin_headers,
    resolve_api_base_url,
)


def _api_request(path, *, method="GET", payload=None, headers=None):
    request_headers = headers if headers is not None else build_admin_headers()
    response = requests.request(
        method,
        f"{resolve_api_base_url()}{path}",
        headers=request_headers,
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


def _development_preview_is_enabled() -> bool:
    app_env = (os.getenv("APP_ENV", "development") or "development").strip().lower()
    return app_env in {"development", "dev", "local", "test"}


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


def _single_caregiver_covers_service_period(order, *, headers):
    start_date = _iso_date_text(
        order.get("actual_start_date") or order.get("start_date"),
        required=True,
        field_name="服務開始日",
    )
    raw_end = order.get("actual_end_date") or order.get("end_date")
    if raw_end:
        end_date = _iso_date_text(raw_end, required=True, field_name="服務結束日")
    else:
        service_days = int(safe_int(order.get("service_days")))
        if service_days <= 0:
            raise ValueError("服務天數必須為正整數")
        end_date = (
            datetime.strptime(start_date, "%Y-%m-%d").date()
            + timedelta(days=service_days - 1)
        ).isoformat()
    availability = _api_request(
        f"/api/v1/orders/{order['case_no']}/caregiver-single-eligibility/check",
        method="POST",
        headers=headers,
        payload={
            "start_date": start_date,
            "end_date": end_date,
            "as_of": date.today().isoformat(),
        },
    )
    return bool(availability.get("complete_combinations"))


def _render_tab2_assign(
    orders_data,
    clients,
    staff_list,
    *,
    multi_segment_renderer=None,
    multi_segment_preview_renderer=None,
    preferred_case_no=None,
):
    """Tab 2: 月嫂配對中心 (OrderUI_Tab2_MatchingCenter) - 僅處理「洽談中」待配對案件"""
    st.subheader("🤝 月嫂配對中心 (Clients, Orders & Matching)")
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

    st.markdown("### ⚙️ 單筆待配對案件控制面板")
    preferred_label = next(
        (
            label
            for label, case_no in target_case_options.items()
            if preferred_case_no is not None
            and str(case_no) == str(preferred_case_no)
        ),
        None,
    )
    if preferred_label is not None:
        st.session_state["tab2_case_picker"] = preferred_label
    selected_case_label = st.selectbox("🎯 選擇待配對與指派之案件", list(target_case_options.keys()), key="tab2_case_picker")
    target_case_no = target_case_options[selected_case_label]
    target_order = next((o for o in pending_orders if o['case_no'] == target_case_no), None)

    if not target_order:
        return

    try:
        admin_headers = build_admin_headers()
    except Exception as err:
        st.error(f"未完成管理員授權設定：{err}")
        return

    # 單筆案件 3 大子選單標籤
    sub_tab1, sub_tab2 = st.tabs(
        ["👁️ 檢視案件詳情", "⚡ 4步智慧配對與指派"]
    )

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
            resp_m = requests.get(
                f"{resolve_api_base_url()}/api/v1/orders/{target_case_no}/matches",
                headers=admin_headers,
                timeout=10,
            )
            resp_m.raise_for_status()
            match_records = resp_m.json().get("data") or []
        except Exception as e:
            st.error(f"❌ 讀取媒合記錄 API 失敗: {e}")
            match_records = []

        # 僅顯示至少有一項發送紀錄或意願已更新的媒合紀錄
        valid_matches = [
            m for m in match_records
            if m.get('sent_info_1_at') or m.get('sent_info_2_at') or m.get('caregiver_accepted') is not None
        ]
        if valid_matches:
            st.write("📋 當前月嫂意願詢問紀錄：")
            for m in valid_matches:
                acc = m.get('caregiver_accepted')
                acc_lbl = "🟢 願意接案" if acc == 1 else ("🔴 拒絕" if acc == 0 else "🟡 待回覆")
                s1_val = m.get('sent_info_1_at')
                s2_val = m.get('sent_info_2_at')
                s1 = f"已於 {s1_val}" if s1_val else "未發送"
                s2 = f"已於 {s2_val}" if s2_val else "未發送"
                st.markdown(f"**{m.get('staff_name', '月嫂')}** - 意願: `{acc_lbl}` (粗篩: {s1} | 精篩: {s2})")
            st.markdown("---")

        single_caregiver_available = True
        if multi_segment_renderer is not None:
            try:
                single_caregiver_available = _single_caregiver_covers_service_period(
                    target_order,
                    headers=admin_headers,
                )
            except (requests.RequestException, ValueError) as err:
                st.error(f"無法確認完整服務檔期：{err}")
                single_caregiver_available = None

        if single_caregiver_available is False:
            multi_segment_renderer(target_order, staff_list)
        elif single_caregiver_available is None:
            st.info("檔期資料恢復後才會顯示單一月嫂或多段配對流程。")
        elif not staff_list:
            st.warning("請先在服務人員資料表中建立服務人員。")
        else:
            if (
                multi_segment_preview_renderer is not None
                and _development_preview_is_enabled()
            ):
                preview_key = f"matching_multi_preview_{target_case_no}"
                preview_enabled = bool(st.session_state.get(preview_key))
                button_label = (
                    "關閉多月嫂測試預覽"
                    if preview_enabled
                    else "測試顯示多月嫂配對"
                )
                if st.button(
                    button_label,
                    key=f"matching_multi_preview_button_{target_case_no}",
                ):
                    st.session_state[preview_key] = not preview_enabled
                    st.rerun()
                if preview_enabled:
                    st.info(
                        "開發測試預覽：只查詢多人檔期並顯示介面，"
                        "不建立配對方案、不聯繫月嫂。"
                    )
                    multi_segment_preview_renderer(target_order, staff_list)

            with st.expander("🎯 智慧粗篩條件控制面板 (可自訂開啟/關閉，預設全選)", expanded=True):
                fc1, fc2 = st.columns(2)
                with fc1:
                    f_region = st.checkbox("☑️ 比對服務區域 (city/address 區域如香山/東區)", value=True, key="f_reg_toggle")
                    f_schedule = st.checkbox("☑️ 排除檔期時間衝突 (含 7 天預留備用期)", value=True, key="f_sch_toggle")
                with fc2:
                    f_babies = st.checkbox("☑️ 比對照顧胎數上限 (單/雙胞胎)", value=True, key="f_bab_toggle")
                    f_time = st.checkbox("☑️ 比對服務時段需求", value=True, key="f_time_toggle")

            try:
                resp_rec = requests.get(
                    f"{resolve_api_base_url()}/api/v1/matches/recommend-staff",
                    headers=admin_headers,
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
                st.error(f"❌ 智慧粗篩比對計算 API 失敗: {err}")
                rec_staff = []

            if not rec_staff:
                st.warning("⚠️ 依據當前勾選條件，暫無符合之月嫂。建議取消部分勾選以展開搜尋範圍。")
                staff_options = {f"{s['name']} ({s['phone']})": s['id'] for s in staff_list if s.get('name')}
            else:
                staff_options = {r['display_label']: r['staff_id'] for r in rec_staff}

            # ---------------------------------------------------------------
            # 步驟 1：粗篩發送 (多選)
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
                        resp_post = requests.post(
                            f"{resolve_api_base_url()}/api/v1/orders/{target_case_no}/matches",
                            headers=admin_headers,
                            json={"staff_id": sid},
                            timeout=10,
                        )
                        resp_post.raise_for_status()
                        m_data = resp_post.json().get("data") or {}
                        match_id = m_data.get("match_id") if isinstance(m_data, dict) else m_data
                        if match_id:
                            resp_s1 = requests.post(
                                f"{resolve_api_base_url()}/api/v1/matches/{match_id}/send-info-1",
                                headers=admin_headers,
                                timeout=10,
                            )
                            resp_s1.raise_for_status()
                    st.success(f"已對 {len(selected_staff_ids)} 位月嫂發送 訂單資訊-1！")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 發送失敗: {e}")

            st.markdown("---")

            # ---------------------------------------------------------------
            # 步驟 2：意願狀態更新 ＆ 發送 訂單資訊-2
            # ---------------------------------------------------------------
            sent1_matches = [m for m in match_records if m.get('sent_info_1_at')]

            st.markdown("##### 步驟 2: 更新月嫂意願 ＆ 發送 訂單資訊-2 (精篩，可複選多位月嫂)")

            if not sent1_matches:
                st.info("⚠️ 尚無月嫂收到 訂單資訊-1，請先完成步驟 1 的粗篩發送。")
            else:
                resp_opts = ["待回覆 (NULL)", "願意接案 (1)", "拒絕接案 (0)"]
                staff_ids_for_step2 = []

                for m in sent1_matches:
                    m_staff_id = m['staff_id']
                    acc_val = m.get('caregiver_accepted')
                    c_idx = 1 if acc_val == 1 else (2 if acc_val == 0 else 0)

                    col_name, col_resp, col_chk = st.columns([2, 2, 1.2])
                    with col_name:
                        s2_val = m.get('sent_info_2_at')
                        s2_lbl = f"已於 {s2_val}" if s2_val else "尚未發送-2"
                        st.write(f"**{m.get('staff_name', '月嫂')}**\n\n({s2_lbl})")
                    with col_resp:
                        new_resp = st.selectbox(
                            "意願狀態", resp_opts, index=c_idx,
                            key=f"resp_select_{m['match_id'] if 'match_id' in m else m.get('id')}", label_visibility="collapsed"
                        )
                        new_accepted_val = True if new_resp == "願意接案 (1)" else (False if new_resp == "拒絕接案 (0)" else None)
                        if new_accepted_val != (True if acc_val == 1 else (False if acc_val == 0 else None)):
                            try:
                                m_id = m.get('match_id') or m.get('id')
                                resp_rep = requests.put(
                                    f"{resolve_api_base_url()}/api/v1/matches/{m_id}/reply",
                                    headers=admin_headers,
                                    json={"accepted": new_accepted_val},
                                    timeout=10,
                                )
                                resp_rep.raise_for_status()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ 意願更新 API 失敗: {e}")
                    with col_chk:
                        m_id = m.get('match_id') or m.get('id')
                        checked = st.checkbox("發送-2", key=f"send2_chk_{m_id}")
                        if checked:
                            staff_ids_for_step2.append(m_staff_id)

                if st.button("2️⃣ 發送 訂單資訊-2 給已勾選月嫂 (精篩)", key="btn_send_2_batch", disabled=not staff_ids_for_step2):
                    try:
                        for sid in staff_ids_for_step2:
                            resp_post = requests.post(
                                f"{resolve_api_base_url()}/api/v1/orders/{target_case_no}/matches",
                                headers=admin_headers,
                                json={"staff_id": sid},
                                timeout=10,
                            )
                            resp_post.raise_for_status()
                            m_data = resp_post.json().get("data") or {}
                            match_id = m_data.get("match_id") if isinstance(m_data, dict) else m_data
                            if match_id:
                                resp_s2 = requests.post(
                                    f"{resolve_api_base_url()}/api/v1/matches/{match_id}/send-info-2",
                                    headers=admin_headers,
                                    timeout=10,
                                )
                                resp_s2.raise_for_status()
                        st.success(f"已對 {len(staff_ids_for_step2)} 位月嫂發送 訂單資訊-2！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 發送失敗: {e}")

            st.markdown("---")
            st.markdown("##### 步驟 3：傳送履歷給客戶與正式指派同步")

            accepted_matches = [m for m in match_records if m.get('caregiver_accepted') == 1]
            if not accepted_matches:
                st.info("⚠️ 提示：需待至少一位月嫂回覆「願意接案」後，方可進行傳送履歷與正式指派同步。")
            else:
                final_options = {}
                for index, match in enumerate(accepted_matches):
                    staff_name = match.get('staff_name', '月嫂')
                    match_id = match.get('match_id') or match.get('id')
                    final_options[f"{index + 1}. {staff_name} (match #{match_id})"] = match

                final_match_label = st.selectbox(
                    "選擇已願意接案者 (步驟 3)",
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
                    st.success(f"🎉 已選定月嫂：{final_match.get('staff_name', '月嫂')}")

                    if st.button("🤝 3️⃣ 傳送履歷給客戶", key=f"btn_send_resume_{target_case_no}"):
                        try:
                            _api_request(
                                f"/api/v1/matches/{final_match_id}/send-resume",
                                method="POST",
                                headers=admin_headers,
                            )
                            st.success("履歷已傳送到客戶 LINE，等待回饋。")
                        except (requests.RequestException, ValueError) as err:
                            st.error(f"❌ 傳送履歷失敗: {err}")

                    st.markdown("#### 步驟 4：正式人力配置")
                    bootstrap_client = CaseArchitectureBootstrapApiClient(
                        base_url=resolve_api_base_url(),
                        headers=admin_headers,
                    )
                    if not ensure_case_architecture_ready(
                        target_case_no,
                        bootstrap_client,
                    ):
                        st.info("案件根狀態完成後，才會開放 Assignment Plan。")
                        return
                    assignment_client = AssignmentPlanApiClient(
                        base_url=resolve_api_base_url(),
                        headers=admin_headers,
                    )
                    render_assignment_plan_panel(
                        target_case_no,
                        assignment_client,
                        preferred_staff_id=final_staff_id,
                    )
