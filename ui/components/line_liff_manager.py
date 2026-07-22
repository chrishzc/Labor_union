"""LIFF theme, page text, navigation and dynamic-field management UI."""

from __future__ import annotations

import html
import json
from copy import deepcopy
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ui.services.line_api_client import LineAdminApiClient, LineAdminApiError


EDIT_ROLES = {"line_manager", "system_admin"}
FLASH_KEY = "line_liff_flash"
PAGE_LABELS = {
    "gateway": "入口選擇頁",
    "bind": "舊客戶綁定頁",
    "registration": "新客戶登記頁",
}
FIELD_TYPES = [
    "text",
    "textarea",
    "phone",
    "email",
    "date",
    "number",
    "single_choice",
    "multiple_choice",
    "boolean",
]


def _field_rows(page: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": field["id"],
                "label": field["label"],
                "type": field["type"],
                "required": field.get("required", False),
                "enabled": field.get("enabled", True),
                "order": field.get("order", 0),
                "placeholder": field.get("placeholder", ""),
                "help_text": field.get("help_text", ""),
                "system_field": field.get("system_field", False),
                "options_json": json.dumps(
                    field.get("options", []), ensure_ascii=False
                ),
            }
            for field in page.get("fields", [])
        ]
    )


def _action_rows(page: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(page.get("actions", []))


def _content_rows(page: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"key": key, "text": value} for key, value in page.get("content", {}).items()]
    )


def _clean(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _build_page(
    original: dict[str, Any],
    *,
    title: str,
    subtitle: str,
    submit_button: str,
    success_title: str,
    success_description: str,
    loading_text: str,
    content_rows: pd.DataFrame,
    action_rows: pd.DataFrame | None,
    field_rows: pd.DataFrame | None,
) -> dict[str, Any]:
    page = deepcopy(original)
    page.update(
        {
            "title": title.strip(),
            "subtitle": subtitle.strip(),
            "submit_button": submit_button.strip(),
            "success_title": success_title.strip(),
            "success_description": success_description.strip(),
            "loading_text": loading_text.strip(),
        }
    )
    page["content"] = {
        _clean(row.get("key")): _clean(row.get("text"))
        for row in content_rows.to_dict("records")
        if _clean(row.get("key"))
    }
    if action_rows is not None:
        page["actions"] = [
            {
                "id": _clean(row.get("id")),
                "label": _clean(row.get("label")),
                "description": _clean(row.get("description")),
                "icon": _clean(row.get("icon")),
                "path": _clean(row.get("path")),
                "enabled": bool(row.get("enabled", True)),
                "order": int(row.get("order") or 0),
            }
            for row in action_rows.to_dict("records")
            if _clean(row.get("id"))
        ]
    if field_rows is not None:
        original_system = {
            item["id"]: item for item in original.get("fields", []) if item.get("system_field")
        }
        fields = []
        seen: set[str] = set()
        for row in field_rows.to_dict("records"):
            field_id = _clean(row.get("id"))
            if not field_id or field_id in seen:
                continue
            seen.add(field_id)
            protected = original_system.get(field_id)
            options_text = _clean(row.get("options_json")) or "[]"
            options = json.loads(options_text)
            if not isinstance(options, list):
                raise ValueError(f"{field_id} 的 options_json 必須是 JSON 陣列")
            field = {
                "id": field_id,
                "label": _clean(row.get("label")),
                "type": _clean(row.get("type")) or "text",
                "required": bool(row.get("required", False)),
                "enabled": bool(row.get("enabled", True)),
                "order": int(row.get("order") or 0),
                "placeholder": _clean(row.get("placeholder")),
                "help_text": _clean(row.get("help_text")),
                "system_field": False,
                "options": options,
            }
            if protected:
                field.update(
                    {
                        "id": protected["id"],
                        "type": protected["type"],
                        "required": True,
                        "enabled": True,
                        "system_field": True,
                    }
                )
            fields.append(field)
        for field_id, protected in original_system.items():
            if field_id not in seen:
                fields.append(deepcopy(protected))
        page["fields"] = sorted(fields, key=lambda item: item["order"])
    return page


def _preview(theme: dict[str, Any], page: dict[str, Any]) -> None:
    fields = "".join(
        f"<label>{html.escape(field['label'])}</label>"
        f"<div class='input'>{html.escape(field.get('placeholder') or field['type'])}</div>"
        for field in sorted(page.get("fields", []), key=lambda item: item["order"])
        if field.get("enabled", True)
    )
    actions = "".join(
        f"<div class='action'><b>{html.escape(action.get('icon', ''))} "
        f"{html.escape(action['label'])}</b><small>{html.escape(action.get('description', ''))}</small></div>"
        for action in sorted(page.get("actions", []), key=lambda item: item["order"])
        if action.get("enabled", True)
    )
    body = actions or fields or "<p>此頁沒有可顯示的欄位。</p>"
    components.html(
        f"""
        <style>
          body {{ margin:0; padding:16px; background:{theme['background']};
                  font-family:{theme['font_family']}; color:{theme['text_color']}; }}
          .phone {{ max-width:360px; margin:auto; padding:22px; border-radius:20px; background:#ffffffdd;
                    box-shadow:0 8px 24px #00000018; border-top:6px solid {theme['primary_color']}; }}
          h2 {{ margin:0 0 8px; }} p {{ color:{theme['muted_text_color']}; }}
          label {{ display:block; font-weight:600; margin-top:12px; }}
          .input {{ border:1px solid #ccd6e0; border-radius:8px; padding:10px; color:#789; margin-top:4px; }}
          .action {{ padding:14px; border:1px solid #dce4ec; border-radius:12px; margin:10px 0; }}
          small {{ display:block; color:{theme['muted_text_color']}; margin-top:5px; }}
          button {{ width:100%; padding:11px; border:0; border-radius:9px; margin-top:16px;
                    background:{theme['primary_color']}; color:white; font-weight:700; }}
        </style>
        <div class="phone"><h2>{html.escape(page['title'])}</h2>
        <p>{html.escape(page.get('subtitle', ''))}</p>{body}
        {f'<button>{html.escape(page.get("submit_button", "送出"))}</button>' if page['page_type'] != 'navigation' else ''}</div>
        """,
        height=540,
        scrolling=True,
    )


def render_liff_manager(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict[str, Any],
) -> None:
    st.subheader("LIFF 設定")
    st.caption("儲存後，使用者下次開啟或重新整理 LIFF 頁面即套用；不需要另外發布到 LINE。")
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        st.success(flash)
    can_edit = profile.get("role") in EDIT_ROLES
    try:
        state = client.liff_config_state(token)
    except LineAdminApiError as exc:
        st.error(f"無法載入 LIFF 設定：{exc}")
        return
    config = state["config"]
    revision = state["revision"]
    page_id = st.selectbox(
        "編輯頁面",
        list(PAGE_LABELS),
        format_func=lambda value: PAGE_LABELS[value],
    )
    page = config["pages"][page_id]
    if not can_edit:
        st.info("目前帳號只有查看權限。")

    with st.form(f"liff_editor_{page_id}"):
        st.markdown("#### 共用主題")
        theme = config["theme"]
        color1, color2, color3, color4 = st.columns(4)
        primary = color1.color_picker("主要顏色", theme["primary_color"], disabled=not can_edit)
        hover = color2.color_picker("按鈕滑過", theme["primary_hover_color"], disabled=not can_edit)
        text_color = color3.color_picker("文字顏色", theme["text_color"], disabled=not can_edit)
        muted = color4.color_picker("次要文字", theme["muted_text_color"], disabled=not can_edit)
        background = st.text_input("背景（色碼或 linear-gradient）", theme["background"], disabled=not can_edit)
        font_family = st.selectbox(
            "字型",
            ["'Outfit', 'Noto Sans TC', sans-serif", "'Noto Sans TC', sans-serif", "sans-serif"],
            index=["'Outfit', 'Noto Sans TC', sans-serif", "'Noto Sans TC', sans-serif", "sans-serif"].index(theme["font_family"])
            if theme["font_family"] in ["'Outfit', 'Noto Sans TC', sans-serif", "'Noto Sans TC', sans-serif", "sans-serif"] else 0,
            disabled=not can_edit,
        )

        st.markdown(f"#### {PAGE_LABELS[page_id]}")
        title = st.text_input("標題", page["title"], disabled=not can_edit)
        subtitle = st.text_area("說明", page.get("subtitle", ""), disabled=not can_edit)
        col1, col2 = st.columns(2)
        submit_button = col1.text_input("送出按鈕", page.get("submit_button", "送出"), disabled=not can_edit)
        loading_text = col2.text_input("載入文字", page.get("loading_text", ""), disabled=not can_edit)
        success_title = col1.text_input("成功標題", page.get("success_title", ""), disabled=not can_edit)
        success_description = col2.text_area("成功說明", page.get("success_description", ""), disabled=not can_edit)
        st.markdown("##### 其他固定文字")
        content_rows = st.data_editor(
            _content_rows(page),
            num_rows="dynamic" if can_edit else "fixed",
            disabled=not can_edit,
            use_container_width=True,
            key=f"liff_content_{page_id}",
        )
        action_rows = None
        field_rows = None
        if page["page_type"] == "navigation":
            st.markdown("##### 入口卡片")
            action_rows = st.data_editor(
                _action_rows(page),
                num_rows="dynamic" if can_edit else "fixed",
                disabled=not can_edit,
                use_container_width=True,
                key=f"liff_actions_{page_id}",
            )
        else:
            st.markdown("##### 表單欄位")
            st.caption("系統欄位可改顯示文字與順序，但儲存時會保留必要 ID、類型、必填及啟用狀態。")
            field_rows = st.data_editor(
                _field_rows(page),
                num_rows="dynamic" if can_edit else "fixed",
                disabled=not can_edit,
                use_container_width=True,
                column_config={
                    "type": st.column_config.SelectboxColumn("類型", options=FIELD_TYPES, required=True),
                    "options_json": st.column_config.TextColumn("選項 JSON"),
                },
                key=f"liff_fields_{page_id}",
            )
        preview_clicked = st.form_submit_button("驗證並預覽")
        save_clicked = st.form_submit_button("儲存並啟用", type="primary", disabled=not can_edit)

    try:
        updated = deepcopy(config)
        updated["theme"] = {
            "primary_color": primary,
            "primary_hover_color": hover,
            "background": background.strip(),
            "text_color": text_color,
            "muted_text_color": muted,
            "font_family": font_family,
        }
        updated_page = _build_page(
            page,
            title=title,
            subtitle=subtitle,
            submit_button=submit_button,
            success_title=success_title,
            success_description=success_description,
            loading_text=loading_text,
            content_rows=content_rows,
            action_rows=action_rows,
            field_rows=field_rows,
        )
        updated["pages"][page_id] = updated_page
    except (ValueError, json.JSONDecodeError) as exc:
        st.error(f"設定格式錯誤：{exc}")
        return

    if preview_clicked:
        try:
            client.validate_liff_config(token, updated)
        except LineAdminApiError as exc:
            st.error(f"驗證失敗：{exc}")
        else:
            st.success("設定驗證通過，以下為手機版示意預覽。")
            _preview(updated["theme"], updated_page)

    if save_clicked:
        try:
            client.update_liff_config(token, updated, revision=revision)
        except LineAdminApiError as exc:
            if exc.status_code == 409:
                st.warning(f"{exc}，請重新整理後再修改。")
            else:
                st.error(f"儲存失敗：{exc}")
        else:
            st.session_state[FLASH_KEY] = f"{PAGE_LABELS[page_id]}已儲存並啟用。"
            st.rerun()

    with st.expander("版本紀錄與還原"):
        try:
            history = client.liff_config_history(token).get("items", [])
        except LineAdminApiError as exc:
            st.error(f"無法載入版本紀錄：{exc}")
            history = []
        if not history:
            st.caption("尚無歷史版本；第一次修改後會保存修改前快照。")
        else:
            st.dataframe(
                pd.DataFrame(history)[["revision", "created_at", "actor", "reason"]],
                use_container_width=True,
                hide_index=True,
            )
            restore_revision = st.selectbox(
                "選擇要還原的版本",
                [item["revision"] for item in history],
                format_func=lambda value: value[:12],
            )
            restore_reason = st.text_input("還原原因")
            confirmed = st.checkbox("我確認還原會立即影響使用者重新載入的 LIFF 頁面")
            if st.button("還原此版本", disabled=not (can_edit and confirmed)):
                try:
                    client.rollback_liff_config(
                        token,
                        restore_revision,
                        current_revision=revision,
                        reason=restore_reason,
                    )
                except LineAdminApiError as exc:
                    st.error(f"還原失敗：{exc}")
                else:
                    st.session_state[FLASH_KEY] = "LIFF 設定已還原。"
                    st.rerun()
