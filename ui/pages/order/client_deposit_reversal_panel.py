"""Thin Streamlit panel for the canonical deposit reversal workflow."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import streamlit as st

from ui.api_clients.client_deposit_reversal_api_client import (
    ClientDepositReversalApiClient,
    DepositReversalApiError,
)
from ui.pages.shared import build_admin_headers, resolve_api_base_url


def render_client_deposit_reversal_panel(case_no: str) -> None:
    st.markdown("#### 正式訂金沖正")
    st.caption("請輸入原始 Client Finance ledger entry ID；金額與訂單後續動作由後端 Preview 決定。")
    original_entry_id = int(
        st.number_input(
            "原始帳務流水 ID",
            min_value=1,
            step=1,
            key=f"deposit_reversal_entry_{case_no}",
        )
    )
    reversal_date = st.date_input(
        "沖正發生日",
        value=date.today(),
        key=f"deposit_reversal_date_{case_no}",
    )
    if st.button("產生訂金沖正預覽", key=f"deposit_reversal_preview_{case_no}"):
        _store_preview(case_no, original_entry_id, reversal_date)
    _render_preview(case_no)


def _store_preview(case_no: str, entry_id: int, reversal_date: date) -> None:
    try:
        preview = _client().preview(
            case_no,
            entry_id,
            reversal_date,
            correlation_id=f"deposit-reversal-preview:{uuid4()}",
        )
    except DepositReversalApiError as error:
        st.error(f"訂金沖正預覽失敗：{error.message}")
        return
    st.session_state[_preview_key(case_no)] = (entry_id, reversal_date, preview)
    st.success("已取得後端訂金沖正預覽，請確認後套用。")


def _render_preview(case_no: str) -> None:
    state = st.session_state.get(_preview_key(case_no))
    if state is None:
        return
    entry_id, reversal_date, preview = state
    st.json(preview.candidate)
    st.caption(f"帳戶版本：`{preview.account_version}`")
    reason = st.text_input("沖正原因", max_chars=500, key=f"deposit_reversal_reason_{case_no}")
    if not st.button("確認訂金沖正並套用", key=f"deposit_reversal_apply_{case_no}"):
        return
    if not reason.strip():
        st.error("請填寫沖正原因。")
        return
    _apply(case_no, entry_id, reversal_date, preview, reason)


def _apply(case_no, entry_id, reversal_date, preview, reason) -> None:
    try:
        receipt = _client().apply(
            case_no,
            entry_id,
            reversal_date,
            preview,
            reason=reason,
            idempotency_key=f"deposit-reversal:{uuid4()}",
            correlation_id=f"deposit-reversal-apply:{uuid4()}",
        )
    except DepositReversalApiError as error:
        st.error(f"訂金沖正套用失敗：{error.message}")
        return
    st.success(
        f"訂金沖正已套用：{receipt.reversal_amount_ntd:,} 元，"
        f"帳戶版本為 {receipt.account_version}。"
    )
    del st.session_state[_preview_key(case_no)]
    st.rerun()


def _preview_key(case_no: str) -> str:
    return f"deposit_reversal_preview:{case_no}"


def _client() -> ClientDepositReversalApiClient:
    return ClientDepositReversalApiClient(
        base_url=resolve_api_base_url(),
        headers=build_admin_headers(),
    )


__all__ = ["render_client_deposit_reversal_panel"]
