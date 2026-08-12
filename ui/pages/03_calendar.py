"""
================================================================================
檔案名稱: ui/pages/03_calendar.py
功能說明: 服務人員行事曆與檔期調控獨立頁面 (CalendarUI)
專案名稱: Lobar Union - 服務人員與訂單管理系統
建立日期: 2026-07-03
架構規範: 已從 OrderUI 完全解耦的獨立行事曆頁面
================================================================================
職責與業務規則:
1. 提供服務人員 (月嫂) 檔期行事曆檢視與切換。
2. 兩階段操作選單 (ADR-v12-01, ADR-v13-01):
   - 「1. 執行操作」: [不連動，單純看行事曆 | 訂單匹配 | 出勤天數精算]
   - 「2. 訂單選擇」: 動態過濾對應狀態案件 (預設為無)。
3. 四色 HTML 月曆 (⚪白/🟡黃/🔴紅/🟢綠底):
   - 🟢 綠底休假: 輸入單日排休調整時，月曆表格即時同步呈現綠底標示。
   - 🔴 紅底工作日: 每增加 1 天綠底休假，後續紅底工作日與完工日自動向後動態順延展延。
   - ⚪ 解鎖備用期: 在「出勤天數精算」下，凡屬 target_order 且超出完工日之舊預排黃底日期強制抹除解鎖為白底。
4. 出勤天數精算與動態排假 (RULE[AGENTS.md]):
   - 確定實際服務開始日 (actual_start_date) 之案件解鎖精算面板。
   - 國定假日單日獨立個體決策: 勾選放假順延 1 天，未勾選照常上班。
5. 導覽約束: ui/app.py 動態載入與 Streamlit `/calendar` 直接入口都必須呼叫同一個 show()。
================================================================================
"""

import streamlit as st
from datetime import date, datetime, timedelta
import math
import re
import calendar
import json
import requests

from ui import nav_helper
from ui.api_clients.order_calendar_detail_api_client import (
    OrderCalendarDetailApiClient,
    OrderCalendarDetailApiError,
)
from ui.api_clients.order_actual_start_api_client import ActualStartApiClient
from ui.pages.order.actual_start_panel import render_actual_start_panel
class OrderLifecycleAdminApiClient:
    def __init__(self, *args, **kwargs): pass
    def get_control_state(self, *args, **kwargs): return None
class OrderLifecycleAdminApiError(Exception): pass
from ui.api_clients.order_summary_api_client import OrderSummaryApiClient
from ui.api_clients.staff_summary_api_client import StaffSummaryApiClient
from ui.api_clients.leave_substitution_api_client import (
    LeaveSubstitutionApiClient,
)
from ui.api_clients.scheduling_current_api_client import (
    SchedulingCurrentApiClient,
)
from ui.pages.shared import build_admin_headers, resolve_api_base_url
from ui.pages.scheduling.case_staffing import render_case_staffing
from ui.pages.scheduling.navigation_state import (
    clear_staff_calendar_navigation,
    consume_staff_calendar_selection,
    staff_option_label,
)
from ui.pages.scheduling.leave_substitution_panel import (
    render_leave_substitution_panel,
)
from ui.pages.scheduling.matching_center import render_matching_center
from ui.pages.scheduling.holiday_management import render_holiday_management
from ui.request_state import accept_request_result, begin_request, request_snapshot

title = "多月嫂排班"
_MATCHING_QUEUE_KEY = "multi_caregiver_matching_case_picker"
_SCHEDULING_WORKSPACES = (
    "服務人員月曆",
    "國定假日管理",
    "月嫂配對中心",
    "案件人力配置",
)
_REFERENCE_DATA_CACHE_SECONDS = 15


@st.cache_data(
    ttl=_REFERENCE_DATA_CACHE_SECONDS,
    show_spinner=False,
)
def _load_calendar_reference_rows(url, header_items):
    response = requests.get(
        url,
        headers=dict(header_items),
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("API 回傳的 data 不是清單格式")
    return rows


def _calendar_reference_rows(path, admin_headers):
    return _load_calendar_reference_rows(
        f"{resolve_api_base_url()}{path}",
        tuple(sorted(admin_headers.items())),
    )


@st.cache_data(
    ttl=_REFERENCE_DATA_CACHE_SECONDS,
    show_spinner=False,
)
def _load_staff_summary_rows(base_url, header_items, after_id=None):
    page = StaffSummaryApiClient(
        base_url=base_url,
        headers=dict(header_items),
    ).query(page_size=200, after_id=after_id)
    return [item.model_dump(mode="json") for item in page.items], page.next_cursor


def _load_staff_summary_page(workspace: str):
    cursor_key = f"scheduling_{workspace}_staff_after_id"
    next_key = f"scheduling_{workspace}_staff_next_cursor"
    rows, next_cursor = _load_staff_summary_rows(
        resolve_api_base_url(),
        tuple(sorted(build_admin_headers().items())),
        st.session_state.get(cursor_key),
    )
    st.session_state[next_key] = next_cursor
    return rows


@st.cache_data(
    ttl=_REFERENCE_DATA_CACHE_SECONDS,
    show_spinner=False,
)
def _load_staff_summary_by_id(base_url, header_items, staff_id):
    page = StaffSummaryApiClient(
        base_url=base_url,
        headers=dict(header_items),
    ).query(page_size=1, staff_id=staff_id)
    if not page.items:
        return None
    return page.items[0].model_dump(mode="json")


def _render_staff_summary_pagination(workspace: str) -> None:
    cursor_key = f"scheduling_{workspace}_staff_after_id"
    history_key = f"scheduling_{workspace}_staff_cursor_history"
    next_key = f"scheduling_{workspace}_staff_next_cursor"
    history = st.session_state.setdefault(history_key, [])
    current_cursor = st.session_state.get(cursor_key)
    next_cursor = st.session_state.get(next_key)
    if not history and not next_cursor:
        return
    previous_column, page_column, next_column = st.columns([1, 2, 1])
    if previous_column.button(
        "上一頁月嫂",
        disabled=not history,
        key=f"{workspace}_previous_staff_page",
    ):
        st.session_state[cursor_key] = history.pop()
        st.rerun()
    page_column.caption(f"月嫂摘要第 {len(history) + 1} 頁，每頁最多 200 筆")
    if next_column.button(
        "下一頁月嫂",
        disabled=not next_cursor,
        key=f"{workspace}_next_staff_page",
    ):
        history.append(current_cursor)
        st.session_state[cursor_key] = next_cursor
        st.rerun()

def safe_int(val) -> int:
    """安全轉換整數，防護 None, NaN, Inf 及無效字串 (ADR-v18-03)"""
    if val is None:
        return 0
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return 0
        return int(round(f))
    except (TypeError, ValueError):
        return 0


def safe_date(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if hasattr(val, "date"):
        return val
    if isinstance(val, (str, bytes)):
        try:
            clean_str = str(val).split(" ")[0].strip()
            return datetime.strptime(clean_str, "%Y-%m-%d").date()
        except ValueError:
            return None
    return val


def _normalise_calendar_schedule_map(value):
    """Restore integer day keys after the API's JSON object serialization."""
    if not isinstance(value, dict):
        return {}
    normalised = {}
    for raw_day, row in value.items():
        try:
            day = int(raw_day)
        except (TypeError, ValueError):
            continue
        if 1 <= day <= 31 and isinstance(row, dict):
            normalised_row = dict(row)
            if "client_name" in normalised_row:
                normalised_row["client_name"] = str(row.get("client_name") or "")
            normalised[day] = normalised_row
    return normalised


def _multi_caregiver_request(path, *, method="GET", payload=None):
    """Use only the assignment-aware APIs for the multi-caregiver panel."""
    response = requests.request(
        method,
        f"{resolve_api_base_url()}{path}",
        headers=build_admin_headers(),
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("success", False):
        raise ValueError(body.get("error") or body.get("message") or "多月嫂排班 API 請求失敗")
    return body.get("data") or {}


def _current_admin_actor() -> str:
    profile = st.session_state.get("line_admin_profile") or {}
    username = profile.get("username") if isinstance(profile, dict) else None
    return str(username or "development-bypass").strip()


def _calendar_has_unsaved_leave_changes() -> bool:
    return any(
        (
            key.startswith("leave_substitution_preview_")
            and isinstance(value, dict)
            and bool(value)
        )
        or (
            key.startswith("leave_item_count_")
            and isinstance(value, int)
            and value > 1
        )
        for key, value in st.session_state.items()
    )


def _discard_calendar_leave_drafts() -> None:
    prefixes = (
        "leave_original_assignment_",
        "leave_item_count_",
        "leave_schedule_",
        "leave_work_date_",
        "leave_resolution_",
        "leave_substitute_staff_",
        "leave_double_pay_",
        "leave_substitution_preview_",
        "leave_apply_reason_",
        "leave_apply_confirmed_",
    )
    for key in list(st.session_state):
        if key.startswith(prefixes):
            st.session_state.pop(key, None)


def _multi_caregiver_error(error):
    if isinstance(error, requests.HTTPError) and error.response is not None:
        try:
            detail = error.response.json().get("detail")
        except ValueError:
            detail = error.response.text
        return f"HTTP {error.response.status_code}: {detail}"
    return str(error)


def _coerce_staff_id(value):
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_iso_date_strict(value):
    if not isinstance(value, str):
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _parse_stored_rest_dates(raw_custom_json):
    """Parse legacy persisted rest dates without accepting ambiguous dates."""
    if not raw_custom_json:
        return set(), None

    try:
        persisted_list = (
            json.loads(raw_custom_json)
            if isinstance(raw_custom_json, str)
            else raw_custom_json
        )
    except (TypeError, json.JSONDecodeError, ValueError):
        return set(), "先前儲存的排休資料非有效 JSON，已忽略該欄位。"

    if not isinstance(persisted_list, list):
        return set(), "先前儲存的排休資料不是清單格式，已忽略該欄位。"

    parsed_dates = set()
    invalid_items = []
    for raw_item in persisted_list:
        parsed = _coerce_iso_date_strict(raw_item)
        if parsed is None:
            invalid_items.append(raw_item)
        else:
            parsed_dates.add(parsed)

    if invalid_items:
        return set(), (
            "先前儲存的排休資料含有不合法日期，已忽略該欄位："
            + ", ".join(str(item) for item in invalid_items)
        )

    return parsed_dates, None


def _extract_case_assignments_for_staff(assignments, staff_id):
    if not isinstance(assignments, list):
        return []
    target_staff_id = _coerce_staff_id(staff_id)
    if target_staff_id is None:
        return []

    active = []
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        if assignment.get("status") == "cancelled":
            continue
        assignment_staff_id = _coerce_staff_id(assignment.get("staff_id"))
        if assignment_staff_id == target_staff_id:
            active.append(assignment)
    return active


def _render_assignment_leave_resolution(
    case_no,
    assignment_id,
    assignments,
    *,
    read_only=False,
):
    """Render leave/defer/substitution controls for an already selected assignment."""
    del assignments
    if read_only:
        st.info("此訂單已完成，排班僅供歷史查閱，不開放休假、順延或代班調整。")
        return set()
    client = LeaveSubstitutionApiClient(
        base_url=resolve_api_base_url(),
        headers=build_admin_headers(),
    )
    render_leave_substitution_panel(
        case_no,
        client,
        original_assignment_id=assignment_id,
    )
    return set()


def _load_actual_start_control_state(case_no):
    client = OrderLifecycleAdminApiClient(_current_admin_actor())
    try:
        return client.get_control_state(case_no)
    except (OrderLifecycleAdminApiError, ValueError) as error:
        st.error(f"無法取得權威生命週期控制狀態：{error}")
        return None


def _render_active_actual_start_control(case_no, reconfirmation):
    blockers = reconfirmation.get("blockers") or []
    if blockers:
        st.error("目前阻擋原因：" + "、".join(map(str, blockers)))


def _render_actual_start_reconfirmation(target_order):
    case_no = str(target_order.get("case_no") or "").strip()
    if not case_no:
        st.error("案件缺少有效案件編號，無法讀取生命週期控制狀態。")
        return True
    control_state = _load_actual_start_control_state(case_no)
    if control_state is None:
        return True
    reconfirmation = control_state.get("actual_start_reconfirmation")
    if not isinstance(reconfirmation, dict):
        st.error("生命週期控制 API 缺少實際開始日重新確認狀態。")
        return True
    state = reconfirmation.get("state")
    if state in {"cleared", "not_required"}:
        return False
    if state == "active":
        _render_active_actual_start_control(case_no, reconfirmation)
        return True
    st.error("實際開始日重新確認狀態不是支援的 canonical 值。")
    return True


def _render_attendance_calculation(target_order, headers):
    context = _attendance_context(target_order)
    if context is None:
        st.warning("缺少實際開始日或服務天數，無法產生出勤 Preview。")
        return
    case_no, request_payload, potential_dates = context

    st.markdown("#### ⚙️ 調整精算控制 (預覽完工日)")
    custom_leave_dates = st.multiselect(
        "選擇休假/請假日期 (僅供完工日試算，正式寫入請至下方操作)",
        options=[d.strftime('%Y-%m-%d') for d in potential_dates],
        default=[],
        key=f"calc_leave_{case_no}",
    )
    request_payload["custom_leave_dates"] = custom_leave_dates

    state_key = f"attendance_preview_{case_no}"
    if st.button("產生出勤天數精算 Preview", key=f"{state_key}_button"):
        preview = _request_attendance_preview(request_payload, headers)
        if preview is not None:
            st.session_state[state_key] = {
                "request": request_payload,
                "preview": preview,
            }
    stored = st.session_state.get(state_key)
    if isinstance(stored, dict) and stored.get("request") == request_payload:
        _render_attendance_result(stored.get("preview") or {})


def _attendance_context(target_order):
    case_no = str(target_order.get("case_no") or "").strip()
    start_date = safe_date(
        target_order.get("actual_start_date")
        or target_order.get("start_date")
    )
    service_days = safe_int(target_order.get("service_days"))
    if not case_no or start_date is None or service_days <= 0:
        return None
    potential_dates = [start_date + timedelta(days=i) for i in range(service_days + 40)]
    return case_no, _attendance_request(target_order, start_date, service_days), potential_dates


def _attendance_request(target_order, start_date, service_days):
    return {
        "actual_start_date": start_date.isoformat(),
        "target_service_days": service_days,
        "service_mode": target_order.get("service_mode") or "週休1日",
    }


def _render_attendance_selection_guidance(action_mode, filtered_orders):
    if action_mode != "出勤天數精算":
        return
    if filtered_orders:
        st.info("請從「2. 訂單選擇」選擇案件，再產生出勤天數精算 Preview。")
        return
    st.info(
        "目前沒有已確認實際開始日、且可進行出勤精算的案件。"
        "請先在訂單頁完成實際開始日確認。"
    )


def _filter_attendance_orders(
    all_orders,
    cal_staff_id,
    cal_staff_name,
    *,
    formal_case_nos=(),
):
    allowed_statuses = {"訂單成立", "服務中", "訂單完成"}
    formal_case_nos = set(formal_case_nos)
    return [
        order
        for order in all_orders
        if order.get("order_status") in allowed_statuses
        and (
            _has_attendance_preview_entry_facts(order)
            or str(order.get("case_no") or "") in formal_case_nos
        )
        and _attendance_order_belongs_to_staff(
            order,
            cal_staff_id,
            cal_staff_name,
            formal_case_nos,
        )
    ]


def _attendance_order_belongs_to_staff(
    order,
    staff_id,
    staff_name,
    formal_case_nos,
):
    if _order_belongs_to_calendar_staff(order, staff_id, staff_name):
        return True
    return str(order.get("case_no") or "") in set(formal_case_nos)


def _staff_formal_case_nos(staff_id):
    assignment_data = _multi_caregiver_request(
        f"/api/v1/staff/{staff_id}/assignment-schedules"
    )
    return {
        str(row.get("case_no") or "")
        for row in assignment_data.get("assignments", [])
        if isinstance(row, dict) and str(row.get("case_no") or "")
    }


def _has_attendance_preview_entry_facts(order):
    if order.get("actual_start_date"):
        return True
    return order.get("order_status") in {"服務中", "訂單完成"}


def _order_belongs_to_calendar_staff(order, staff_id, staff_name):
    if safe_int(order.get("staff_id")) == staff_id:
        return True
    names = {
        item.strip()
        for item in str(order.get("staff_name") or "").replace("、", ",").split(",")
        if item.strip()
    }
    return staff_name in names


def _request_attendance_preview(payload, headers):
    try:
        response = requests.post(
            f"{resolve_api_base_url()}/api/v1/orders/calculate-schedule",
            headers=headers,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()
        return body.get("data") if body.get("success") else None
    except (requests.RequestException, ValueError) as error:
        st.error(f"出勤天數精算 Preview 失敗：{error}")
        return None


def _render_attendance_result(preview):
    if not preview:
        st.warning("後端未回傳出勤天數精算結果。")
        return
    st.markdown("#### 出勤天數與完工日 Preview")
    columns = st.columns(4)
    columns[0].metric("目標服務天數", preview.get("target_service_days", 0))
    columns[1].metric("總日曆天數", preview.get("total_calendar_days", 0))
    columns[2].metric("休假／請假天數", preview.get("rest_days_count", 0))
    columns[3].metric("預計完工日", str(preview.get("actual_end_date", "")))
    
    rest_days_count = preview.get("rest_days_count", 0)
    day_by_day = preview.get("day_by_day", [])
    if rest_days_count > 0 and day_by_day:
        rest_dates = [
            str(d.get("date", ""))
            for d in day_by_day
            if d.get("is_rest_day") and d.get("date")
        ]
        if rest_dates:
            st.info(f"休假日期清單：{', '.join(rest_dates)}")
            
    st.caption("此處只讀顯示後端計算；正式變更仍須走休假 Preview／Apply。")


def _apply_pending_staff_calendar_selection(staff_options):
    """套用來自異常警示中心的單次導向：預先選好月嫂與年月，並回傳要顯示的說明文字。

    只在有 pending_staff_calendar_staff_id 時動作一次（用 pop 取出並清掉，
    避免使用者手動切換人員/年月後，下次 rerun 又被異常導向的舊值蓋回去）。
    """
    selection = consume_staff_calendar_selection(st.session_state, staff_options)
    if selection is None:
        return None
    st.session_state["cal_staff_main"] = selection.label
    if selection.year is not None and selection.month is not None:
        st.session_state["calendar_view_year"] = selection.year
        st.session_state["calendar_view_month"] = selection.month
        st.session_state["cal_year_choice"] = selection.year
        st.session_state["cal_month_choice"] = selection.month
    return selection.note


def _render_staff_calendar():
    """服務人員行事曆與檔期調控獨立頁面入口 (CalendarUI)"""
    st.subheader("服務人員月曆")
    st.write("本系統提供月嫂動態檔期月曆、訂單匹配檔期預估以及確定開始日案件之出勤天數與完工日精算。")

    try:
        admin_headers = build_admin_headers()

        staff_list = _load_staff_summary_page("calendar")
        pending_staff_id = st.session_state.get("pending_staff_calendar_staff_id")
        if pending_staff_id is not None:
            pending_staff = _load_staff_summary_by_id(
                resolve_api_base_url(),
                tuple(sorted(admin_headers.items())),
                pending_staff_id,
            )
            if pending_staff is None:
                clear_staff_calendar_navigation(st.session_state)
                st.warning("異常導向的服務人員已不存在，未切換目前月曆選取。")
                return
            if all(item.get("id") != pending_staff_id for item in staff_list):
                staff_list.insert(0, pending_staff)
    except Exception as e:
        st.error(f"初始化載入服務人員資料失敗: {e}")
        return

    if not staff_list:
        st.warning("請先在服務人員名冊中建立服務人員。")
        return

    _render_staff_summary_pagination("calendar")

    try:
        # 1. 選擇月嫂與年月（同一列）
        staff_options = {
            staff_option_label(staff): staff["id"]
            for staff in staff_list
            if staff.get("name")
        }
        if not staff_options:
            st.warning("目前無可用的服務人員姓名資料，無法載入日曆。")
            return

        pending_note = _apply_pending_staff_calendar_selection(staff_options)

        today = datetime.today()
        st.session_state.setdefault("calendar_view_year", today.year)
        st.session_state.setdefault("calendar_view_month", today.month)
        view_year = int(st.session_state["calendar_view_year"])
        view_month = int(st.session_state["calendar_view_month"])
        if st.session_state.pop("calendar_reset_choices", False):
            st.session_state["cal_year_choice"] = view_year
            st.session_state["cal_month_choice"] = view_month

        if pending_note:
            st.warning(pending_note)

        staff_col, year_col, month_col = st.columns(3)
        with staff_col:
            selected_staff_label = st.selectbox(
                "選擇服務人員",
                list(staff_options.keys()),
                key="cal_staff_main",
            )
        cal_staff_id = staff_options[selected_staff_label]
        cal_staff_name = selected_staff_label.split(" (")[0] if " (" in selected_staff_label else selected_staff_label
        with year_col:
            current_year = datetime.today().year
            year_options = list(range(current_year - 2, current_year + 4))
            st.session_state.setdefault(
                "cal_year_choice",
                view_year if view_year in year_options else current_year,
            )
            requested_year = st.selectbox(
                "選擇年份",
                year_options,
                key="cal_year_choice",
            )
        with month_col:
            st.session_state.setdefault("cal_month_choice", view_month)
            requested_month = st.selectbox(
                "選擇月份",
                list(range(1, 13)),
                key="cal_month_choice",
            )

        previous_col, next_col, current_col = st.columns(3)
        pending_month = None
        if (requested_year, requested_month) != (view_year, view_month):
            pending_month = (requested_year, requested_month)
        if previous_col.button("上個月", key="calendar_previous_month"):
            target = datetime(view_year, view_month, 1) - timedelta(days=1)
            pending_month = (target.year, target.month)
        if next_col.button("下個月", key="calendar_next_month"):
            target = datetime(
                view_year + (1 if view_month == 12 else 0),
                1 if view_month == 12 else view_month + 1,
                1,
            )
            pending_month = (target.year, target.month)
        if current_col.button("回到本月", key="calendar_current_month"):
            pending_month = (today.year, today.month)

        st.markdown(f"#### 正在查看：{view_year} 年 {view_month} 月")

        if pending_month is not None and pending_month != (view_year, view_month):
            if _calendar_has_unsaved_leave_changes():
                st.session_state["calendar_pending_month"] = pending_month
            else:
                st.session_state["calendar_view_year"] = pending_month[0]
                st.session_state["calendar_view_month"] = pending_month[1]
                st.session_state["calendar_reset_choices"] = True
                st.rerun()

        pending_month = st.session_state.get("calendar_pending_month")
        if pending_month:
            st.warning("目前有尚未套用的休假調整；切換月份會放棄這些內容。")
            discard_col, stay_col = st.columns(2)
            if discard_col.button(
                "放棄未儲存調整並切換",
                key="calendar_confirm_discard_drafts",
            ):
                _discard_calendar_leave_drafts()
                st.session_state["calendar_view_year"] = pending_month[0]
                st.session_state["calendar_view_month"] = pending_month[1]
                st.session_state["calendar_reset_choices"] = True
                st.session_state.pop("calendar_pending_month", None)
                st.rerun()
            if stay_col.button("留在本月", key="calendar_keep_drafts"):
                st.session_state["calendar_reset_choices"] = True
                st.session_state.pop("calendar_pending_month", None)
                st.rerun()

        cal_year, cal_month = view_year, view_month
            
        # 2. 獲取該月嫂當月的排班狀態與國定假日
        try:
            resp_sched = requests.get(
                f"{resolve_api_base_url()}/api/v1/staff/{cal_staff_id}/monthly-schedule",
                headers=admin_headers,
                params={"year": cal_year, "month": cal_month},
                timeout=10,
            )
            resp_sched.raise_for_status()
            sched_payload = resp_sched.json()
            sched_data = sched_payload.get("data") or {}
            monthly_schedules = _normalise_calendar_schedule_map(
                sched_data.get("schedule_map")
            )
            monthly_schedule_rows = {}
            for row in sched_data.get("days") or []:
                work_date = safe_date(row.get("work_date"))
                if work_date and (
                    row.get("assignment_id") is not None
                    or row.get("status") == "waiting_deposit_lock"
                ) and row.get("order_status") != "訂單取消":
                    monthly_schedule_rows.setdefault(work_date.day, []).append(row)
        except Exception as err_sched:
            st.warning(f"⚠️ 月度排班資料 API 讀取失敗: {err_sched}")
            monthly_schedules = {}
            monthly_schedule_rows = {}

        try:
            holidays_raw = _calendar_reference_rows(
                "/api/v1/holidays",
                admin_headers,
            )
        except Exception as err_h:
            st.warning(f"⚠️ 國定假日資料 API 讀取失敗: {err_h}")
            holidays_raw = []
        
        holiday_map = {}
        for h in holidays_raw:
            h_date = safe_date(h['holiday_date'])
            if h_date and h_date.year == cal_year and h_date.month == cal_month:
                holiday_map[h_date.day] = h['holiday_name']

        # 3. 兩階段操作選單
        try:
            all_orders = _load_all_matching_order_summaries(
                resolve_api_base_url(),
                tuple(sorted(admin_headers.items())),
            )
        except Exception as err_o:
            st.warning(f"⚠️ 訂單資料 API 讀取失敗: {err_o}")
            all_orders = []
        target_order = None
        case_assignments = []
        
        col_op1, col_op2 = st.columns([1, 2])
        with col_op1:
            action_modes = ["訂單匹配", "出勤天數精算"]
            if st.session_state.get("calendar_action_mode") not in action_modes:
                st.session_state["calendar_action_mode"] = "出勤天數精算"
            action_mode = st.radio(
                "1. 執行操作",
                action_modes,
                key="calendar_action_mode"
            )
            
        with col_op2:
            # 根據 1. 執行操作 動態過濾符合條件的訂單
            if action_mode == "訂單匹配":
                filtered_orders = [
                    order
                    for order in all_orders
                    if order.get("order_status") == "洽談中"
                ]
            elif action_mode == "出勤天數精算":
                filtered_orders = _filter_attendance_orders(
                    all_orders,
                    cal_staff_id,
                    cal_staff_name,
                    formal_case_nos=_staff_formal_case_nos(cal_staff_id),
                )
            else:
                filtered_orders = []
            _render_attendance_selection_guidance(action_mode, filtered_orders)
                
            order_menu_opts = {"無 (單純查看行事曆)": None}
            for o in filtered_orders:
                st_d_tmp = safe_date(o['actual_start_date']) or safe_date(o['start_date'])
                ed_d_tmp = (
                    safe_date(o.get('actual_end_date'))
                    or safe_date(o.get('end_date'))
                )
                st_str = st_d_tmp.strftime('%Y-%m-%d') if st_d_tmp else '未定'
                ed_str = ed_d_tmp.strftime('%Y-%m-%d') if ed_d_tmp else '未定'
                label = f"訂單 #{o['case_no']} {o['client_name']} {o['order_status']} ({st_str} ~ {ed_str})"
                order_menu_opts[label] = o['case_no']
                
            order_selection_key = f"order_select_{action_mode}_{cal_staff_id}"
            if st.session_state.get(order_selection_key) not in order_menu_opts:
                st.session_state[order_selection_key] = next(iter(order_menu_opts))
            selected_order_label = st.selectbox(
                "2. 訂單選擇", 
                list(order_menu_opts.keys()), 
                index=0,
                disabled=(action_mode == "不連動，單純看行事曆"),
                key=order_selection_key
            )
            calc_case_no = order_menu_opts[selected_order_label]
            calc_assignment_id = None
            if calc_case_no:
                try:
                    case_assignments = _multi_caregiver_request(
                        f"/api/v1/cases/{calc_case_no}/assignment-schedules"
                    ).get("assignments", [])
                    active_assignments = _extract_case_assignments_for_staff(
                        case_assignments, cal_staff_id
                    )
                    if len(active_assignments) == 1:
                        calc_assignment_id = active_assignments[0].get("id")
                        st.caption(
                            "已自動使用該月嫂目前唯一有效的正式服務指派，"
                            "可直接進入排休保存流程。"
                        )
                    elif len(active_assignments) > 1:
                        st.warning("此案件目前有多位有效正式服務指派，請先選擇服務指派後再儲存排休。")
                        assignment_options = {
                            "請先選擇服務指派": None
                        }
                        for item in active_assignments:
                            assignment_label = (
                                f"#{item.get('id')} "
                                f"{item.get('staff_name', '') or ''} "
                                f"{item.get('assigned_start_date', '')} ～ {item.get('assigned_end_date', '')}"
                            ).strip()
                            assignment_options[assignment_label] = item.get("id")
                        selected_assignment_label = st.selectbox(
                            "2-1. 選擇正式服務指派",
                            list(assignment_options.keys()),
                            index=0,
                            key=f"calendar_case_assignment_{calc_case_no}_{cal_staff_id}",
                        )
                        calc_assignment_id = assignment_options.get(selected_assignment_label)
                    else:
                        st.warning("此案件目前沒有可用的正式服務指派（未取消、且屬於該月嫂）。")
                except (requests.RequestException, ValueError) as error:
                    st.error(f"無法取得案例正式服務指派：{_multi_caregiver_error(error)}")

            if calc_case_no:
                target_order = next((o for o in all_orders if o['case_no'] == calc_case_no), None)
                if action_mode == "出勤天數精算" and target_order:
                    try:
                        calendar_detail = _load_order_calendar_detail(
                            resolve_api_base_url(),
                            tuple(sorted(admin_headers.items())),
                            calc_case_no,
                        )
                        target_order = {**target_order, **calendar_detail}
                    except (
                        OrderCalendarDetailApiError,
                        ValueError,
                    ) as error:
                        st.error(f"無法取得訂單固定排休條款：{error}")
                        target_order = None

        preview_days_set = set()
        buffer_days_set = set()
        if action_mode == "訂單匹配" and target_order:
            st_d = safe_date(target_order.get('actual_start_date')) or safe_date(target_order.get('start_date'))
            days_cnt = target_order.get('service_days') or 20
            ed_d = st_d + timedelta(days=days_cnt - 1) if st_d else None
            
            if st_d and ed_d:
                curr = st_d
                while curr <= ed_d:
                    if curr.year == cal_year and curr.month == cal_month:
                        preview_days_set.add(curr.day)
                    curr += timedelta(days=1)
                
                # 計算後 7 日緩衝
                b_curr = ed_d + timedelta(days=1)
                for _ in range(7):
                    if b_curr.year == cal_year and b_curr.month == cal_month:
                        buffer_days_set.add(b_curr.day)
                    b_curr += timedelta(days=1)

        # Matching Preview belongs to the backend matching workflow.
        if action_mode == "訂單匹配" and target_order:
            st.info(
                "訂單匹配、服務區間與七日緩衝只顯示後端 Preview；"
                "本頁不自行推算或預先標色。"
            )

        # Leave/substitution mutation is delegated to the typed backend workflow.
        if action_mode == "出勤天數精算" and target_order:
            st.markdown("#### ⚙️ 調整精算控制 (休假與代班)")
            
            is_started_or_completed = target_order.get("order_status") in ("服務中", "訂單完成")
            is_completed = target_order.get("order_status") == "訂單完成"
            
            reconfirmation_blocks_assignment_writes = False
            if not is_started_or_completed:
                reconfirmation_blocks_assignment_writes = (
                    _render_actual_start_reconfirmation(
                        target_order,
                    )
                )

            if not is_started_or_completed:
                actual_start_client = ActualStartApiClient(
                    base_url=resolve_api_base_url(),
                    headers=admin_headers,
                )
                from ui.pages.order.actual_start_panel import render_actual_start_panel
                render_actual_start_panel(calc_case_no, actual_start_client)
                
                st.markdown("---")

            if is_completed and calc_assignment_id:
                _render_assignment_leave_resolution(
                    calc_case_no,
                    calc_assignment_id,
                    case_assignments,
                    read_only=True,
                )
            elif reconfirmation_blocks_assignment_writes:
                st.info(
                    "請先在上方確認『實際開工日』。完成確認後，才能產生正式的休假／代班 Preview。"
                )
            elif calc_assignment_id:
                _render_assignment_leave_resolution(
                    calc_case_no,
                    calc_assignment_id,
                    case_assignments,
                    read_only=False,
                )
            else:
                st.info("尚未產生正式服務指派，無法產生休假／代班 Preview。")

    except Exception as e_step2:
        st.error(f"資料庫與選單加載失敗: {e_step2}")
        st.exception(e_step2)
        return

    try:
        if action_mode == "出勤天數精算" and calc_case_no:
            # 1. First check if there is a formal leave batch preview
            formal_preview = st.session_state.get(f"attendance_preview_formal_{calc_case_no}")
            if formal_preview is not None and hasattr(formal_preview, 'calendar_candidate'):
                preview_client_name = target_order.get("client_name", "") + " (Preview)" if target_order else ""
                for cell in formal_preview.calendar_candidate.day_cells:
                    d_obj = cell.calendar_date
                    if d_obj.year != cal_year or d_obj.month != cal_month or cell.change_kind == "unchanged":
                        continue
                    if cell.change_kind == "substitute":
                        status = "preview_substitute"
                        description = "代班服務日"
                    elif cell.after_kind == "none":
                        status = "preview_holiday"
                        description = "休假日（扣除服務日並順延）"
                    else:
                        status = "preview_deferred"
                        description = "順延後服務日"
                    owner = f"月嫂 {cell.before_staff_id or '-'} → {cell.after_staff_id or '-'}"
                    monthly_schedules[d_obj.day] = {
                        "status": status,
                        "client_name": f"{preview_client_name}｜{description}｜{owner}",
                    }
                    monthly_schedule_rows.pop(d_obj.day, None)

        # 6. 繪製四色 HTML 月曆表格 (即時反映 ⚪白 / 🟡黃 / 🔴紅 / 🟢綠底)
        first_weekday, num_days = calendar.monthrange(cal_year, cal_month)
        first_weekday_sun = (first_weekday + 1) % 7
        
        html = """<style>
.cal-table { width: 100%; border-collapse: collapse; font-family: sans-serif; margin-top: 15px; margin-bottom: 20px; }
.cal-table th { background-color: #f3f4f6; color: #374151; padding: 10px; text-align: center; border: 1px solid #e5e7eb; font-weight: bold; }
.cal-table td { height: 110px; width: 14%; border: 1px solid #e5e7eb; vertical-align: top; padding: 8px; position: relative; }
.day-num { font-weight: bold; font-size: 1.1em; color: #4b5563; }
.day-holiday { font-size: 0.8em; color: #ef4444; margin-top: 2px; font-weight: bold; }
.day-status { font-size: 0.85em; margin-top: 6px; padding: 4px 6px; border-radius: 4px; font-weight: 500; text-align: center; }
.status-white { background-color: #ffffff; color: #1f2937; }
.status-yellow { background-color: #fef08a; color: #854d0e; }
.status-red { background-color: #fca5a5; color: #991b1b; }
.status-green { background-color: #bbf7d0; color: #166534; }
.status-preview-holiday { background-color: #dbeafe; color: #1e3a8a; }
.status-preview-deferred { background-color: #ffedd5; color: #9a3412; }
.status-preview-substitute { background-color: #fce7f3; color: #9d174d; }
.status-label-white { color: #10b981; font-weight: bold; }
.status-label-yellow { color: #b45309; font-weight: bold; }
.status-label-red { color: #b91c1c; font-weight: bold; }
.status-label-green { color: #15803d; font-weight: bold; }
.status-label-preview-holiday { color: #1d4ed8; font-weight: bold; }
.status-label-preview-deferred { color: #c2410c; font-weight: bold; }
.status-label-preview-substitute { color: #be185d; font-weight: bold; }
.client-text { font-size: 0.9em; margin-top: 4px; display: block; }
</style>
<table class="cal-table"><thead><tr><th>星期日</th><th>星期一</th><th>星期二</th><th>星期三</th><th>星期四</th><th>星期五</th><th>星期六</th></tr></thead><tbody>"""
        
        day = 1
        for row in range(6):
            html += "<tr>"
            for col in range(7):
                cell_idx = row * 7 + col
                if cell_idx < first_weekday_sun or day > num_days:
                    html += "<td class='status-white'></td>"
                else:
                    day_info = monthly_schedules.get(day, None)
                    day_rows = monthly_schedule_rows.get(day, [])
                    holiday_name = holiday_map.get(day, None)
                    
                    bg_class = "status-white"
                    status_label = "<span class='status-label-white'>⚪ 可接案</span>"
                    client_text = ""
                    
                    if day_info:
                        day_client_name = str(day_info.get('client_name') or "")
                        if day_info['status'] == 'yellow':
                            bg_class = "status-yellow"
                            status_label = "<span class='status-label-yellow'>🟡 已鎖定／待成立</span>"
                            client_text = f"<span class='client-text'><b>客戶: {day_client_name}</b></span>"
                        elif day_info['status'] == 'green':
                            bg_class = "status-green"
                            status_label = "<span class='status-label-green'>🟢 排班週休日</span>"
                            client_text = f"<span class='client-text'><b>客戶: {day_client_name}</b></span>"
                        elif day_info['status'] == 'red':
                            bg_class = "status-red"
                            status_label = "<span class='status-label-red'>🔴 服務工作日</span>"
                            client_text = f"<span class='client-text'><b>客戶: {day_client_name}</b></span>"
                        elif day_info['status'] == 'historical':
                            bg_class = "status-yellow"
                            status_label = "<span class='status-label-yellow'>📜 歷史正式指派</span>"
                            client_text = f"<span class='client-text'><b>客戶: {day_client_name}</b></span>"
                        elif day_info['status'] == 'preview_holiday':
                            bg_class = "status-preview-holiday"
                            status_label = "<span class='status-label-preview-holiday'>🌴 Preview 國定假日休假</span>"
                            client_text = f"<span class='client-text'><b>{day_client_name}</b></span>"
                        elif day_info['status'] == 'preview_deferred':
                            bg_class = "status-preview-deferred"
                            status_label = "<span class='status-label-preview-deferred'>➡ Preview 順延後服務日</span>"
                            client_text = f"<span class='client-text'><b>{day_client_name}</b></span>"
                        elif day_info['status'] == 'preview_substitute':
                            bg_class = "status-preview-substitute"
                            status_label = "<span class='status-label-preview-substitute'>🔁 Preview 代班服務日</span>"
                            client_text = f"<span class='client-text'><b>{day_client_name}</b></span>"

                    if day_rows and not day_info:
                        client_text = "".join(
                            "<span class='client-text'><b>"
                            + f"{row.get('client_name') or '-'}｜{row.get('order_status') or '-'}｜{row.get('staff_name') or '-'}"
                            + "</b></span>"
                            for row in day_rows
                        )
                    
                    # 訂單匹配模式下疊加黃底預排試算
                    if action_mode == "訂單匹配" and target_order and bg_class == "status-white":
                        if day in preview_days_set:
                            bg_class = "status-yellow"
                            status_label = "<span class='status-label-yellow'>🟡 試算預排檔期</span>"
                            client_text = f"<span class='client-text'><b>預覽: {target_order.get('client_name', '')}</b></span>"
                        elif day in buffer_days_set:
                            bg_class = "status-yellow"
                            status_label = "<span class='status-label-yellow'>🟡 試算預留備用期</span>"
                    
                    holiday_text = f"<div class='day-holiday'>🔴 {holiday_name}</div>" if holiday_name else ""
                    
                    html += f"<td class='{bg_class}'><div class='day-num'>{day}</div>{holiday_text}<div class='day-status'>{status_label}{client_text}</div></td>"
                    day += 1
            html += "</tr>"
            if day > num_days:
                break
        html += "</tbody></table>"
        
        st.markdown(html, unsafe_allow_html=True)
    except Exception as e_step3:
        st.error(f"❌ 月曆 HTML 繪製失敗: {e_step3}")
        st.exception(e_step3)
        return

def _load_matching_center_data(query_text=None, after_case_no=None):
    headers = build_admin_headers()
    order_page = _load_matching_order_summaries(
        resolve_api_base_url(),
        tuple(sorted(headers.items())),
        after_case_no,
        query_text,
    )
    return order_page


@st.cache_data(
    ttl=_REFERENCE_DATA_CACHE_SECONDS,
    show_spinner=False,
)
def _load_matching_order_summaries(
    base_url,
    header_items,
    after_case_no=None,
    query_text=None,
):
    result = OrderSummaryApiClient(
        base_url=base_url,
        headers=dict(header_items),
    ).query(
        page_size=50,
        after_case_no=after_case_no,
        query_text=query_text,
    )
    if result.page is None:
        raise ValueError("訂單摘要 API 未回傳資料")
    return (
        [item.model_dump(mode="json") for item in result.page.items],
        result.page.next_cursor,
    )


def _load_all_matching_order_summaries(base_url, header_items):
    all_orders = []
    after_case_no = None
    while True:
        page, next_cursor = _load_matching_order_summaries(
            base_url,
            header_items,
            after_case_no,
        )
        all_orders.extend(page)
        if next_cursor is None:
            return all_orders
        after_case_no = next_cursor


@st.cache_data(
    ttl=_REFERENCE_DATA_CACHE_SECONDS,
    show_spinner=False,
)
def _load_order_calendar_detail(base_url, header_items, case_no):
    detail = OrderCalendarDetailApiClient(
        base_url=base_url,
        headers=dict(header_items),
    ).query(case_no)
    return detail.model_dump(mode="json")


def show():
    """多月嫂排班集中入口。"""
    st.title("多月嫂排班")
    if "pending_staff_calendar_staff_id" in st.session_state:
        st.session_state["scheduling_workspace"] = "服務人員月曆"
    queue_item = nav_helper.current_queue_item(_MATCHING_QUEUE_KEY)
    if queue_item is not None:
        queue = nav_helper.current_queue(_MATCHING_QUEUE_KEY)
        st.warning(
            f"來自異常警示中心的配對佇列：第 {queue['index'] + 1} / "
            f"{len(queue['items'])} 筆｜案件 {queue_item['case_no']}"
        )
        next_col, exit_col = st.columns(2)
        if next_col.button("下一筆案件", key="matching_queue_next"):
            nav_helper.advance_queue(_MATCHING_QUEUE_KEY)
            st.rerun()
        if exit_col.button("結束配對佇列", key="matching_queue_exit"):
            nav_helper.end_queue()
            st.rerun()
        try:
            orders, _ = _load_matching_center_data(str(queue_item["case_no"]))
            staff = _load_staff_summary_page("matching_queue")
            _render_staff_summary_pagination("matching_queue")
            render_matching_center(
                orders,
                staff,
                preferred_case_no=str(queue_item["case_no"]),
                default_to_plan=True,
            )
        except Exception as error:
            st.error(f"月嫂配對中心載入失敗：{error}")
        return

    workspace = st.radio(
        "排班工作區",
        _SCHEDULING_WORKSPACES,
        horizontal=True,
        label_visibility="collapsed",
        key="scheduling_workspace",
    )
    _render_scheduling_workspace(workspace)


def _render_scheduling_workspace(workspace: str) -> None:
    if workspace == "服務人員月曆":
        _render_staff_calendar()
        return

    if workspace == "國定假日管理":
        render_holiday_management()
        return

    if workspace == "月嫂配對中心":
        _render_matching_workspace()
        return

    if workspace == "案件人力配置":
        _render_case_staffing_workspace()
        return

    st.error("未知的排班工作區。")


def _render_matching_workspace() -> None:
    query_text = st.text_input("搜尋案件編號或客戶姓名", key="scheduling_order_search").strip()
    after_case_no = _prepare_scheduling_order_page("matching", query_text)
    request = begin_request(st.session_state, "scheduling_matching_request")
    try:
        with st.spinner("正在載入月嫂配對案件與人員…"):
            orders, next_cursor = _load_matching_center_data(query_text or None, after_case_no)
            staff = _load_staff_summary_page("matching")
    except Exception as error:
        accept_request_result(
            st.session_state,
            "scheduling_matching_request",
            request,
            item_count=0,
            error_message=str(error),
        )
        st.error(f"月嫂配對中心載入失敗：{error}")
        return
    if not _accept_matching_workspace_result(request, orders, staff):
        return
    _render_scheduling_order_pagination("matching", next_cursor)
    _render_staff_summary_pagination("matching")
    render_matching_center(orders, staff)


def _accept_matching_workspace_result(request, orders, staff) -> bool:
    accepted = accept_request_result(
        st.session_state,
        "scheduling_matching_request",
        request,
        item_count=len(orders) + len(staff),
    )
    snapshot = request_snapshot(st.session_state, "scheduling_matching_request")
    if not accepted or snapshot.generation != request.generation:
        st.info("已忽略過期的配對資料回應，正在使用較新的查詢。")
        return False
    if snapshot.status == "empty":
        st.info("目前沒有符合條件的配對案件或可用人員。")
    return True


def _render_case_staffing_workspace() -> None:
    try:
        pending_case_no = st.session_state.get("pending_scheduling_case_no")
        manual_query_text = st.text_input(
            "搜尋案件編號或客戶姓名",
            key="scheduling_order_search",
        ).strip()
        query_text = (
            pending_case_no.strip()
            if isinstance(pending_case_no, str) and pending_case_no.strip()
            else manual_query_text
        )
        after_case_no = _prepare_scheduling_order_page("staffing", query_text)
        orders, next_cursor = _load_matching_center_data(query_text or None, after_case_no)
        staff = _load_staff_summary_page("staffing")
        _render_scheduling_order_pagination("staffing", next_cursor)
        _render_staff_summary_pagination("staffing")
        render_case_staffing(orders=orders, staff=staff)
    except Exception as error:
        st.error(f"案件人力配置載入失敗：{error}")


def _prepare_scheduling_order_page(workspace: str, query_text: str) -> str | None:
    query_key = f"scheduling_{workspace}_order_query"
    cursor_key = f"scheduling_{workspace}_order_after_case_no"
    if st.session_state.get(query_key) != query_text:
        st.session_state[query_key] = query_text
        st.session_state[cursor_key] = None
        st.session_state[f"scheduling_{workspace}_order_cursor_history"] = []
    return st.session_state.get(cursor_key)


def _render_scheduling_order_pagination(workspace: str, next_cursor: str | None) -> None:
    cursor_key = f"scheduling_{workspace}_order_after_case_no"
    history_key = f"scheduling_{workspace}_order_cursor_history"
    history = st.session_state.setdefault(history_key, [])
    if not history and not next_cursor:
        return
    previous_column, page_column, next_column = st.columns([1, 2, 1])
    if previous_column.button("上一頁案件", disabled=not history, key=f"{workspace}_previous_order_page"):
        st.session_state[cursor_key] = history.pop()
        _clear_scheduling_page_selection(workspace)
        st.rerun()
    page_column.caption(f"案件摘要第 {len(history) + 1} 頁，每頁最多 50 筆")
    if next_column.button("下一頁案件", disabled=not next_cursor, key=f"{workspace}_next_order_page"):
        history.append(st.session_state.get(cursor_key))
        st.session_state[cursor_key] = next_cursor
        _clear_scheduling_page_selection(workspace)
        st.rerun()


def _clear_scheduling_page_selection(workspace: str) -> None:
    selection_key = "matching_center_case" if workspace == "matching" else "staffing_case"
    st.session_state.pop(selection_key, None)


if __name__ == "__main__":
    show()
