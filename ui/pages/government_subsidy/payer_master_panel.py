"""Contextual editor for the singleton government refund account master."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import streamlit as st

from api.schemas.government_subsidy import (
    GovernmentPayerAccountApplyBody,
    GovernmentPayerAccountPreviewBody,
    GovernmentRefundAccountInputView,
)
from ui.api_clients.government_subsidy_api_client import (
    GovernmentSubsidyApiClient,
    GovernmentSubsidyApiError,
)


def render_government_refund_account_editor(
    client: GovernmentSubsidyApiClient,
    *,
    key_prefix: str,
) -> None:
    """Render only when a government-overpayment return needs an account."""
    try:
        master = client.query_payer_master()
    except GovernmentSubsidyApiError as error:
        st.error(f"無法讀取政府退款帳戶主檔：{error}")
        return
    st.caption(f"付款方：{master.payer_name}（{master.payer_identity}）")
    _render_active_account(master.active_refund_account)
    with st.expander("新增／更新政府退款帳戶", expanded=master.active_refund_account is None):
        _render_account_command(client, key_prefix)


def _render_active_account(account) -> None:
    if account is None:
        st.warning("尚未登錄政府退款帳戶；選擇退還政府前必須先建立。")
        return
    st.info(
        "目前有效帳戶："
        f"{account.bank_code}／{account.account_display}／{account.account_name}"
    )


def _render_account_command(client, key_prefix: str) -> None:
    account = _account_input(key_prefix)
    preview_key = f"{key_prefix}_refund_account_preview"
    if st.button("產生帳戶更新 Preview", key=f"{key_prefix}_refund_account_preview_button"):
        _preview_account(client, account, preview_key)
    preview = st.session_state.get(preview_key)
    if preview is None:
        return
    st.json(preview.model_dump())
    if st.button("依 Preview 儲存退款帳戶", key=f"{key_prefix}_refund_account_apply_button"):
        _apply_account(client, account, preview.preview_fingerprint, preview_key)


def _account_input(key_prefix: str) -> dict[str, str]:
    return {
        "bank_code": st.text_input("銀行代碼", key=f"{key_prefix}_refund_bank_code"),
        "account_number": st.text_input("帳號", type="password", key=f"{key_prefix}_refund_account_number"),
        "account_name": st.text_input("戶名", key=f"{key_prefix}_refund_account_name"),
        "effective_from": st.date_input("生效日", value=date.today(), key=f"{key_prefix}_refund_effective_from").isoformat(),
        "reason": st.text_input("設定原因", key=f"{key_prefix}_refund_reason"),
        "evidence_reference": st.text_input("依據／證明", key=f"{key_prefix}_refund_evidence"),
    }


def _preview_account(client, account, preview_key: str) -> None:
    try:
        preview = client.preview_refund_account(
            GovernmentPayerAccountPreviewBody(
                account=GovernmentRefundAccountInputView(**account)
            ),
            _new_command_key("government-payer-account-preview"),
        )
    except (GovernmentSubsidyApiError, ValueError) as error:
        st.error(f"帳戶 Preview 失敗：{error}")
        return
    st.session_state[preview_key] = preview


def _apply_account(client, account, preview_fingerprint: str, preview_key: str) -> None:
    try:
        receipt = client.apply_refund_account(
            GovernmentPayerAccountApplyBody(
                account=GovernmentRefundAccountInputView(**account),
                preview_fingerprint=preview_fingerprint,
            ),
            _new_command_key("government-payer-account-apply"),
        )
    except (GovernmentSubsidyApiError, ValueError) as error:
        st.error(f"帳戶儲存失敗：{error}")
        return
    st.session_state.pop(preview_key, None)
    st.success("政府退款帳戶已建立新版本。")
    st.json(receipt.model_dump())


def _new_command_key(prefix: str) -> str:
    return f"{prefix}:{uuid4()}"
