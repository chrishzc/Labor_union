"""
================================================================================
檔案名稱: ui/components/line_rich_menu_manager.py
功能說明: LINE Rich Menu 管理元件，使用專用草稿 Preview／確認／Apply 與圖片發布流程
================================================================================
"""

from __future__ import annotations

from io import BytesIO
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from PIL import Image
from streamlit_cropper import st_cropper

from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError
from ui.components.line_ui_support import (
    complete_operation,
    has_capability,
    operation_headers,
)


FLASH_KEY = "line_rich_menu_flash"
PREVIEW_KEY = "line_rich_menu_preview"
DRAFT_PREVIEW_KEY = "line_rich_menu_draft_preview"
PUBLISH_PREVIEW_KEY = "line_rich_menu_publish_preview"
TAIPEI = ZoneInfo("Asia/Taipei")
ROLE_LABELS = {
    "customer": "一般客戶／媽媽",
    "staff": "月嫂",
    "union_staff": "工會人員",
    "union_staff_page": "工會人員分頁",
}
ACTION_LABELS = {
    "message": "傳送一段文字",
    "url": "開啟指定網頁",
    "liff": "開啟 LINE 內的服務頁面",
    "postback": "執行系統功能",
    "richmenuswitch": "切換工會分頁",
}
PUBLICATION_STATUS_LABELS = {
    "draft": "草稿",
    "queued": "等待發布",
    "publishing": "發布中",
    "published": "已發布",
    "publish_retryable_failed": "發布暫時失敗",
    "failed": "發布失敗",
    "rollback_queued": "等待回復",
    "delete_queued": "等待刪除",
    "rollback_retryable_failed": "回復暫時失敗",
    "delete_retryable_failed": "刪除暫時失敗",
    "rolled_back": "已回復",
    "deleted": "已刪除",
}


def _button_rows(menu: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for button in menu["buttons"]:
        action = button["action"]
        value = action.get("text") or action.get("data") or action.get("uri") or ""
        if action.get("type") == "richmenuswitch":
            value = action.get("rich_menu_alias_id") or value
        action_kind = action["type"]
        if action["type"] == "uri":
            action_kind = "liff" if action.get("uri_source") == "liff" else "url"
        rows.append(
            {
                "id": button["id"],
                "label": button["label"],
                "text_color": button.get("text_color", "#FFFFFF"),
                "background_color": button.get("background_color", "#4A90E2"),
                "border_radius": button.get("border_radius", 0),
                "x": button["bounds"]["x"],
                "y": button["bounds"]["y"],
                "width": button["bounds"]["width"],
                "height": button["bounds"]["height"],
                "action_type": action["type"],
                "uri_source": action.get("uri_source", "literal"),
                "action_kind": ACTION_LABELS[action_kind],
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
    has_uploaded_asset = bool(appearance.get("image_asset_id"))
    appearance["image_mode"] = image_mode if image_mode == "generated" or has_uploaded_asset else "generated"
    if appearance["image_mode"] == "generated":
        appearance["image_asset_id"] = None
    menu["appearance"] = appearance

    buttons = []
    for record in rows.to_dict("records"):
        if pd.isna(record.get("id")) or not str(record.get("id") or "").strip():
            continue
        action_label = str(record.get("action_kind") or ACTION_LABELS["message"])
        action_kind = next(
            (key for key, label in ACTION_LABELS.items() if label == action_label),
            "message",
        )
        action_type = "uri" if action_kind in {"url", "liff"} else action_kind
        uri_source = "liff" if action_kind == "liff" else "literal"
        value = str(record.get("action_value") or "").strip()
        action = {
            "type": action_type,
            "text": value if action_type == "message" else None,
            "data": value if action_type == "postback" else None,
            "uri": value if action_type == "uri" and value else None,
            "uri_source": uri_source if action_type == "uri" else "literal",
            "rich_menu_alias_id": value if action_type == "richmenuswitch" else None,
        }
        if action_type == "richmenuswitch":
            action["data"] = f"tab={value}"
        buttons.append(
            {
                "id": str(record["id"]).strip(),
                "label": str(record.get("label") or "").strip(),
                "text_color": str(record.get("text_color") or "#FFFFFF"),
                "background_color": str(
                    record.get("background_color") or "#4A90E2"
                ),
                "border_radius": int(record.get("border_radius") or 0),
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


def _apply_menu_draft(
    client: LineAdminApiClient,
    token: str | None,
    draft_preview: dict[str, Any],
    operation: str,
) -> None:
    definition = draft_preview["definition"]
    identity = operation_headers(operation, definition)
    client.update_line_menus(
        token,
        definition,
        revision=draft_preview["expected_revision"],
        preview_fingerprint=draft_preview["preview_fingerprint"],
        reason="管理員儲存 Rich Menu 設定",
        idempotency_key=identity["Idempotency-Key"],
        correlation_id=identity["X-Correlation-ID"],
    )
    complete_operation(operation)


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
    st.subheader("LINE 聊天室下方選單")
    st.caption("選擇使用者身分後，可修改選單文字、點擊後的動作與圖片。")
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        st.success(flash)
    can_edit = has_capability(profile, "line.config.manage")
    can_publish = has_capability(profile, "line.menu.publish")
    if profile.get("id") is None and not can_publish:
        st.info("開發模式可編輯與預覽；套用到真實 LINE 需要啟用管理員登入。")

    try:
        state = client.line_menu_state(token)
    except LineAdminApiError as exc:
        st.error(f"無法載入 LINE 下方選單：{exc}")
        return
    config = state["config"]
    menus = config.get("menus", [])
    if not menus:
        st.warning("目前沒有 LINE 下方選單設定。")
        return

    selected_id = st.selectbox(
        "選擇要修改的選單",
        [item["id"] for item in menus],
        format_func=lambda value: next(
            f"{item['name']}（{ROLE_LABELS.get(item['audience_role'], '使用者')}）"
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
            "顯示給誰看",
            ["customer", "staff", "union_staff", "union_staff_page"],
            index=["customer", "staff", "union_staff", "union_staff_page"].index(
                selected_menu["audience_role"]
            ),
            format_func=lambda value: ROLE_LABELS[value],
            disabled=not can_edit,
        )
        col1, col2, col3 = st.columns(3)
        enabled = col1.checkbox("啟用", value=selected_menu["enabled"], disabled=not can_edit)
        selected = col2.checkbox(
            "開啟聊天室時展開", value=selected_menu["selected"], disabled=not can_edit
        )
        set_as_default = col3.checkbox(
            "設為新好友預設選單",
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
            "選單大小",
            heights,
            index=heights.index(selected_menu["size"]["height"]),
            format_func=lambda value: "標準" if value == 843 else "大型",
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
            "選單外觀",
            modes,
            index=modes.index(appearance.get("image_mode", "generated")),
            format_func=lambda value: "使用系統配色" if value == "generated" else "使用自訂圖片",
            horizontal=True,
            disabled=not can_edit,
        )
        st.markdown("#### 選單按鈕")
        st.caption("可修改按鈕名稱，以及使用者點下後要傳送文字、開啟網頁或執行功能。")
        rows = st.data_editor(
            _button_rows(selected_menu),
            num_rows="fixed",
            disabled=not can_edit,
            width="stretch",
            column_order=["label", "action_kind", "action_value"],
            column_config={
                "label": st.column_config.TextColumn("按鈕名稱", required=True),
                "action_kind": st.column_config.SelectboxColumn(
                    "點擊後要做什麼",
                    options=list(ACTION_LABELS.values()),
                    required=True,
                ),
                "action_value": st.column_config.TextColumn(
                    "傳送文字或網址"
                ),
            },
            key=f"rich_menu_buttons_{selected_id}",
        )
        preview_col, save_col = st.columns(2)
        preview_clicked = preview_col.form_submit_button(
            "建立草稿預覽", width="stretch"
        )
        save_col.caption(
            "預覽後需在下方明確確認，才可套用草稿。"
        )

    if preview_clicked:
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
            draft_result = client.preview_line_menu_draft(
                token,
                draft,
                revision=state["revision"],
            )
            normalized_definition = draft_result["normalized_definition"]
            preview = client.preview_line_menu(token, normalized_definition)
        except (ValueError, LineAdminApiError) as exc:
            st.error(f"選單內容有問題：{exc}")
        else:
            st.session_state[PREVIEW_KEY] = preview
            st.session_state[DRAFT_PREVIEW_KEY] = {
                "menu_id": selected_id,
                "expected_revision": state["revision"],
                "definition": normalized_definition,
                "preview_fingerprint": draft_result["preview_fingerprint"],
            }
            st.session_state.pop(f"rich_menu_confirm_{selected_id}", None)

    preview = st.session_state.get(PREVIEW_KEY)
    if preview:
        st.markdown("#### 選單預覽")
        st.image(preview, width="stretch")

    draft_preview = st.session_state.get(DRAFT_PREVIEW_KEY)
    if draft_preview and draft_preview.get("menu_id") == selected_id:
        st.warning("已建立伺服器草稿預覽；請確認目前預覽後再套用。")
        confirmed = st.checkbox(
            "我已確認目前 Rich Menu 草稿預覽內容",
            key=f"rich_menu_confirm_{selected_id}",
            disabled=not can_edit,
        )
        if st.button(
            "套用已確認草稿",
            type="primary",
            disabled=not can_edit or not confirmed,
            key=f"rich_menu_apply_{selected_id}",
        ):
            try:
                _apply_menu_draft(
                    client,
                    token,
                    draft_preview,
                    f"rich-menu-config-apply:{selected_id}",
                )
            except LineAdminApiError as exc:
                st.error(f"套用失敗：{exc}")
            else:
                st.session_state.pop(DRAFT_PREVIEW_KEY, None)
                st.session_state.pop(PREVIEW_KEY, None)
                st.session_state.pop(PUBLISH_PREVIEW_KEY, None)
                st.session_state[FLASH_KEY] = "選單草稿已套用，尚未發布到 LINE。"
                st.rerun()

    st.markdown("#### 自訂選單圖片")
    st.caption("若不上傳圖片，系統會依上方顏色自動產生選單；每個選單一次只能套用一張底圖。")
    uploaded = st.file_uploader(
        "上傳 JPEG／PNG",
        type=["jpg", "jpeg", "png"],
        disabled=not can_edit,
        accept_multiple_files=False,
        key=f"rich_menu_upload_{selected_id}",
    )
    cropped_image = None
    if uploaded is not None:
        try:
            source_image = Image.open(uploaded).convert("RGB")
        except Exception:
            st.error("圖片讀取失敗，請重新上傳 JPEG 或 PNG。")
        else:
            st.caption("請拖曳虛線框選擇要套用的範圍，框內就是實際產生的選單底圖。")
            cropped_image = st_cropper(
                source_image,
                realtime_update=True,
                box_color="#FF4B4B",
                aspect_ratio=(2500, 843),
                return_type="image",
                key=f"rich_menu_cropper_{selected_id}_{uploaded.file_id}",
            )
            if cropped_image is not None:
                st.image(cropped_image, caption="裁切後預覽", width="stretch")

    if st.button("確認裁切並套用至選單", disabled=not can_edit or cropped_image is None):
        target_size = (
            int(selected_menu["size"]["width"]),
            int(selected_menu["size"]["height"]),
        )
        final_image = cropped_image.convert("RGB").resize(
            target_size,
            Image.Resampling.LANCZOS,
        )
        buffer = BytesIO()
        final_image.save(buffer, format="PNG")
        try:
            asset = client.upload_line_menu_image(
                token,
                selected_id,
                filename=f"{selected_id}_rich_menu.png",
                content=buffer.getvalue(),
                content_type="image/png",
            )
            updated = deepcopy(selected_menu)
            updated["appearance"]["image_mode"] = "uploaded"
            updated["appearance"]["image_asset_id"] = asset["id"]
            draft_result = client.preview_line_menu_draft(
                token,
                _replace_menu(config, updated),
                revision=state["revision"],
            )
            normalized_definition = draft_result["normalized_definition"]
            st.session_state[PREVIEW_KEY] = client.preview_line_menu(
                token,
                normalized_definition,
            )
            st.session_state[DRAFT_PREVIEW_KEY] = {
                "menu_id": selected_id,
                "expected_revision": state["revision"],
                "definition": normalized_definition,
                "preview_fingerprint": draft_result["preview_fingerprint"],
            }
            st.session_state.pop(f"rich_menu_confirm_{selected_id}", None)
        except (ValueError, LineAdminApiError) as exc:
            st.error(f"圖片上傳失敗：{exc}")
        else:
            st.session_state.pop(PUBLISH_PREVIEW_KEY, None)
            st.session_state[FLASH_KEY] = "自訂圖片已建立草稿預覽；請確認後套用。"

    st.markdown("#### 套用到 LINE")
    st.warning("請先套用已確認草稿、確認預覽，然後建立本次發布確認。")
    publish_preview = st.session_state.get(PUBLISH_PREVIEW_KEY)
    preview_is_current = bool(
        publish_preview and publish_preview.get("menu_id") == selected_id
    )
    if st.button("確認目前預覽，繼續套用", disabled=not can_publish):
        try:
            confirmation = client.create_line_menu_publish_preview(
                token, selected_id
            )
        except LineAdminApiError as exc:
            st.error(f"無法確認目前預覽：{exc}")
        else:
            st.session_state[PUBLISH_PREVIEW_KEY] = {
                "menu_id": selected_id,
                "preview_id": confirmation["preview_id"],
            }
            st.rerun()
    if preview_is_current:
        st.success("已確認目前版本的預覽；請再次勾選後套用。")
    else:
        st.info("先按「確認目前預覽，繼續套用」，才能啟用套用按鈕。")
    reason = st.text_input("本次修改備註（選填）", key=f"publish_reason_{selected_id}")
    confirmed = st.checkbox(
        "我已確認選單內容，要套用到 LINE",
        key=f"publish_confirm_{selected_id}",
    )
    if st.button(
        "套用到 LINE",
        type="primary",
        disabled=not can_publish or not preview_is_current or not confirmed,
    ):
        operation = f"rich-menu-publish:{selected_id}"
        request_identity = operation_headers(
            operation,
            {"menu_id": selected_id, "reason": reason},
        )
        try:
            client.publish_line_menu(
                token,
                selected_id,
                preview_id=publish_preview["preview_id"],
                reason=reason,
                idempotency_key=request_identity["Idempotency-Key"],
                correlation_id=request_identity["X-Correlation-ID"],
            )
        except LineAdminApiError as exc:
            st.error(f"無法建立發布工作：{exc}")
        else:
            complete_operation(operation)
            st.session_state.pop(PUBLISH_PREVIEW_KEY, None)
            st.session_state[FLASH_KEY] = "選單已排入套用流程，請稍後重新整理查看結果。"
            st.rerun()

    st.markdown("#### 套用紀錄")
    if st.button("重新整理紀錄"):
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
            "狀態": PUBLICATION_STATUS_LABELS.get(item["status"], item["status"]),
            "設定版本": item["configuration_revision"],
            "工作編號": item["id"],
        }
        for item in history["items"]
    ]
    st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)
    retryable_statuses = {"failed", "publish_retryable_failed"}
    failed = [item for item in history["items"] if item["status"] in retryable_statuses]
    if failed and can_publish:
        retry_id = st.selectbox(
            "選擇要重新套用的紀錄",
            [item["id"] for item in failed],
            format_func=lambda value: next(
                f"工作 {item['id']}（設定版本 {item['configuration_revision']}）"
                for item in failed
                if item["id"] == value
            ),
        )
        retry_reason = st.text_input("處理備註", key=f"retry_reason_{retry_id}")
        retry_confirmed = st.checkbox("我確認要重新套用這個選單")
        if st.button("重新套用", disabled=not retry_confirmed):
            operation = f"rich-menu-retry:{retry_id}"
            request_identity = operation_headers(
                operation,
                {"publication_id": retry_id, "reason": retry_reason},
            )
            try:
                client.retry_line_menu_publication(
                    token,
                    retry_id,
                    reason=retry_reason,
                    idempotency_key=request_identity["Idempotency-Key"],
                    correlation_id=request_identity["X-Correlation-ID"],
                )
            except LineAdminApiError as exc:
                st.error(f"重新排入失敗：{exc}")
            else:
                complete_operation(operation)
                st.session_state[FLASH_KEY] = "選單已重新排入套用流程。"
                st.rerun()
