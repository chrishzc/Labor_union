"""Thin Streamlit panel for verified contract evidence and human mapping."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ui.api_clients.contract_integration_api_client import ContractIntegrationApiClient
from ui.api_clients.line_api_client import LineAdminApiError
from ui.components.line_ui_support import complete_operation, has_capability, operation_headers


CURSOR_KEY = "contract_evidence_cursor"
FILTER_KEY = "contract_evidence_filter"
PROCESSING_LABELS = {
    "received": "已接收",
    "verified": "已驗證",
    "normalized": "已整理",
    "applied": "已完成處理",
    "rejected": "已拒絕",
    "retry_pending": "等待重試",
}


def render_contract_evidence_manager(client, token, profile: dict[str, Any]) -> None:
    st.subheader("電子契約確認")
    st.caption("只顯示通過簽章驗證的外部事件；綁定後仍須到訂單頁 Preview／Apply。")
    _render_runtime_warning(profile)
    contract_id = st.text_input("外部契約編號（可留空）").strip() or None
    status_label = st.selectbox("處理狀態", ["全部", *PROCESSING_LABELS.values()])
    selected_status = next(
        (key for key, label in PROCESSING_LABELS.items() if label == status_label),
        None,
    )
    _reset_cursor_when_filter_changes(contract_id, selected_status)
    try:
        page = client.evidence(
            token,
            provider_contract_id=contract_id,
            processing_status=selected_status,
            cursor=st.session_state.get(CURSOR_KEY),
        )
    except LineAdminApiError as error:
        st.error(f"無法載入契約事件：{error}")
        return
    items = page.get("items", [])
    if not items:
        st.info("目前沒有符合條件的契約事件。")
        return
    st.dataframe(pd.DataFrame(_evidence_rows(items)), width="stretch", hide_index=True)
    _render_page_navigation(page)
    if has_capability(profile, "contract.evidence.manage"):
        _render_mapping(client, token, items)


def _reset_cursor_when_filter_changes(contract_id, status) -> None:
    signature = (contract_id, status)
    if st.session_state.get(FILTER_KEY) == signature:
        return
    st.session_state[FILTER_KEY] = signature
    st.session_state.pop(CURSOR_KEY, None)


def _render_page_navigation(page: dict) -> None:
    newest, older = st.columns(2)
    if newest.button("回到最新", disabled=CURSOR_KEY not in st.session_state):
        st.session_state.pop(CURSOR_KEY, None)
        st.rerun()
    next_cursor = page.get("next_cursor")
    if older.button("查看更早紀錄", disabled=not next_cursor):
        st.session_state[CURSOR_KEY] = next_cursor
        st.rerun()


def _render_runtime_warning(profile: dict[str, Any]) -> None:
    enabled = profile.get("runtime_availability", {}).get("contract_worker_enabled")
    if not enabled:
        st.warning("契約背景處理目前未啟用；既有證據仍可查看，但新事件不會自動處理。")


def _evidence_rows(items):
    return [
        {
            "外部契約": item["provider_contract_id"],
            "事件": item["event_type"],
            "契約狀態": item["contract_status"],
            "發生時間": item["provider_occurred_at"],
            "處理狀態": PROCESSING_LABELS.get(
                item["processing_status"], item["processing_status"]
            ),
            "內部合約／案件": item.get("internal_contract_identity") or "尚未綁定",
            "錯誤": item.get("last_error_code") or "",
        }
        for item in items
    ]


def _render_mapping(client: ContractIntegrationApiClient, token, items) -> None:
    st.markdown("#### 人工綁定內部合約")
    inbox_id = st.selectbox("選擇契約事件", [item["inbox_id"] for item in items])
    selected = next(item for item in items if item["inbox_id"] == inbox_id)
    if selected.get("internal_contract_identity"):
        st.page_link(
            "pages/02_orders.py",
            label=f"前往案件與配對中心：{selected['internal_contract_identity']}",
        )
    internal_identity = st.text_input(
        "內部合約或案件編號", value=selected.get("internal_contract_identity") or ""
    ).strip()
    reason = st.text_input("綁定原因").strip()
    confirmed = st.checkbox("我已確認外部契約與內部案件是同一份契約")
    if not st.button("儲存契約綁定", disabled=not (confirmed and internal_identity and reason)):
        return
    payload = _mapping_payload(selected, internal_identity, reason)
    _submit_mapping(client, token, selected["provider_contract_id"], payload)


def _mapping_payload(selected: dict, internal_identity: str, reason: str) -> dict:
    return {
        "provider": selected["provider"],
        "provider_contract_id": selected["provider_contract_id"],
        "internal_contract_identity": internal_identity,
        "expected_version": selected.get("mapping_version", 0),
        "reason": reason,
    }


def _submit_mapping(client, token, provider_contract_id: str, payload: dict) -> None:
    operation = f"contract-map:{provider_contract_id}"
    headers = operation_headers(operation, payload)
    try:
        client.map_evidence(token, payload, **_header_arguments(headers))
    except LineAdminApiError as error:
        st.error(f"綁定失敗：{error}")
        return
    complete_operation(operation)
    st.success("契約綁定已保存；請到訂單契約頁執行 Preview／Apply。")
    st.rerun()


def _header_arguments(headers):
    return {
        "idempotency_key": headers["Idempotency-Key"],
        "correlation_id": headers["X-Correlation-ID"],
    }


__all__ = ["render_contract_evidence_manager"]
