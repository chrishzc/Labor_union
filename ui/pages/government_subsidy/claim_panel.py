"""Thin Streamlit UI for government subsidy claim planning/submit/approval."""

from __future__ import annotations

import json
from uuid import uuid4

import streamlit as st

from api.schemas.government_subsidy import (
    GovernmentSubsidyApprovalItemView,
    GovernmentSubsidyClaimBatchPageView,
    GovernmentSubsidyClaimPlanningIntentView,
    GovernmentSubsidyClaimPreviewView,
)
from ui.api_clients.government_subsidy_api_client import (
    GovernmentSubsidyApiClient,
    GovernmentSubsidyApiError,
)

_BATCH_LIST_STATE_KEY = "government_subsidy_batch_list"
_BATCH_STATE_KEY = "government_subsidy_claim_batch"
_PLAN_PREVIEW_KEY = "government_subsidy_claim_plan_state"
_SUBMIT_PREVIEW_KEY = "government_subsidy_claim_submit_state"
_APPROVAL_PREVIEW_KEY = "government_subsidy_claim_approval_state"
_PLAN_APPLY_STATE_KEY = "government_subsidy_claim_plan_apply_state"
_SUBMIT_APPLY_STATE_KEY = "government_subsidy_claim_submit_apply_state"
_APPROVAL_APPLY_STATE_KEY = "government_subsidy_claim_approval_apply_state"


def render_government_subsidy_claim_panel(client: GovernmentSubsidyApiClient) -> None:
    st.subheader("政府補助申請批次")
    st.caption("先 Preview 再 Apply，與異常導向頁一致。")
    _render_batch_list_panel(client)
    _render_batch_query_panel(client)
    _render_planning_panel(client)
    batch = st.session_state.get(_BATCH_STATE_KEY)
    if batch is None:
        return
    _render_batch_detail(batch)
    _render_submission_panel(client, batch.batch_id)
    _render_approval_panel(client, batch.batch_id)


def _render_batch_list_panel(client: GovernmentSubsidyApiClient) -> None:
    with st.expander("1. 批次清單", expanded=True):
        cursor = st.number_input("cursor（空白代表第一頁）", min_value=0, value=0, step=1, key="gov_subsidy_batch_cursor")
        limit = st.number_input("每頁數", min_value=1, max_value=100, value=20, step=1, key="gov_subsidy_batch_limit")
        if st.button("查詢補助批次清單", key="gov_subsidy_query_batch_list"):
            _query_batch_list(client, cursor, int(limit))
        page = st.session_state.get(_BATCH_LIST_STATE_KEY)
        if not isinstance(page, GovernmentSubsidyClaimBatchPageView):
            return
        st.dataframe(
            [
                {
                    "批次ID": item.batch_id,
                    "識別碼": item.batch_identity,
                    "狀態": item.status,
                    "申請總額": item.requested_total_ntd,
                    "待申請": item.outstanding_ntd,
                }
                for item in page.batches
            ],
            hide_index=True,
        )
        if page.next_cursor is not None:
            st.info(f"下一頁 cursor：{page.next_cursor}")


def _render_batch_query_panel(client: GovernmentSubsidyApiClient) -> None:
    with st.expander("2. 查詢指定 Batch", expanded=True):
        batch_id = st.text_input(
            "batch_id",
            value=str(st.session_state.get("government_subsidy_pending_query_batch_id") or ""),
            key="gov_subsidy_batch_id_input",
        )
        if st.button("查詢 Batch 明細", key="gov_subsidy_query_batch"):
            _query_batch(client, batch_id)


def _render_batch_detail(batch) -> None:
    with st.expander("3. Batch 明細", expanded=True):
        st.json(
            {
                "batch_id": batch.batch_id,
                "batch_identity": batch.batch_identity,
                "batch_version": batch.batch_version,
                "status": batch.status,
                "requested_total_ntd": batch.requested_total_ntd,
                "approved_total_ntd": batch.approved_total_ntd,
                "net_allocated_ntd": batch.net_allocated_ntd,
                "outstanding_ntd": batch.outstanding_ntd,
            }
        )
        st.dataframe(
            [
                {
                    "item_id": item.item_id,
                    "case_no": item.case_no,
                    "staff_id": item.staff_id,
                    "requested": item.requested_amount_ntd,
                    "approved": item.approved_amount_ntd,
                    "outstanding": item.outstanding_ntd,
                }
                for item in batch.items
            ],
            hide_index=True,
        )


def _render_planning_panel(client: GovernmentSubsidyApiClient) -> None:
    with st.expander("4. 規劃申請批次", expanded=False):
        year = st.number_input("申請年度", min_value=2020, max_value=2500, value=2026, key="gov_subsidy_plan_year")
        quarter = st.selectbox("季度", [1, 2, 3, 4], key="gov_subsidy_plan_quarter")
        revision = st.number_input("版次", min_value=1, max_value=99999, value=1, key="gov_subsidy_plan_revision")
        if st.button("產生規劃 Preview", key="gov_subsidy_preview_plan"):
            intent = _build_plan_intent(year, quarter, revision)
            if intent is None:
                return
            try:
                preview = client.preview_claim_plan(
                    intent,
                    correlation_id=_new_key("government-subsidy-claim-plan-preview"),
                )
                st.session_state[_PLAN_PREVIEW_KEY] = {
                    "preview": preview,
                    "intent": intent,
                }
                st.session_state.pop(_PLAN_APPLY_STATE_KEY, None)
            except (GovernmentSubsidyApiError, ValueError) as error:
                st.error(f"規劃 Preview 失敗：{error}")
        _render_claim_preview_and_apply(
            client,
            _PLAN_PREVIEW_KEY,
            _PLAN_APPLY_STATE_KEY,
            "規劃申請",
            _apply_plan,
        )


def _render_submission_panel(client: GovernmentSubsidyApiClient, batch_id: int) -> None:
    with st.expander("5. 送件 Preview / Apply", expanded=False):
        if st.button("產生送件 Preview", key="gov_subsidy_preview_submit"):
            try:
                preview = client.preview_claim_submission(
                    batch_id,
                    correlation_id=_new_key("government-subsidy-claim-submit-preview"),
                )
                st.session_state[_SUBMIT_PREVIEW_KEY] = {
                    "preview": preview,
                    "batch_id": batch_id,
                }
                st.session_state.pop(_SUBMIT_APPLY_STATE_KEY, None)
            except (GovernmentSubsidyApiError, ValueError) as error:
                st.error(f"送件 Preview 失敗：{error}")
        _render_claim_preview_and_apply(
            client,
            _SUBMIT_PREVIEW_KEY,
            _SUBMIT_APPLY_STATE_KEY,
            "送件",
            lambda c, s, p, r, k: _apply_submit(c, s, p, r, k, batch_id),
        )


def _render_approval_panel(client: GovernmentSubsidyApiClient, batch_id: int) -> None:
    with st.expander("6. 核准 Preview / Apply", expanded=False):
        approvals_raw = st.text_area(
            "核准資料（JSON 陣列）",
            value='[{"item_id": 1, "approved_amount_ntd": 0}]',
            height=120,
            key="gov_subsidy_approval_raw",
        )
        if st.button("產生核准 Preview", key="gov_subsidy_preview_approval"):
            approvals = _parse_approvals(approvals_raw)
            if approvals is None:
                return
            if not approvals:
                st.warning("尚未輸入核准資料。")
                return
            try:
                preview = client.preview_claim_approval(
                    batch_id,
                    approvals,
                    correlation_id=_new_key("government-subsidy-claim-approval-preview"),
                )
                st.session_state[_APPROVAL_PREVIEW_KEY] = {
                    "preview": preview,
                    "approvals": approvals,
                }
                st.session_state.pop(_APPROVAL_APPLY_STATE_KEY, None)
            except (GovernmentSubsidyApiError, ValueError) as error:
                st.error(f"核准 Preview 失敗：{error}")
        _render_claim_preview_and_apply(
            client,
            _APPROVAL_PREVIEW_KEY,
            _APPROVAL_APPLY_STATE_KEY,
            "核准",
            lambda c, s, p, r, k: _apply_approval(c, s, p, r, k, batch_id),
        )


def _render_claim_preview_and_apply(
    client: GovernmentSubsidyApiClient,
    preview_state_key: str,
    apply_state_key: str,
    action_label: str,
    apply_action,
) -> None:
    state = st.session_state.get(preview_state_key)
    if not isinstance(state, dict):
        return
    preview = state.get("preview")
    if not isinstance(preview, GovernmentSubsidyClaimPreviewView):
        st.warning("預覽資料已失效，請重新產生。")
        st.session_state.pop(preview_state_key, None)
        return
    st.json(preview.model_dump())
    reason = st.text_input(f"{action_label}原因", key=f"gov_subsidy_{action_label}_reason")
    if st.button(f"依 Preview {action_label}（Apply）", key=f"gov_subsidy_apply_{action_label}"):
        if not reason.strip():
            st.error("請先輸入原因。")
            return
        apply_action(client, state, preview, reason.strip(), apply_state_key)
    _render_apply_status(client, apply_state_key, action_label)


def _render_apply_status(
    client: GovernmentSubsidyApiClient,
    state_key: str,
    action_label: str,
) -> None:
    command = st.session_state.get(state_key)
    if not isinstance(command, dict) or command.get("terminal"):
        return
    job_id = command.get("job_id")
    if not job_id:
        st.warning(f"{action_label} 尚未取得 job_id，請重試")
        return
    if st.button(f"查詢 {action_label} 狀態", key=f"gov_subsidy_check_{state_key}"):
        try:
            status = client.get_job_status(job_id)
        except GovernmentSubsidyApiError as error:
            st.error(f"查詢狀態失敗：{error}")
            return
        if status.status in {"queued", "running"}:
            st.info(f"{action_label} 中：{status.status}")
            return
        command["terminal"] = True
        if status.status == "succeeded":
            st.success(f"{action_label} 已完成。")
            return
        st.error(f"{action_label} 未完成：{status.status}")


def _query_batch_list(
    client: GovernmentSubsidyApiClient,
    cursor: int,
    limit: int,
) -> None:
    request_cursor = None if cursor <= 0 else cursor
    try:
        st.session_state[_BATCH_LIST_STATE_KEY] = client.list_batches(
            cursor=request_cursor,
            limit=limit,
        )
    except (GovernmentSubsidyApiError, ValueError) as error:
        st.error(f"查詢補助批次清單失敗：{error}")


def _query_batch(client: GovernmentSubsidyApiClient, batch_id_value: str) -> None:
    batch_id = _positive_int(batch_id_value)
    if batch_id is None:
        st.error("batch_id 必須是正整數")
        return
    try:
        st.session_state[_BATCH_STATE_KEY] = client.query_batch(batch_id)
        st.session_state.pop("government_subsidy_pending_query_batch_id", None)
    except (GovernmentSubsidyApiError, ValueError) as error:
        st.error(f"查詢 Batch 失敗：{error}")


def _apply_plan(
    client: GovernmentSubsidyApiClient,
    state: dict,
    preview: GovernmentSubsidyClaimPreviewView,
    reason: str,
    apply_state_key: str,
) -> None:
    intent = state.get("intent")
    if not isinstance(intent, dict) and not hasattr(intent, "application_year"):
        st.error("請先重新產生申請規劃 Preview。")
        return
    command = _build_claim_command("規劃申請", apply_state_key)
    try:
        job = client.apply_claim_plan(
            intent,
            preview,
            reason=reason,
            idempotency_key=command["idempotency_key"],
            correlation_id=command["correlation_id"],
        )
    except (GovernmentSubsidyApiError, ValueError) as error:
        st.error(f"Apply 規劃申請失敗：{error}")
        return
    command["job_id"] = job.job_id
    st.session_state[apply_state_key] = command
    st.info(f"規劃申請已提交：{job.job_id}")


def _apply_submit(
    client: GovernmentSubsidyApiClient,
    _state: dict,
    preview: GovernmentSubsidyClaimPreviewView,
    reason: str,
    apply_state_key: str,
    batch_id: int,
) -> None:
    command = _build_claim_command("送件", apply_state_key)
    try:
        job = client.apply_claim_submission(
            batch_id,
            preview,
            reason=reason,
            idempotency_key=command["idempotency_key"],
            correlation_id=command["correlation_id"],
        )
    except (GovernmentSubsidyApiError, ValueError) as error:
        st.error(f"Apply 送件失敗：{error}")
        return
    command["job_id"] = job.job_id
    st.session_state[apply_state_key] = command
    st.info(f"送件已提交：{job.job_id}")


def _apply_approval(
    client: GovernmentSubsidyApiClient,
    state: dict,
    preview: GovernmentSubsidyClaimPreviewView,
    reason: str,
    apply_state_key: str,
    batch_id: int,
) -> None:
    approvals = state.get("approvals")
    if not isinstance(approvals, list) or not approvals:
        st.error("請先產生核准 Preview。")
        return
    typed = [_coerce_approval(item) for item in approvals]
    command = _build_claim_command("核准", apply_state_key)
    try:
        job = client.apply_claim_approval(
            batch_id,
            typed,
            preview,
            reason=reason,
            idempotency_key=command["idempotency_key"],
            correlation_id=command["correlation_id"],
        )
    except (GovernmentSubsidyApiError, ValueError) as error:
        st.error(f"Apply 核准失敗：{error}")
        return
    command["job_id"] = job.job_id
    st.session_state[apply_state_key] = command
    st.info(f"核准已提交：{job.job_id}")


def _build_plan_intent(year: int, quarter: int, revision: int):
    try:
        return GovernmentSubsidyClaimPlanningIntentView(
            application_year=year,
            quarter=quarter,
            revision=revision,
        )
    except (ValueError, TypeError):
        st.error("申請規劃參數不正確。")
        return None


def _parse_approvals(value: str) -> list[GovernmentSubsidyApprovalItemView] | None:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        st.error("核准 JSON 解析失敗。")
        return None
    if not isinstance(parsed, list):
        st.error("核准資料必須是陣列。")
        return None
    items: list[GovernmentSubsidyApprovalItemView] = []
    for row in parsed:
        if not isinstance(row, dict):
            st.error("每筆核准資料必須是物件。")
            return None
        try:
            items.append(
                GovernmentSubsidyApprovalItemView(
                    item_id=_positive_int(row.get("item_id")),
                    approved_amount_ntd=_non_negative_int(row.get("approved_amount_ntd")),
                )
            )
        except (TypeError, ValueError) as error:
            st.error(f"核准資料不正確：{error}")
            return None
    return items


def _coerce_approval(item: object) -> GovernmentSubsidyApprovalItemView:
    if isinstance(item, GovernmentSubsidyApprovalItemView):
        return item
    raise ValueError("approval item invalid")


def _build_claim_command(action_label: str, apply_state_key: str) -> dict:
    existing = st.session_state.get(apply_state_key)
    if isinstance(existing, dict):
        return existing
    return {
        "action": action_label,
        "idempotency_key": _new_key("government-subsidy-claim"),
        "correlation_id": _new_key("government-subsidy-claim-apply"),
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


def _non_negative_int(value: object) -> int:
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ValueError("expected non-negative integer")


def _new_key(prefix: str) -> str:
    return f"{prefix}:{uuid4()}"
