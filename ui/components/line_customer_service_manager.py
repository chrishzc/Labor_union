"""Thin Streamlit editor for static customer-service presentation settings."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError
from ui.components.line_ui_support import has_capability


def render_customer_service_manager(client, token, profile: dict[str, Any]) -> None:
    st.subheader("客服入口設定")
    st.caption("設定客服顯示文字與服務時間；訂單、配對與客服狀態仍由後端正式流程管理。")
    try:
        config = client.customer_service_config(token)
    except LineAdminApiError as error:
        st.error(f"無法載入客服設定：{error}")
        return
    can_edit = has_capability(profile, "line.config.manage")
    settings = config["settings"]
    messages = config["default_messages"]
    submitted, form_values = _customer_service_form(settings, messages, can_edit)
    if not submitted:
        return
    _save_customer_service(client, token, config, form_values)


def _customer_service_form(settings, messages, can_edit: bool) -> tuple[bool, dict]:
    with st.form("customer_service_settings"):
        timeout = st.number_input(
            "客服閒置提醒分鐘數",
            min_value=1,
            value=int(settings["idle_timeout_minutes"]),
            disabled=not can_edit,
        )
        waiting = st.text_area("等待客服時顯示", messages.get("waiting", ""), disabled=not can_edit)
        offline = st.text_area("非服務時間顯示", messages.get("offline", ""), disabled=not can_edit)
        resolved = st.text_area("服務完成時顯示", messages.get("resolved", ""), disabled=not can_edit)
        submitted = st.form_submit_button("儲存客服設定", disabled=not can_edit)
    return submitted, {
        "idle_timeout_minutes": int(timeout),
        "waiting": waiting.strip(),
        "offline": offline.strip(),
        "resolved": resolved.strip(),
    }


def _save_customer_service(client, token, config: dict, form_values: dict) -> None:
    settings = config["settings"]
    messages = config["default_messages"]
    updated = dict(config)
    updated["settings"] = {
        **settings,
        "idle_timeout_minutes": form_values["idle_timeout_minutes"],
    }
    updated["default_messages"] = {
        **messages,
        "waiting": form_values["waiting"],
        "offline": form_values["offline"],
        "resolved": form_values["resolved"],
    }
    try:
        client.update_customer_service_config(token, updated)
    except LineAdminApiError as error:
        st.error(f"儲存失敗：{error}")
        return
    st.success("客服設定已儲存。")


__all__ = ["render_customer_service_manager"]
