"""Human review center for B6 finance alerts, backed only by the alert router."""

from __future__ import annotations

import json
import os
from typing import Any

import requests
import streamlit as st


title = "⚠️ 帳務警示中心"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
_STATUSES = ("", "open", "claimed", "resolved")


def _api_request(
    path: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    """Call only the finance-alert router; no workflow or database access exists here."""
    response = requests.request(
        method,
        f"{API_BASE_URL}/api/v1/finance-alerts{path}",
        params=params,
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("success", False):
        raise ValueError(body.get("error") or body.get("message") or "警示 API 請求失敗")
    return body.get("data")


def _error_text(error: Exception) -> str:
    if isinstance(error, requests.HTTPError) and error.response is not None:
        try:
            detail = error.response.json().get("detail")
        except ValueError:
            detail = error.response.text
        return f"HTTP {error.response.status_code}: {detail}"
    return str(error)


def _snapshot(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _render_alert_detail(alert: dict[str, Any]) -> None:
    st.subheader(f"警示 #{alert['id']}：{alert.get('alert_code', '')}")
    st.caption(
        f"狀態：{alert.get('status')}｜來源："
        f"{alert.get('source_domain')} / {alert.get('source_type')} / {alert.get('source_id')}"
    )
    st.write(alert.get("reason") or "未提供原因")
    st.dataframe(
        [
            {
                "預期金額": alert.get("expected_amount"),
                "實際金額": alert.get("actual_amount"),
                "差額": alert.get("difference_amount"),
                "匯入列": alert.get("finance_import_row_id"),
                "匯入批次": alert.get("finance_import_batch_id"),
            }
        ],
        hide_index=True,
        width="stretch",
    )
    st.markdown("#### 候選快照（僅供人工判讀）")
    st.json(_snapshot(alert.get("candidate_snapshot") or {}))
    st.markdown("#### 事件歷程")
    events = alert.get("events") or []
    if events:
        st.dataframe(events, hide_index=True, width="stretch")
    else:
        st.info("尚無事件歷程。")


def _render_actions(alert: dict[str, Any]) -> None:
    alert_id = alert["id"]
    st.markdown("#### 人工處理")
    st.warning("解除警示不等於完成核銷，也不會建立或修改正式帳務。")
    left, right = st.columns(2)
    with left:
        with st.form(f"finance_alert_claim_{alert_id}"):
            operator = st.text_input("認領者", key=f"claim_operator_{alert_id}")
            claim = st.form_submit_button("認領警示")
        if claim:
            if not operator.strip():
                st.error("認領者不可空白。")
            else:
                try:
                    result = _api_request(
                        f"/{alert_id}/claim",
                        method="POST",
                        payload={"operator": operator.strip()},
                    )
                except (requests.RequestException, ValueError) as error:
                    st.error(f"認領失敗：{_error_text(error)}")
                else:
                    st.success(f"認領結果：{result.get('result')}")
                    st.rerun()
    with right:
        with st.form(f"finance_alert_resolve_{alert_id}"):
            operator = st.text_input("處理者", key=f"resolve_operator_{alert_id}")
            reason = st.text_area("解除原因（必填）", key=f"resolve_reason_{alert_id}")
            resolve = st.form_submit_button("解除警示")
        if resolve:
            if not operator.strip() or not reason.strip():
                st.error("處理者與解除原因不可空白。")
            else:
                try:
                    result = _api_request(
                        f"/{alert_id}/resolve",
                        method="POST",
                        payload={"operator": operator.strip(), "reason": reason.strip()},
                    )
                except (requests.RequestException, ValueError) as error:
                    st.error(f"解除失敗：{_error_text(error)}")
                else:
                    st.success(f"解除結果：{result.get('result')}")
                    st.rerun()


def show() -> None:
    st.title(title)
    st.caption("CLIENT、RETURN、SUBSIDY、STAFF 與 COMMON 警示的人工檢視入口。")
    filter_left, filter_right, filter_domain = st.columns(3)
    with filter_left:
        status = st.selectbox("狀態", _STATUSES, format_func=lambda value: value or "全部")
    with filter_right:
        alert_code = st.text_input("警示代碼")
    with filter_domain:
        source_domain = st.text_input("來源領域")
    limit = st.number_input("每頁筆數", min_value=1, max_value=200, value=50)

    params = {"limit": int(limit), "offset": 0}
    if status:
        params["status"] = status
    if alert_code.strip():
        params["alert_code"] = alert_code.strip()
    if source_domain.strip():
        params["source_domain"] = source_domain.strip()

    try:
        alerts = _api_request("", params=params)
    except (requests.RequestException, ValueError) as error:
        st.error(f"無法讀取帳務警示：{_error_text(error)}")
        return

    st.dataframe(alerts, hide_index=True, width="stretch")
    if not alerts:
        st.info("目前沒有符合條件的警示。")
        return

    options = [None, *[alert["id"] for alert in alerts]]
    selected_id = st.selectbox(
        "選擇要檢視的警示",
        options,
        format_func=lambda value: "請選擇警示" if value is None else f"警示 #{value}",
    )
    if selected_id is None:
        return

    try:
        alert = _api_request(f"/{selected_id}")
    except (requests.RequestException, ValueError) as error:
        st.error(f"無法讀取警示詳情：{_error_text(error)}")
        return
    _render_alert_detail(alert)
    _render_actions(alert)
