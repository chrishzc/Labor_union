"""Rich Menu configuration, preview, image upload and publication UI."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from ui.services.line_api_client import LineAdminApiClient, LineAdminApiError


EDIT_ROLES = {"line_manager", "system_admin"}
FLASH_KEY = "line_rich_menu_flash"
PREVIEW_KEY = "line_rich_menu_preview"
TAIPEI = ZoneInfo("Asia/Taipei")


def _button_rows(menu: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for button in menu["buttons"]:
        action = button["action"]
        value = action.get("text") or action.get("data") or action.get("uri") or ""
        rows.append(
            {
                "id": button["id"],
                "label": button["label"],
                "text_color": button.get("text_color", "#FFFFFF"),
                "background_color": button.get("background_color", "#4A90E2"),
                "x": button["bounds"]["x"],
                "y": button["bounds"]["y"],
                "width": button["bounds"]["width"],
                "height": button["bounds"]["height"],
                "action_type": action["type"],
                "uri_source": action.get("uri_source", "literal"),
                "action_value": value,
            }
        )
    return pd.DataFrame(rows)


def _build_menu_from_editor(
    *,
    original: dict[str, Any],
    name: str,
    audience_role: str,
    enabled: bool,
    selected: bool,
    set_as_default: bool,
    chat_bar_text: str,
    height: int,
    background_color: str,
    image_mode: str,
    rows: pd.DataFrame,
) -> dict[str, Any]:
    menu = deepcopy(original)
    menu.update(
        {
            "name": name.strip(),
            "audience_role": audience_role,
            "enabled": enabled,
            "selected": selected,
            "set_as_default": set_as_default,
            "chat_bar_text": chat_bar_text.strip(),
            "size": {"width": 2500, "height": int(height)},
        }
    )
    appearance = deepcopy(menu.get("appearance", {}))
    appearance["background_color"] = background_color
    appearance["image_mode"] = image_mode
    if image_mode == "generated":
        appearance["image_asset_id"] = None
    menu["appearance"] = appearance

    buttons = []
    for record in rows.to_dict("records"):
        if pd.isna(record.get("id")) or not str(record.get("id") or "").strip():
            continue
        action_type = str(record.get("action_type") or "message")
        uri_source = str(record.get("uri_source") or "literal")
        value = str(record.get("action_value") or "").strip()
        action = {
            "type": action_type,
            "text": value if action_type == "message" else None,
            "data": value if action_type == "postback" else None,
            "uri": value if action_type == "uri" and value else None,
            "uri_source": uri_source if action_type == "uri" else "literal",
        }
        buttons.append(
            {
                "id": str(record["id"]).strip(),
                "label": str(record.get("label") or "").strip(),
                "text_color": str(record.get("text_color") or "#FFFFFF"),
                "background_color": str(
                    record.get("background_color") or "#4A90E2"
                ),
                "bounds": {
                    "x": int(record.get("x") or 0),
                    "y": int(record.get("y") or 0),
                    "width": int(record.get("width") or 0),
                    "height": int(record.get("height") or 0),
                },
                "action": action,
            }
        )
    menu["buttons"] = buttons
    return menu


def _replace_menu(config: dict[str, Any], updated: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(config)
    result["menus"] = [
        updated if item["id"] == updated["id"] else item for item in result["menus"]
    ]
    return result


def _taipei_time(value: Any) -> str:
    if not value:
        return "-"
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M:%S")


def render_rich_menu_manager(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict[str, Any],
) -> None:
    st.subheader("Rich Menu 管理")
    st.caption("草稿儲存與發布分開；此頁不會固定輪詢發布狀態。")
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        st.success(flash)
    can_edit = profile.get("role") in EDIT_ROLES

    try:
        state = client.line_menu_state(token)
    except LineAdminApiError as exc:
        st.error(f"無法載入 Rich Menu：{exc}")
        return
    config = state["config"]
    menus = config.get("menus", [])
    if not menus:
        st.warning("目前沒有 Rich Menu 設定。")
        return

    selected_id = st.selectbox(
        "角色選單",
        [item["id"] for item in menus],
        format_func=lambda value: next(
            f"{item['name']}（{item['audience_role']}）"
            for item in menus
            if item["id"] == value
        ),
    )
    selected_menu = next(item for item in menus if item["id"] == selected_id)
    if not can_edit:
        st.info("目前帳號可查看與預覽，但不能儲存或發布。")

    with st.form(f"rich_menu_editor_{selected_id}"):
        left, right = st.columns(2)
        name = left.text_input("選單名稱", value=selected_menu["name"], disabled=not can_edit)
        audience_role = right.selectbox(
            "對應角色",
            ["customer", "staff", "union_staff"],
            index=["customer", "staff", "union_staff"].index(
                selected_menu["audience_role"]
            ),
            disabled=not can_edit,
        )
        col1, col2, col3 = st.columns(3)
        enabled = col1.checkbox("啟用", value=selected_menu["enabled"], disabled=not can_edit)
        selected = col2.checkbox(
            "開啟聊天室時展開", value=selected_menu["selected"], disabled=not can_edit
        )
        set_as_default = col3.checkbox(
            "設為官方帳號預設選單",
            value=selected_menu["set_as_default"],
            disabled=not can_edit,
        )
        col4, col5 = st.columns(2)
        chat_bar_text = col4.text_input(
            "聊天列文字",
            value=selected_menu["chat_bar_text"],
            max_chars=14,
            disabled=not can_edit,
        )
        heights = [843, 1686]
        height = col5.selectbox(
            "選單高度",
            heights,
            index=heights.index(selected_menu["size"]["height"]),
            disabled=not can_edit,
        )
        appearance = selected_menu.get("appearance", {})
        color_col, mode_col = st.columns(2)
        background_color = color_col.color_picker(
            "背景顏色",
            value=appearance.get("background_color", "#F5F5F5"),
            disabled=not can_edit,
        )
        modes = ["generated", "uploaded"]
        image_mode = mode_col.radio(
            "圖片模式",
            modes,
            index=modes.index(appearance.get("image_mode", "generated")),
            horizontal=True,
            disabled=not can_edit,
        )
        st.markdown("#### 按鈕與 Action")
        rows = st.data_editor(
            _button_rows(selected_menu),
            num_rows="dynamic" if can_edit else "fixed",
            disabled=not can_edit,
            use_container_width=True,
            column_config={
                "action_type": st.column_config.SelectboxColumn(
                    "Action", options=["message", "uri", "postback"], required=True
                ),
                "uri_source": st.column_config.SelectboxColumn(
                    "網址來源", options=["literal", "liff"], required=True
                ),
                "action_value": st.column_config.TextColumn(
                    "文字／網址／Postback Data"
                ),
            },
            key=f"rich_menu_buttons_{selected_id}",
        )
        preview_col, save_col = st.columns(2)
        preview_clicked = preview_col.form_submit_button(
            "產生預覽", use_container_width=True
        )
        save_clicked = save_col.form_submit_button(
            "儲存草稿", type="primary", disabled=not can_edit, use_container_width=True
        )

    if preview_clicked or save_clicked:
        try:
            draft = _build_menu_from_editor(
                original=selected_menu,
                name=name,
                audience_role=audience_role,
                enabled=enabled,
                selected=selected,
                set_as_default=set_as_default,
                chat_bar_text=chat_bar_text,
                height=height,
                background_color=background_color,
                image_mode=image_mode,
                rows=rows,
            )
            preview = client.preview_line_menu(token, draft)
        except (ValueError, LineAdminApiError) as exc:
            st.error(f"Rich Menu 格式錯誤：{exc}")
        else:
            st.session_state[PREVIEW_KEY] = preview
            if save_clicked:
                try:
                    client.update_line_menus(
                        token,
                        _replace_menu(config, draft),
                        revision=state["revision"],
                    )
                except LineAdminApiError as exc:
                    st.error(f"儲存失敗：{exc}")
                else:
                    st.session_state[FLASH_KEY] = "Rich Menu 草稿已儲存，尚未發布至 LINE。"
                    st.rerun()

    preview = st.session_state.get(PREVIEW_KEY)
    if preview:
        st.markdown("#### 圖片預覽")
        st.image(preview, use_container_width=True)

    st.markdown("#### 自訂圖片")
    st.caption(
        f"目前圖片資產：{appearance.get('image_asset_id') or '未指定'}。"
        "上傳成功後會把草稿切換為 uploaded 模式。"
    )
    uploaded = st.file_uploader(
        "上傳 JPEG／PNG",
        type=["jpg", "jpeg", "png"],
        disabled=not can_edit,
        key=f"rich_menu_upload_{selected_id}",
    )
    if st.button("上傳並套用至草稿", disabled=not can_edit or uploaded is None):
        try:
            asset = client.upload_line_menu_image(
                token,
                selected_id,
                filename=uploaded.name,
                content=uploaded.getvalue(),
                content_type=uploaded.type or "application/octet-stream",
            )
            updated = deepcopy(selected_menu)
            updated["appearance"]["image_mode"] = "uploaded"
            updated["appearance"]["image_asset_id"] = asset["id"]
            client.update_line_menus(
                token,
                _replace_menu(config, updated),
                revision=state["revision"],
            )
        except LineAdminApiError as exc:
            st.error(f"圖片上傳失敗：{exc}")
        else:
            st.session_state[FLASH_KEY] = f"圖片資產 #{asset['id']} 已套用至草稿。"
            st.rerun()

    st.markdown("#### 發布至 LINE")
    st.warning("發布會建立新的 LINE Rich Menu；草稿必須先儲存。")
    reason = st.text_input("發布原因（選填，會記錄於稽核）", key=f"publish_reason_{selected_id}")
    confirmed = st.checkbox(
        "我確認要發布目前已儲存的版本",
        key=f"publish_confirm_{selected_id}",
    )
    if st.button(
        "建立發布工作",
        type="primary",
        disabled=not can_edit or not confirmed,
    ):
        try:
            publication = client.publish_line_menu(token, selected_id, reason=reason)
        except LineAdminApiError as exc:
            st.error(f"無法建立發布工作：{exc}")
        else:
            st.session_state[FLASH_KEY] = f"發布工作 #{publication['id']} 已建立。"
            st.rerun()

    st.markdown("#### 發布紀錄")
    if st.button("重新整理發布紀錄"):
        st.rerun()
    try:
        history = client.line_menu_publications(token, menu_id=selected_id)
    except LineAdminApiError as exc:
        st.error(f"無法載入發布紀錄：{exc}")
        return
    if not history["items"]:
        st.caption("此選單尚無發布紀錄。")
        return
    table = [
        {
            "ID": item["id"],
            "狀態": item["status"],
            "目前版本": "是" if item["is_current"] else "否",
            "LINE Menu ID": item.get("line_rich_menu_id") or "",
            "錯誤": item.get("error_code") or "",
            "建立時間（台北）": _taipei_time(item.get("created_at")),
            "發布時間（台北）": _taipei_time(item.get("published_at")),
        }
        for item in history["items"]
    ]
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
    failed = [item for item in history["items"] if item["status"] == "failed"]
    if failed and can_edit:
        retry_id = st.selectbox(
            "選擇失敗工作",
            [item["id"] for item in failed],
            format_func=lambda value: f"#{value}",
        )
        retry_reason = st.text_input("重試原因", key=f"retry_reason_{retry_id}")
        retry_confirmed = st.checkbox("我確認重新執行此發布工作")
        if st.button("重新排入發布", disabled=not retry_confirmed):
            try:
                client.retry_line_menu_publication(
                    token, retry_id, reason=retry_reason
                )
            except LineAdminApiError as exc:
                st.error(f"重新排入失敗：{exc}")
            else:
                st.session_state[FLASH_KEY] = f"發布工作 #{retry_id} 已重新排入。"
                st.rerun()
