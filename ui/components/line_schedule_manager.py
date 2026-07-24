"""Editable D+N onboarding schedule management for LINE follow events."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError


FLASH_KEY = "line_schedule_flash"
PREVIEW_KEY = "line_schedule_preview"
EDIT_ROLES = {"line_manager", "system_admin"}


def _build_schedule_payload(
    *,
    config: dict[str, Any],
    schedule_id: str,
    timezone_name: str,
    name: str,
    enabled: bool,
    restart_on_refollow: bool,
    rows: pd.DataFrame,
) -> dict[str, Any]:
    ZoneInfo(timezone_name)
    steps = []
    for row in rows.to_dict("records"):
        if pd.isna(row.get("day")) or not str(row.get("template_id") or "").strip():
            continue
        steps.append(
            {
                "day": int(row["day"]),
                "send_time": str(row.get("send_time") or "").strip(),
                "template_id": str(row["template_id"]).strip(),
            }
        )
    if not steps:
        raise ValueError("排程至少需要一個發送步驟")
    steps.sort(key=lambda item: (item["day"], item["send_time"]))
    if len({item["day"] for item in steps}) != len(steps):
        raise ValueError("同一個排程不能設定重複的 D+天數")

    payload = deepcopy(config)
    payload["timezone"] = timezone_name
    for schedule in payload["schedules"]:
        if schedule["id"] == schedule_id:
            schedule.update(
                {
                    "name": name.strip(),
                    "enabled": enabled,
                    "trigger": "follow",
                    "restart_on_refollow": restart_on_refollow,
                    "steps": steps,
                }
            )
            break
    return payload


def _preview_rows(payload: dict[str, Any], schedule_id: str) -> list[dict[str, Any]]:
    timezone_name = payload["timezone"]
    zone = ZoneInfo(timezone_name)
    now = datetime.now(zone)
    schedule = next(item for item in payload["schedules"] if item["id"] == schedule_id)
    result = []
    for step in schedule["steps"]:
        hour, minute = map(int, step["send_time"].split(":"))
        target = (now + timedelta(days=step["day"])).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        result.append(
            {
                "階段": f"D+{step['day']}",
                "台灣／設定時區時間": target.strftime("%Y-%m-%d %H:%M %Z"),
                "訊息範本": step["template_id"],
                "若時間已過": "到期後由 Worker 立即處理" if target <= now else "等待排程時間",
            }
        )
    return result


def render_schedule_manager(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict[str, Any],
) -> None:
    st.subheader("D+1～D+3 排程設定")
    st.caption("此頁不會固定輪詢；儲存只影響之後新建立的 onboarding 任務。")
    st.info("既有 line_tasks 保存建立當時的時間與訊息，不會因修改此設定而被回溯改寫。")

    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        st.success(flash)

    try:
        state = client.message_schedule_state(token)
        template_state = client.message_template_state(token)
    except LineAdminApiError as exc:
        st.error(f"無法載入排程設定：{exc}")
        return

    config = state["config"]
    schedules = config.get("schedules", [])
    if not schedules:
        st.warning("目前沒有 follow onboarding 排程。")
        return
    enabled_template_ids = [
        item["id"]
        for item in template_state["config"].get("templates", [])
        if item.get("enabled") and "schedule" in item.get("usage", [])
    ]
    can_edit = profile.get("role") in EDIT_ROLES
    schedule_ids = [item["id"] for item in schedules]
    selected_id = st.selectbox(
        "排程",
        schedule_ids,
        format_func=lambda value: next(
            item["name"] for item in schedules if item["id"] == value
        ),
    )
    selected = next(item for item in schedules if item["id"] == selected_id)

    if not can_edit:
        st.info("目前帳號為唯讀權限。")

    with st.form(f"line_schedule_{selected_id}"):
        col1, col2 = st.columns(2)
        name = col1.text_input("排程名稱", value=selected["name"], disabled=not can_edit)
        timezone_name = col2.text_input(
            "時區", value=config.get("timezone", "Asia/Taipei"), disabled=not can_edit
        )
        enabled_col, restart_col = st.columns(2)
        enabled = enabled_col.checkbox("啟用排程", value=selected["enabled"], disabled=not can_edit)
        restart_on_refollow = restart_col.checkbox(
            "解除封鎖／重新加入時重新開始",
            value=selected.get("restart_on_refollow", False),
            disabled=not can_edit,
        )

        rows = st.data_editor(
            pd.DataFrame(selected["steps"], columns=["day", "send_time", "template_id"]),
            num_rows="dynamic" if can_edit else "fixed",
            disabled=not can_edit,
            use_container_width=True,
            column_config={
                "day": st.column_config.NumberColumn("D+天數", min_value=0, max_value=365, step=1),
                "send_time": st.column_config.TextColumn("發送時間 HH:MM"),
                "template_id": st.column_config.SelectboxColumn(
                    "訊息範本", options=enabled_template_ids, required=True
                ),
            },
            key=f"line_schedule_steps_{selected_id}",
        )
        button1, button2 = st.columns(2)
        preview_clicked = button1.form_submit_button("預覽日期", use_container_width=True)
        save_clicked = button2.form_submit_button(
            "儲存排程",
            type="primary",
            disabled=not can_edit,
            use_container_width=True,
        )

    if preview_clicked or save_clicked:
        try:
            payload = _build_schedule_payload(
                config=config,
                schedule_id=selected_id,
                timezone_name=timezone_name.strip(),
                name=name,
                enabled=enabled,
                restart_on_refollow=restart_on_refollow,
                rows=rows,
            )
            preview = _preview_rows(payload, selected_id)
        except Exception as exc:
            st.error(f"排程格式錯誤：{exc}")
        else:
            st.session_state[PREVIEW_KEY] = preview
            if save_clicked:
                try:
                    client.update_message_schedules(
                        token, payload, revision=state["revision"]
                    )
                except LineAdminApiError as exc:
                    st.error(f"儲存失敗：{exc}")
                else:
                    st.session_state[FLASH_KEY] = "排程設定已儲存；只影響之後建立的新任務。"
                    st.rerun()

    preview = st.session_state.get(PREVIEW_KEY)
    if preview:
        st.markdown("#### 排程日期預覽")
        st.dataframe(preview, use_container_width=True, hide_index=True)
