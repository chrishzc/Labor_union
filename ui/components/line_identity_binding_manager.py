"""Thin Streamlit UI for querying, correcting, and revoking LINE identities."""

from __future__ import annotations

from uuid import uuid4

import pandas as pd
import streamlit as st

from ui.api_clients.line_api_client import LineAdminApiError
from ui.api_clients.line_identity_binding_api_client import LineIdentityBindingApiClient
from ui.components.line_ui_support import has_capability


_TYPE_LABELS = {"customer": "一般用戶", "staff": "月嫂", "admin": "工會人員"}
_STATUS_LABELS = {
    "bound": "已綁定",
    "revocation_pending": "解除中",
    "revoked": "已解除",
    "pending_review": "待審核",
    "unbound": "未綁定",
}
_BLOCKER_LABELS = {
    "line_identity_binding_not_bound": "此身分目前不是已綁定狀態",
    "line_identity_default_menu_not_published": "找不到已發布的一般用戶 Rich Menu",
    "line_identity_subject_unchanged": "新綁定對象與目前相同",
    "line_identity_replacement_subject_not_found": "找不到新的綁定對象",
    "line_identity_replacement_subject_already_bound": "新的綁定對象已有 LINE 身分",
}


# Kept cohesive because Streamlit widget order defines the page's session-state lifecycle.
def render_identity_binding_manager(transport, token, profile) -> None:
    st.subheader("LINE 身分查詢／編輯")
    st.caption("查詢所有 LINE 綁定；更正綁定對象或解除身分都會保留完整歷史。")
    client = LineIdentityBindingApiClient(transport)
    status_label, subject_label, search = _filters()
    try:
        page = client.bindings(
            token,
            {
                "status": _value_for_label(_STATUS_LABELS, status_label),
                "subject_type": _value_for_label(_TYPE_LABELS, subject_label),
                "search": search,
                "page": 1,
                "page_size": 100,
            },
        )
    except LineAdminApiError as error:
        st.error(f"無法載入 LINE 身分：{error}")
        return
    if not page.items:
        st.info("目前沒有符合條件的 LINE 身分。")
        return
    _render_table(page)
    binding = _selected_binding(page)
    _render_detail(binding)
    if not has_capability(profile, "line.identity.binding.manage"):
        st.info("目前帳號只有查詢權限。")
        return
    replacement_tab, revocation_tab = st.tabs(["更正綁定對象", "解除身分"])
    with replacement_tab:
        _render_replacement(client, token, binding)
    with revocation_tab:
        _render_revocation(client, token, profile, binding)


def _filters():
    columns = st.columns(3)
    status = columns[0].selectbox("綁定狀態", ["全部", *_STATUS_LABELS.values()])
    subject = columns[1].selectbox("身分類型", ["全部", *_TYPE_LABELS.values()])
    search = columns[2].text_input("搜尋 User ID／姓名")
    return status, subject, search


def _render_table(page) -> None:
    rows = [
        {
            "LINE User ID": item.line_user_id,
            "身分": _TYPE_LABELS.get(item.subject_type, item.subject_type),
            "綁定對象": item.subject_name,
            "資料 ID": item.subject_reference,
            "狀態": _STATUS_LABELS.get(item.status, item.status),
            "版本": item.version,
        }
        for item in page.items
    ]
    st.caption(f"共 {page.total} 筆")
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _selected_binding(page):
    selected = st.selectbox(
        "選擇要管理的 LINE 身分",
        [item.line_user_id for item in page.items],
        format_func=lambda value: next(
            f"{item.subject_name} · {_TYPE_LABELS.get(item.subject_type, item.subject_type)} · {value}"
            for item in page.items
            if item.line_user_id == value
        ),
    )
    return next(item for item in page.items if item.line_user_id == selected)


def _render_detail(binding) -> None:
    st.markdown("#### 身分詳細資料")
    st.json(
        {
            "LINE User ID": binding.line_user_id,
            "身分": _TYPE_LABELS.get(binding.subject_type, binding.subject_type),
            "綁定對象": binding.subject_name,
            "資料 ID": binding.subject_reference,
            "狀態": _STATUS_LABELS.get(binding.status, binding.status),
            "版本": binding.version,
            "解除工作": binding.revocation_status or "-",
            "解除時間": str(binding.revoked_at or "-"),
        }
    )


# Kept cohesive because preview state and the apply confirmation share one widget lifecycle.
def _render_replacement(client, token, binding) -> None:
    if binding.status != "bound":
        st.info("只有已綁定身分可以更正綁定對象。")
        return
    target = st.text_input("新的資料 ID", key=f"identity_replace_target_{binding.line_user_id}")
    reason = st.text_area("更正原因", key=f"identity_replace_reason_{binding.line_user_id}")
    preview_key = f"identity_replace_preview_state_{binding.line_user_id}"
    if st.button("預覽更正", key=f"identity_replace_preview_{binding.line_user_id}"):
        if not target.strip():
            st.error("請輸入新的資料 ID。")
            return
        try:
            st.session_state[preview_key] = client.replacement_preview(
                token,
                binding.line_user_id,
                target.strip(),
            )
        except LineAdminApiError as error:
            st.error(f"無法預覽更正：{error}")
            return
    preview = st.session_state.get(preview_key)
    if preview is None or preview.target_subject_reference != target.strip():
        return
    _show_blockers(preview.blockers)
    if preview.blockers or not reason.strip():
        if not reason.strip():
            st.error("請填寫更正原因。")
        return
    st.write(f"新綁定對象：{preview.target_subject_name}（#{preview.target_subject_reference}）")
    if st.button("確認套用更正", type="primary", key=f"identity_replace_apply_{binding.line_user_id}"):
        _apply_replacement(client, token, binding, target, reason)


def _apply_replacement(client, token, binding, target, reason) -> None:
    operation_id = str(uuid4())
    try:
        client.replacement_apply(
            token,
            binding.line_user_id,
            {
                "expected_version": binding.version,
                "target_subject_reference": target.strip(),
                "reason": reason.strip(),
                "idempotency_key": f"identity-replace:{operation_id}",
                "correlation_id": f"identity-replace:{operation_id}",
            },
        )
    except LineAdminApiError as error:
        st.error(f"更正失敗：{error}")
        return
    st.success("LINE 身分綁定對象已更正。")
    st.rerun()


# Kept cohesive because preview state and the destructive confirmation must stay adjacent.
def _render_revocation(client, token, profile, binding) -> None:
    if binding.status == "revocation_pending":
        _render_pending_actions(client, token, profile, binding)
        return
    if binding.status != "bound":
        st.info("此身分目前不需要解除。")
        return
    reason = st.text_area("解除原因", key=f"identity_revoke_reason_{binding.line_user_id}")
    preview_key = f"identity_revoke_preview_state_{binding.line_user_id}"
    if st.button("預覽解除", key=f"identity_revoke_preview_{binding.line_user_id}"):
        try:
            st.session_state[preview_key] = client.revocation_preview(
                token,
                binding.line_user_id,
            )
        except LineAdminApiError as error:
            st.error(f"無法預覽解除：{error}")
            return
    preview = st.session_state.get(preview_key)
    if preview is None or preview.binding.version != binding.version:
        return
    _show_blockers(preview.blockers)
    if preview.blockers or not reason.strip():
        if not reason.strip():
            st.error("請填寫解除原因。")
        return
    st.warning("套用後會立即停用專屬身分；預設 Rich Menu 成功套用後才清除 User ID projection。")
    if st.button("確認解除身分", type="primary", key=f"identity_revoke_apply_{binding.line_user_id}"):
        _apply_revocation(client, token, binding, reason)


def _apply_revocation(client, token, binding, reason) -> None:
    operation_id = str(uuid4())
    try:
        client.revocation_apply(
            token,
            binding.line_user_id,
            {
                "expected_version": binding.version,
                "reason": reason.strip(),
                "idempotency_key": f"identity-revoke:{operation_id}",
                "correlation_id": f"identity-revoke:{operation_id}",
            },
        )
    except LineAdminApiError as error:
        st.error(f"解除失敗：{error}")
        return
    st.success("已停用身分並排入預設 Rich Menu 回復工作。")
    st.rerun()


def _render_pending_actions(client, token, profile, binding) -> None:
    st.warning(f"解除工作狀態：{binding.revocation_status or '處理中'}")
    if binding.revocation_status != "menu_reset_failed":
        return
    reason = st.text_area("重新處理／人工完成原因", key=f"identity_retry_reason_{binding.line_user_id}")
    columns = st.columns(2)
    if columns[0].button("重新套用預設選單", disabled=not reason.strip()):
        _revocation_action(client, token, binding, "retry", reason)
    can_override = has_capability(profile, "line.identity.binding.override")
    if columns[1].button("人工完成解除", disabled=not can_override or not reason.strip()):
        _revocation_action(client, token, binding, "manual-complete", reason)


def _revocation_action(client, token, binding, action, reason) -> None:
    try:
        client.revocation_action(
            token,
            binding.revocation_request_id,
            action,
            reason.strip(),
        )
    except LineAdminApiError as error:
        st.error(f"處理失敗：{error}")
        return
    st.success("解除工作已更新。")
    st.rerun()


def _show_blockers(blockers) -> None:
    for blocker in blockers:
        st.error(_BLOCKER_LABELS.get(blocker, blocker))


def _value_for_label(labels, selected):
    if selected == "全部":
        return None
    return next(key for key, label in labels.items() if label == selected)


__all__ = ["render_identity_binding_manager"]
