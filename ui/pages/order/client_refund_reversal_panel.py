"""Read-only Client Finance refund status for the case-detail page."""

from __future__ import annotations

import streamlit as st

from ui.api_clients.client_refund_reversal_api_client import (
    ClientRefundReversalApiClient,
)
from ui.pages.shared import build_admin_headers, resolve_api_base_url


def render_client_refund_reversal_panel(case_no: str) -> None:
    """Show case-owned obligations; bank rows stay in Finance Import correction."""
    st.markdown("#### 正式客戶退款／補助退還")
    try:
        facts = _client().query(case_no)
    except Exception as error:
        st.error(f"無法取得正式退款根事實：{error}")
        return

    st.caption(
        "銀行出款、退匯與套用須從「銀行流水匯入與帳務修正」進入，"
        "以固定銀行列、人工證據與案件義務完成 Preview／Apply，避免跨案件配對。"
    )
    _render_obligations("一般客戶退款待付", facts.refund_obligations)
    _render_obligations("客戶補助退還待付", facts.subsidy_return_obligations)


def _client() -> ClientRefundReversalApiClient:
    return ClientRefundReversalApiClient(
        base_url=resolve_api_base_url(),
        headers=build_admin_headers(),
    )


def _render_obligations(title, obligations) -> None:
    st.caption(title)
    if not obligations:
        st.info("目前沒有待付義務。")
        return
    st.dataframe(obligations, hide_index=True, use_container_width=True)


__all__ = ["render_client_refund_reversal_panel"]
