"""Orders UI for confirming planned service dates."""

from datetime import date
from uuid import uuid4
import requests
import streamlit as st


def render_service_date_confirmation_panel(case_no, base_url, headers):
    st.markdown("#### 確認服務日期")
    try:
        facts = _request("GET", f"{base_url}/api/v1/orders/{case_no}/service-dates", headers)
    except ValueError as error:
        st.error(f"無法取得服務日期：{error}")
        return
    defaults = facts.get("current_dates") or facts.get("suggested_dates") or []
    try:
        selected = _service_dates_editor(case_no, facts, defaults)
    except ValueError:
        st.error("服務日期格式錯誤，請每列輸入一個 YYYY-MM-DD 日期。")
        return
    required_count = facts["contracted_service_days"]
    st.caption(f"已選 {len(selected)}／{required_count} 天")
    if st.button("產生服務日期 Preview", key=f"preview_service_dates_{case_no}"):
        if len(selected) != required_count:
            st.error(f"服務日期必須剛好選擇 {required_count} 天。")
            return
        try:
            st.session_state[f"service_date_preview_{case_no}"] = _request("POST", f"{base_url}/api/v1/orders/{case_no}/service-dates/preview", headers, {"service_dates": selected})
        except ValueError as error:
            st.error(f"服務日期 Preview 失敗：{error}")
    preview = st.session_state.get(f"service_date_preview_{case_no}")
    if not preview:
        return
    st.dataframe(preview["weeks"], hide_index=True, width="stretch")
    reason = st.text_input("調整說明（選填）", key=f"service_date_reason_{case_no}")
    if st.button("確認服務日期", type="primary", key=f"apply_service_dates_{case_no}"):
        payload = {"service_dates": preview["service_dates"], "expected_order_version": preview["order_version"], "expected_scheduling_version": preview["scheduling_version"], "preview_fingerprint": preview["preview_fingerprint"], "reason": reason}
        try:
            _request("POST", f"{base_url}/api/v1/orders/{case_no}/service-dates/apply", {**headers, "Idempotency-Key": str(uuid4())}, payload)
        except ValueError as error:
            st.error(f"確認服務日期失敗：{error}")
            return
        st.session_state.pop(f"service_date_preview_{case_no}", None)
        st.success("服務日期已確認；日期表需重新發送並取得客戶與月嫂確認。")
        st.rerun()


def _service_dates_editor(case_no, facts, defaults):
    selectable_dates = facts.get("selectable_dates") or []
    if selectable_dates:
        st.caption(
            f"可調整範圍：{selectable_dates[0]} ～ {selectable_dates[-1]}；"
            "每列一個 YYYY-MM-DD 日期。"
        )
    raw_dates = st.text_area(
        f"服務日期（需選 {facts['contracted_service_days']} 天）",
        value="\n".join(str(item) for item in defaults),
        key=f"confirmed_service_dates_{case_no}",
        placeholder="2026-10-10\n2026-10-11",
    )
    return _parse_service_dates(raw_dates)


def _parse_service_dates(raw_dates):
    dates = []
    for raw_date in raw_dates.splitlines():
        normalized = raw_date.strip()
        if not normalized:
            continue
        dates.append(date.fromisoformat(normalized).isoformat())
    return dates


def _request(method, url, headers, payload=None):
    response = requests.request(method, url, headers=headers, json=payload, timeout=15)
    try:
        body = response.json()
    except ValueError as error:
        raise ValueError(f"HTTP {response.status_code}") from error
    if not response.ok or not body.get("success"):
        raise ValueError(str(body.get("detail") or body.get("message") or body))
    return body.get("data") or {}
