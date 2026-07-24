"""LINE message-template CRUD, validation and preview component."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from typing import Any

import pandas as pd
import streamlit as st

from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError


SELECTED_KEY = "line_message_template_selected"
NEW_SEED_KEY = "line_message_template_new_seed"
DELETE_KEY = "line_message_template_delete_pending"
PREVIEW_KEY = "line_message_template_preview"
FLASH_KEY = "line_message_template_flash"

CATEGORIES = ["webhook_reply", "push", "scheduled_push", "customer_service"]
USAGES = ["webhook", "push", "schedule", "customer_service"]
EDIT_ROLES = {"line_manager", "system_admin"}


def _empty_template() -> dict[str, Any]:
    return {
        "id": "new_template",
        "name": "新訊息範本",
        "category": "webhook_reply",
        "message_type": "text",
        "enabled": True,
        "content": "",
        "variables": [],
        "usage": ["webhook"],
    }


def _copy_id(source_id: str, existing_ids: set[str]) -> str:
    base = f"{source_id}_copy"
    candidate = base
    index = 2
    while candidate in existing_ids:
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def _clean_cell(value: Any, default: str = "") -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    return str(value).strip()


def _payload_from_form(
    *,
    template_id: str,
    name: str,
    category: str,
    message_type: str,
    enabled: bool,
    content_source: str,
    usage: list[str],
    variable_rows: pd.DataFrame,
) -> dict[str, Any]:
    content: str | dict[str, Any]
    if message_type == "flex":
        content = json.loads(content_source)
        if not isinstance(content, dict):
            raise ValueError("Flex Message 內容必須是 JSON object")
    else:
        content = content_source

    variables = []
    for row in variable_rows.to_dict("records"):
        variable_name = _clean_cell(row.get("name"))
        if not variable_name:
            continue
        variables.append(
            {
                "name": variable_name,
                "required": bool(row.get("required", True)),
                "description": _clean_cell(row.get("description")),
            }
        )
    return {
        "id": template_id.strip(),
        "name": name.strip(),
        "category": category,
        "message_type": message_type,
        "enabled": enabled,
        "content": content,
        "variables": variables,
        "usage": usage,
    }


def _render_preview(preview: dict[str, Any] | None) -> None:
    if not preview:
        return
    st.markdown("#### 預覽結果")
    if preview.get("message_type") == "flex":
        st.json(preview.get("content", {}))
        st.caption("5.2 提供結構預覽；LINE 手機版視覺模擬器將於後續優化加入。")
    else:
        st.code(str(preview.get("content", "")), language=None, wrap_lines=True)


def render_message_manager(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict[str, Any],
) -> None:
    st.subheader("訊息管理中心")
    st.caption("管理 Webhook 回覆、主動推播、D+1～D+3 內容與客服常用文字。")

    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        st.success(flash)

    try:
        state = client.message_template_state(token)
    except LineAdminApiError as exc:
        st.error(f"無法載入訊息範本：{exc}")
        return

    revision = state["revision"]
    config = state["config"]
    templates = list(config.get("templates", []))
    by_id = {item["id"]: item for item in templates}
    can_edit = profile.get("role") in EDIT_ROLES

    if not can_edit:
        st.info("目前帳號為唯讀權限，可以查詢與預覽，但不能修改範本。")

    filter_col1, filter_col2, filter_col3 = st.columns([2, 1, 1])
    search = filter_col1.text_input("搜尋", placeholder="名稱或範本 ID")
    category_filter = filter_col2.selectbox("分類", ["全部", *CATEGORIES])
    enabled_filter = filter_col3.selectbox("狀態", ["全部", "啟用", "停用"])

    filtered = []
    for item in templates:
        if search and search.lower() not in f"{item['id']} {item['name']}".lower():
            continue
        if category_filter != "全部" and item["category"] != category_filter:
            continue
        if enabled_filter == "啟用" and not item["enabled"]:
            continue
        if enabled_filter == "停用" and item["enabled"]:
            continue
        filtered.append(item)

    list_col, action_col = st.columns([4, 2])
    option_ids = [item["id"] for item in filtered]
    current = st.session_state.get(SELECTED_KEY)
    if current == "__new__":
        option_ids = ["__new__", *option_ids]
    elif current not in option_ids:
        current = option_ids[0] if option_ids else None
        st.session_state[SELECTED_KEY] = current

    if option_ids:
        selected = list_col.selectbox(
            "選擇範本",
            option_ids,
            index=option_ids.index(current) if current in option_ids else 0,
            format_func=lambda item_id: (
                "➕ 新範本（尚未儲存）"
                if item_id == "__new__"
                else f"{'🟢' if by_id[item_id]['enabled'] else '⚪'} {by_id[item_id]['name']} · {item_id}"
            ),
        )
        st.session_state[SELECTED_KEY] = selected
    else:
        selected = None
        list_col.info("目前篩選條件沒有符合的範本。")

    if action_col.button("新增範本", disabled=not can_edit, use_container_width=True):
        st.session_state[NEW_SEED_KEY] = _empty_template()
        st.session_state[SELECTED_KEY] = "__new__"
        st.session_state.pop(PREVIEW_KEY, None)
        st.rerun()

    if selected and selected != "__new__" and action_col.button(
        "複製範本", disabled=not can_edit, use_container_width=True
    ):
        seed = deepcopy(by_id[selected])
        seed["id"] = _copy_id(seed["id"], set(by_id))
        seed["name"] = f"{seed['name']}（複製）"
        st.session_state[NEW_SEED_KEY] = seed
        st.session_state[SELECTED_KEY] = "__new__"
        st.session_state.pop(PREVIEW_KEY, None)
        st.rerun()

    if selected is None:
        return
    is_new = selected == "__new__"
    item = deepcopy(
        st.session_state.get(NEW_SEED_KEY, _empty_template()) if is_new else by_id[selected]
    )

    st.divider()
    with st.form(f"line_message_template_form_{selected}"):
        identity_col, name_col = st.columns([2, 3])
        template_id = identity_col.text_input(
            "範本 ID",
            value=item["id"],
            disabled=not can_edit or not is_new,
            help="建立後不可更改；只允許小寫英文、數字、底線與連字號。",
        )
        name = name_col.text_input("顯示名稱", value=item["name"], disabled=not can_edit)

        setting_col1, setting_col2, setting_col3 = st.columns(3)
        category = setting_col1.selectbox(
            "分類",
            CATEGORIES,
            index=CATEGORIES.index(item["category"]),
            disabled=not can_edit,
        )
        message_type = setting_col2.selectbox(
            "訊息類型",
            ["text", "flex"],
            index=["text", "flex"].index(item["message_type"]),
            disabled=not can_edit,
        )
        enabled = setting_col3.checkbox("啟用", value=item["enabled"], disabled=not can_edit)

        usage = st.multiselect(
            "使用位置",
            USAGES,
            default=item.get("usage", []),
            disabled=not can_edit,
        )
        content_value = (
            json.dumps(item["content"], ensure_ascii=False, indent=2)
            if isinstance(item["content"], dict)
            else str(item["content"])
        )
        content_source = st.text_area(
            "訊息內容" if message_type == "text" else "Flex Message JSON",
            value=content_value,
            height=220,
            disabled=not can_edit,
        )

        st.markdown("##### 範本變數")
        variable_rows = st.data_editor(
            pd.DataFrame(item.get("variables", []), columns=["name", "required", "description"]),
            num_rows="dynamic" if can_edit else "fixed",
            disabled=not can_edit,
            use_container_width=True,
            key=f"line_template_variables_{selected}",
        )
        default_preview_values = {
            variable.get("name", ""): ""
            for variable in item.get("variables", [])
            if variable.get("name")
        }
        preview_values_source = st.text_area(
            "預覽變數（JSON）",
            value=json.dumps(default_preview_values, ensure_ascii=False, indent=2),
            height=100,
            help='例如：{"name": "王小明", "case_no": "115000001"}',
        )

        button_col1, button_col2 = st.columns(2)
        preview_clicked = button_col1.form_submit_button("預覽", use_container_width=True)
        save_clicked = button_col2.form_submit_button(
            "儲存範本",
            type="primary",
            disabled=not can_edit,
            use_container_width=True,
        )

    if preview_clicked or save_clicked:
        try:
            payload = _payload_from_form(
                template_id=template_id,
                name=name,
                category=category,
                message_type=message_type,
                enabled=enabled,
                content_source=content_source,
                usage=usage,
                variable_rows=variable_rows,
            )
            preview_values = json.loads(preview_values_source or "{}")
            if not isinstance(preview_values, dict):
                raise ValueError("預覽變數必須是 JSON object")
            preview_values = {str(key): str(value) for key, value in preview_values.items()}
        except (ValueError, json.JSONDecodeError) as exc:
            st.error(f"格式錯誤：{exc}")
        else:
            if preview_clicked:
                try:
                    st.session_state[PREVIEW_KEY] = client.preview_message_template(
                        token, payload, preview_values
                    )
                except LineAdminApiError as exc:
                    st.error(f"預覽失敗：{exc}")
            if save_clicked:
                try:
                    if is_new:
                        client.create_message_template(token, payload, revision=revision)
                    else:
                        client.update_message_template(
                            token, selected, payload, revision=revision
                        )
                except LineAdminApiError as exc:
                    st.error(f"儲存失敗：{exc}")
                else:
                    st.session_state[SELECTED_KEY] = payload["id"]
                    st.session_state.pop(NEW_SEED_KEY, None)
                    st.session_state.pop(PREVIEW_KEY, None)
                    st.session_state[FLASH_KEY] = f"已儲存「{payload['name']}」"
                    st.rerun()

    _render_preview(st.session_state.get(PREVIEW_KEY))

    if not is_new and can_edit:
        st.divider()
        if st.session_state.get(DELETE_KEY) != selected:
            if st.button("刪除這個範本", type="secondary"):
                st.session_state[DELETE_KEY] = selected
                st.rerun()
        else:
            st.warning(f"確定刪除「{item['name']}」？此操作無法從管理介面復原。")
            confirm_col, cancel_col = st.columns(2)
            if confirm_col.button("確認刪除", type="primary", use_container_width=True):
                try:
                    client.delete_message_template(token, selected, revision=revision)
                except LineAdminApiError as exc:
                    st.error(f"刪除失敗：{exc}")
                else:
                    st.session_state.pop(DELETE_KEY, None)
                    st.session_state.pop(SELECTED_KEY, None)
                    st.session_state.pop(PREVIEW_KEY, None)
                    st.session_state[FLASH_KEY] = f"已刪除「{item['name']}」"
                    st.rerun()
            if cancel_col.button("取消", use_container_width=True):
                st.session_state.pop(DELETE_KEY, None)
                st.rerun()
