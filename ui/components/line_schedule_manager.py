"""
================================================================================
檔案名稱: ui/components/line_schedule_manager.py
功能說明: LINE 新好友自動通知設定元件，管理加入好友後各天的訊息與發送時間
================================================================================
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError
from ui.components.line_ui_support import has_capability


FLASH_KEY = "line_schedule_flash"
PREVIEW_KEY = "line_schedule_preview"


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
        raise ValueError("自動通知至少需要設定一則訊息")
    steps.sort(key=lambda item: (item["day"], item["send_time"]))
    if len({item["day"] for item in steps}) != len(steps):
        raise ValueError("加入後的同一天不能重複設定")

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


def _preview_rows(
    payload: dict[str, Any],
    schedule_id: str,
    template_names: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
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
                "發送內容": (template_names or {}).get(
                    step["template_id"], step["template_id"]
                ),
                "執行狀態": "時間已到，將儘快發送" if target <= now else "等待發送時間",
            }
        )
    return result


def render_schedule_manager(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict[str, Any],
) -> None:
    st.subheader("新好友自動通知")
    st.caption("設定使用者加入好友後，第幾天、幾點收到哪一則訊息。")
    st.info("修改後只套用到之後新加入的好友；已經排定的通知不會改變。")

    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        st.success(flash)

    try:
        state = client.message_schedule_state(token)
        template_state = client.message_template_state(token)
    except LineAdminApiError as exc:
        st.error(f"無法載入自動通知設定：{exc}")
        return

    config = state["config"]
    schedules = config.get("schedules", [])
    if not schedules:
        st.warning("目前沒有新好友通知設定。")
        return
    template_items = [
        item
        for item in template_state["config"].get("templates", [])
        if item.get("enabled") and "schedule" in item.get("usage", [])
    ]
    template_names: dict[str, str] = {}
    name_to_id: dict[str, str] = {}
    for item in template_items:
        display_name = item["name"]
        suffix = 2
        while display_name in name_to_id:
            display_name = f"{item['name']}（{suffix}）"
            suffix += 1
        template_names[item["id"]] = display_name
        name_to_id[display_name] = item["id"]
    can_edit = has_capability(profile, "line.config.manage")
    schedule_ids = [item["id"] for item in schedules]
    selected_id = st.selectbox(
        "設定名稱",
        schedule_ids,
        format_func=lambda value: next(
            item["name"] for item in schedules if item["id"] == value
        ),
    )
    selected = next(item for item in schedules if item["id"] == selected_id)

    if not can_edit:
        st.info("目前帳號只有查看權限；如需修改，請聯絡 LINE 主管。")

    with st.form(f"line_schedule_{selected_id}"):
        name = selected["name"]
        timezone_name = config.get("timezone", "Asia/Taipei")
        enabled_col, restart_col = st.columns(2)
        enabled = enabled_col.checkbox("啟用自動通知", value=selected["enabled"], disabled=not can_edit)
        restart_on_refollow = restart_col.checkbox(
            "解除封鎖／重新加入時重新開始",
            value=selected.get("restart_on_refollow", False),
            disabled=not can_edit,
        )

        editor_rows = pd.DataFrame(
            [
                {
                    "day": step["day"],
                    "send_time": step["send_time"],
                    "message_name": template_names.get(
                        step["template_id"], "目前使用中的訊息"
                    ),
                }
                for step in selected["steps"]
            ],
            columns=["day", "send_time", "message_name"],
        )
        rows = st.data_editor(
            editor_rows,
            num_rows="dynamic" if can_edit else "fixed",
            disabled=not can_edit,
            width="stretch",
            column_config={
                "day": st.column_config.NumberColumn("加入後第幾天", min_value=0, max_value=365, step=1),
                "send_time": st.column_config.TextColumn("發送時間（例如 10:00）"),
                "message_name": st.column_config.SelectboxColumn(
                    "發送哪一則訊息", options=list(name_to_id), required=True
                ),
            },
            key=f"line_schedule_steps_{selected_id}",
        )
        button1, button2 = st.columns(2)
        preview_clicked = button1.form_submit_button("查看預計時間", width="stretch")
        save_clicked = button2.form_submit_button(
            "儲存自動通知",
            type="primary",
            disabled=not can_edit,
            width="stretch",
        )

    if preview_clicked or save_clicked:
        try:
            payload_rows = rows.rename(columns={"message_name": "template_id"}).copy()
            payload_rows["template_id"] = payload_rows["template_id"].map(name_to_id)
            payload = _build_schedule_payload(
                config=config,
                schedule_id=selected_id,
                timezone_name=timezone_name.strip(),
                name=name,
                enabled=enabled,
                restart_on_refollow=restart_on_refollow,
                rows=payload_rows,
            )
            preview = _preview_rows(payload, selected_id, template_names)
        except Exception as exc:
            st.error(f"通知設定有誤：{exc}")
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
                    st.session_state[FLASH_KEY] = "新好友通知已儲存；只影響之後加入的好友。"
                    st.rerun()

    preview = st.session_state.get(PREVIEW_KEY)
    if preview:
        st.markdown("#### 預計發送時間")
        st.dataframe(preview, width="stretch", hide_index=True)
