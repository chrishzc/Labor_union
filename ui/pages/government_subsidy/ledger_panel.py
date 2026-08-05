"""Thin Streamlit UI for government subsidy ledger receipts and reversals."""

from __future__ import annotations

import json
from uuid import uuid4

import streamlit as st

from api.schemas.government_subsidy import (
    GovernmentSubsidyAllocationIntentView,
    GovernmentSubsidyReceiptIntentView,
    GovernmentSubsidyReversalIntentView,
)
from ui.api_clients.government_subsidy_api_client import (
    GovernmentSubsidyApiClient,
    GovernmentSubsidyApiError,
)

_RECEIPT_PREVIEW_KEY = "government_subsidy_receipt_preview"
_REVERSAL_PREVIEW_KEY = "government_subsidy_reversal_preview"
_RECEIPT_APPLY_KEY = "government_subsidy_receipt_apply"
_REVERSAL_APPLY_KEY = "government_subsidy_reversal_apply"


def render_government_subsidy_ledger_panel(client: GovernmentSubsidyApiClient) -> None:
    st.subheader("政府補助入款與沖正")
    st.caption("對應銀行流水事件，先 Preview 再 Apply。")
    bank_row_id = st.text_input(
        "finance_import_row_id",
        value=str(st.session_state.get("government_subsidy_bank_row") or ""),
        key="gov_subsidy_ledger_row_input",
    )
    batch_id = st.text_input(
        "batch_id（可空）",
        value=str(st.session_state.get("government_subsidy_batch_id") or ""),
        key="gov_subsidy_ledger_batch_input",
    )
    action = st.selectbox(
        "作業類型",
        ("政府入款", "政府沖正"),
        index=0
        if st.session_state.get("government_subsidy_action") != "政府沖正"
        else 1,
        key="gov_subsidy_ledger_action",
    )
    source_receipt = st.text_input(
        "source_receipt_id（沖正需要）",
        value=str(st.session_state.get("government_subsidy_source_receipt") or ""),
        key="gov_subsidy_ledger_source_receipt",
    )
    allocations_raw = st.text_area(
        "allocation 陣列（JSON）\n[{\"target_identity\": <id>, \"amount_ntd\": <金額}]",
        value='[{"target_identity": 1, "amount_ntd": 0}]',
        height=140,
        key="gov_subsidy_ledger_allocations",
    )
    if action == "政府入款":
        _render_receipt_flow(
            client,
            bank_row_id,
            batch_id,
            allocations_raw,
        )
        return
    _render_reversal_flow(
        client,
        bank_row_id,
        source_receipt,
        allocations_raw,
    )


def _render_receipt_flow(
    client: GovernmentSubsidyApiClient,
    bank_row_id: str,
    batch_id: str,
    allocations_raw: str,
) -> None:
    with st.expander("政府入款 Preview / Apply", expanded=True):
        if st.button("產生入款 Preview", key="gov_subsidy_preview_receipt"):
            row_id = _positive_int(bank_row_id)
            batch_id_value = _positive_int(batch_id) if batch_id else None
            allocations = _parse_allocations(allocations_raw)
            if allocations is None:
                return
            intent = GovernmentSubsidyReceiptIntentView(
                finance_import_row_id=row_id,
                batch_id=batch_id_value,
                allocations=allocations,
            )
            try:
                preview = client.preview_receipt(
                    intent,
                    correlation_id=_new_key("government-subsidy-receipt-preview"),
                )
                st.session_state[_RECEIPT_PREVIEW_KEY] = {
                    "preview": preview,
                    "intent": intent,
                }
                st.session_state.pop(_RECEIPT_APPLY_KEY, None)
            except (GovernmentSubsidyApiError, ValueError) as error:
                st.error(f"入款 Preview 失敗：{error}")
        _render_ledger_preview_and_apply(
            client,
            _RECEIPT_PREVIEW_KEY,
            _RECEIPT_APPLY_KEY,
            "入款",
        )


def _render_reversal_flow(
    client: GovernmentSubsidyApiClient,
    bank_row_id: str,
    source_receipt: str,
    allocations_raw: str,
) -> None:
    with st.expander("政府沖正 Preview / Apply", expanded=True):
        if st.button("產生沖正 Preview", key="gov_subsidy_preview_reversal"):
            row_id = _positive_int(bank_row_id)
            source_receipt_id = _positive_int(source_receipt)
            allocations = _parse_allocations(allocations_raw)
            if allocations is None:
                return
            intent = GovernmentSubsidyReversalIntentView(
                finance_import_row_id=row_id,
                source_receipt_id=source_receipt_id,
                allocations=allocations,
            )
            try:
                preview = client.preview_reversal(
                    intent,
                    correlation_id=_new_key("government-subsidy-reversal-preview"),
                )
                st.session_state[_REVERSAL_PREVIEW_KEY] = {
                    "preview": preview,
                    "intent": intent,
                }
                st.session_state.pop(_REVERSAL_APPLY_KEY, None)
            except (GovernmentSubsidyApiError, ValueError) as error:
                st.error(f"沖正 Preview 失敗：{error}")
        _render_ledger_preview_and_apply(
            client,
            _REVERSAL_PREVIEW_KEY,
            _REVERSAL_APPLY_KEY,
            "沖正",
        )


def _render_ledger_preview_and_apply(
    client: GovernmentSubsidyApiClient,
    preview_state_key: str,
    apply_state_key: str,
    action_label: str,
) -> None:
    state = st.session_state.get(preview_state_key)
    if not isinstance(state, dict):
        return
    preview = state.get("preview")
    if not preview:
        st.warning("請先產生 Preview。")
        return
    st.json(preview.model_dump())
    reason = st.text_input(f"{action_label}原因", key=f"gov_subsidy_ledger_{action_label}_reason")
    if st.button(f"依 Preview {action_label}（Apply）", key=f"gov_subsidy_ledger_apply_{action_label}"):
        if not reason.strip():
            st.error("請先輸入原因。")
            return
        _apply_ledger(
            client,
            action_label,
            state,
            reason.strip(),
            apply_state_key,
        )
    _render_ledger_status(client, apply_state_key, action_label)


def _apply_ledger(
    client: GovernmentSubsidyApiClient,
    action_label: str,
    state: dict,
    reason: str,
    apply_state_key: str,
) -> None:
    intent = state.get("intent")
    preview = state.get("preview")
    command = _build_ledger_command(action_label, apply_state_key)
    try:
        if action_label == "入款":
            job = client.apply_receipt(
                intent,
                preview,
                reason=reason,
                idempotency_key=command["idempotency_key"],
                correlation_id=command["correlation_id"],
            )
        else:
            job = client.apply_reversal(
                intent,
                preview,
                reason=reason,
                idempotency_key=command["idempotency_key"],
                correlation_id=command["correlation_id"],
            )
    except (GovernmentSubsidyApiError, ValueError, TypeError) as error:
        st.error(f"{action_label} Apply 失敗：{error}")
        return
    command["job_id"] = job.job_id
    st.session_state[apply_state_key] = command
    st.info(f"{action_label} 已提交：{job.job_id}")


def _render_ledger_status(
    client: GovernmentSubsidyApiClient,
    apply_state_key: str,
    action_label: str,
) -> None:
    command = st.session_state.get(apply_state_key)
    if not isinstance(command, dict) or command.get("terminal"):
        return
    job_id = command.get("job_id")
    if not job_id:
        st.warning(f"{action_label} 尚未取得工作編號。")
        return
    if st.button(f"查詢 {action_label} 狀態", key=f"gov_subsidy_ledger_check_{apply_state_key}"):
        try:
            status = client.get_job_status(job_id)
        except GovernmentSubsidyApiError as error:
            st.error(f"查詢狀態失敗：{error}")
            return
        if status.status in {"queued", "running"}:
            st.info(f"{action_label} 處理中：{status.status}")
            return
        command["terminal"] = True
        if status.status == "succeeded":
            st.success(f"{action_label} 已完成。")
            return
        st.error(f"{action_label} 失敗：{status.status}")


def _parse_allocations(raw: str) -> list[GovernmentSubsidyAllocationIntentView] | None:
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        st.error("allocation JSON 解析失敗。")
        return None
    if not isinstance(parsed, list):
        st.error("allocation 必須是陣列。")
        return None
    items: list[GovernmentSubsidyAllocationIntentView] = []
    for row in parsed:
        if not isinstance(row, dict):
            st.error("allocation 每筆必須是物件。")
            return None
        try:
            items.append(
                GovernmentSubsidyAllocationIntentView(
                    target_identity=_positive_int(row.get("target_identity")),
                    amount_ntd=_positive_int(row.get("amount_ntd")),
                )
            )
        except (TypeError, ValueError) as error:
            st.error(f"allocation 不正確：{error}")
            return None
    return items


def _build_ledger_command(action_label: str, apply_state_key: str) -> dict:
    existing = st.session_state.get(apply_state_key)
    if isinstance(existing, dict) and not existing.get("terminal"):
        return existing
    return {
        "action": action_label,
        "idempotency_key": _new_key("government-subsidy-ledger"),
        "correlation_id": _new_key("government-subsidy-ledger-apply"),
        "job_id": None,
        "terminal": False,
    }


def _positive_int(value: object) -> int:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        if parsed > 0:
            return parsed
    raise ValueError("expected positive integer")


def _new_key(prefix: str) -> str:
    return f"{prefix}:{uuid4()}"
