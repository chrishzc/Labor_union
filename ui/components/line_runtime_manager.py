"""
File: line_runtime_manager.py
Description: 以 typed server receipt 管理 LINE runtime 告警對象。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from ui.api_clients.line_api_client import LineAdminApiError
from ui.api_clients.runtime_health_api_client import (
    AlertAdminCandidateView,
    AlertTargetMutationReceipt,
    AlertTargetView,
    RuntimeHealthApiClient,
    RuntimeHealthEventView,
    RuntimeHealthRecordView,
)
from ui.components.line_ui_support import complete_operation, has_capability, operation_headers


STATUS_LABELS = {
    "healthy": "正常",
    "warning": "需要注意",
    "critical": "異常",
    "unknown": "尚無資料",
    "maintenance": "維護中",
}


def render_runtime_manager(
    runtime_client: RuntimeHealthApiClient,
    token: str | None,
    profile: dict[str, Any],
) -> None:
    st.subheader("LINE 系統使用狀態")
    st.caption("顯示監控程序最近一次保存的結果；開啟此頁不會直接探測或重啟服務。")
    try:
        records = runtime_client.health_status(token)
    except LineAdminApiError as error:
        st.error(f"無法取得系統狀態：{error}")
        return
    _render_summary(records)
    _render_status_records(records)
    _render_events(runtime_client, token)
    _render_alert_targets(runtime_client, token, profile)


def _render_summary(records: list[RuntimeHealthRecordView]) -> None:
    critical = sum(item.status == "critical" for item in records)
    warning = sum(item.status == "warning" for item in records)
    unknown = sum(item.status == "unknown" for item in records)
    columns = st.columns(4)
    columns[0].metric("已監控項目", len(records))
    columns[1].metric("嚴重異常", critical)
    columns[2].metric("需要注意", warning)
    columns[3].metric("尚無檢測資料", unknown)
    if not records:
        st.info("監控資料尚未建立。Stage 10 套用 migration 並啟動 Monitor 後才會開始出現結果。")


def _render_status_records(records: list[RuntimeHealthRecordView]) -> None:
    if not records:
        return
    rows = [
        {
            "服務": item.component,
            "檢查項目": item.check_name,
            "狀態": STATUS_LABELS.get(item.status, item.status),
            "說明": item.message,
            "回應時間(ms)": item.response_ms,
            "連續失敗": item.consecutive_failures,
            "最後檢測": item.checked_at,
            "狀態變更": item.status_changed_at,
            "詳細資訊": _details_summary(item.details),
        }
        for item in records
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _render_events(client: RuntimeHealthApiClient, token: str | None) -> None:
    with st.expander("最近狀態變更"):
        try:
            events = client.health_events(token, 100)
        except LineAdminApiError as error:
            st.error(f"無法載入狀態紀錄：{error}")
            return
        if not events:
            st.caption("目前沒有狀態變更紀錄。")
            return
        st.dataframe(_event_rows(events), width="stretch", hide_index=True)


def _event_rows(events: list[RuntimeHealthEventView]) -> list[dict[str, object]]:
    return [
        {
            "時間": item.occurred_at,
            "檢查項目": item.check_name,
            "狀態變化": item.transition_type,
            "結果": STATUS_LABELS.get(
                item.resulting_status, item.resulting_status
            ),
            "說明": item.message,
        }
        for item in events
    ]


def _render_alert_targets(
    client: RuntimeHealthApiClient, token: str | None, profile: dict[str, Any]
) -> None:
    with st.expander("異常通知對象"):
        try:
            targets = client.alert_targets(token)
        except LineAdminApiError as error:
            st.error(f"無法載入通知對象：{error}")
            return
        if targets:
            st.dataframe(_target_rows(targets), width="stretch", hide_index=True)
        else:
            st.caption("尚未設定異常通知對象。")
        if not has_capability(profile, "line.alert.manage"):
            return
        _render_target_toggle(client, token, targets)


def _target_rows(targets: list[AlertTargetView]) -> list[dict[str, object]]:
    return [
        {
            "編號": item.target_id,
            "對象": item.display_label,
            "類型": "工會群組" if item.target_kind == "group" else "工會人員",
            "最低通知等級": STATUS_LABELS.get(item.minimum_status, item.minimum_status),
            "啟用": item.state == "active",
        }
        for item in targets
    ]


def _render_target_toggle(
    client: RuntimeHealthApiClient,
    token: str | None,
    targets: list[AlertTargetView],
) -> None:
    _render_target_add(client, token)
    if not targets:
        return
    target_id = st.selectbox("選擇通知對象", [item.target_id for item in targets])
    selected = next(item for item in targets if item.target_id == target_id)
    enabled = st.checkbox(
        "啟用通知",
        value=selected.state == "active",
        key=f"alert_target_{target_id}",
    )
    reason = st.text_input("變更原因", value="管理端更新 LINE 告警對象")
    if st.button("更新通知設定"):
        try:
            receipt = _set_target_enabled(
                client, token, selected, enabled, reason,
            )
            _require_readback(client, token, receipt)
        except LineAdminApiError as error:
            st.error(f"更新失敗：{error}")
            return
        complete_operation("line-alert-target-enable")
        st.rerun()
    if selected.target_kind == "group" and st.button("重設群組通知對象"):
        try:
            receipt = _reset_group_target(client, token, selected, reason)
            _require_readback(client, token, receipt)
        except LineAdminApiError as error:
            st.error(f"重設失敗：{error}")
            return
        complete_operation("line-alert-group-reset")
        st.rerun()


def _render_target_add(client: RuntimeHealthApiClient, token: str | None) -> None:
    candidates = _linked_admin_candidates(client, token)
    if not candidates:
        return
    _render_add_target_form(client, token, candidates)


def _linked_admin_candidates(
    client: RuntimeHealthApiClient, token: str | None
) -> list[AlertAdminCandidateView]:
    try:
        candidates = [item for item in client.admin_alert_candidates(token) if item.line_linked]
    except LineAdminApiError as error:
        st.error(f"無法載入工會人員：{error}")
        return []
    if not candidates:
        st.caption("目前沒有已綁定 LINE 的工會人員可加入通知。")
    return candidates


def _render_add_target_form(
    client: RuntimeHealthApiClient,
    token: str | None,
    candidates: list[AlertAdminCandidateView],
) -> None:
    selected_id = st.selectbox(
        "新增工會人員通知",
        [item.candidate_id for item in candidates],
        format_func=lambda value: next(
            item.display_label for item in candidates if item.candidate_id == value
        ),
    )
    minimum_status = st.selectbox("最低通知等級", ["warning", "critical"])
    reason = st.text_input("新增原因", value="管理端新增 LINE 告警對象")
    if not st.button("加入通知對象"):
        return
    try:
        payload = {
            "admin_user_id": selected_id,
            "minimum_status": minimum_status,
            "reason": reason,
        }
        identity = operation_headers("line-alert-admin-target", payload)
        receipt = client.add_admin_target(
            token,
            selected_id,
            minimum_status,
            reason=reason,
            idempotency_key=identity["Idempotency-Key"],
            correlation_id=identity["X-Correlation-ID"],
        )
        _require_readback(client, token, receipt)
    except LineAdminApiError as error:
        st.error(f"新增失敗：{error}")
        return
    complete_operation("line-alert-admin-target")
    st.rerun()


def _set_target_enabled(
    client: RuntimeHealthApiClient,
    token: str | None,
    selected: AlertTargetView,
    enabled: bool,
    reason: str,
) -> AlertTargetMutationReceipt:
    payload = {
        "target_id": selected.target_id,
        "expected_version": selected.current_version,
        "enabled": enabled,
        "reason": reason,
    }
    identity = operation_headers("line-alert-target-enable", payload)
    return client.set_target_enabled(
        token,
        selected.target_id,
        expected_version=selected.current_version,
        enabled=enabled,
        reason=reason,
        idempotency_key=identity["Idempotency-Key"],
        correlation_id=identity["X-Correlation-ID"],
    )


def _reset_group_target(
    client: RuntimeHealthApiClient,
    token: str | None,
    selected: AlertTargetView,
    reason: str,
) -> AlertTargetMutationReceipt:
    payload = {
        "target_id": selected.target_id,
        "expected_version": selected.current_version,
        "reason": reason,
    }
    identity = operation_headers("line-alert-group-reset", payload)
    return client.reset_group_target(
        token,
        expected_version=selected.current_version,
        reason=reason,
        idempotency_key=identity["Idempotency-Key"],
        correlation_id=identity["X-Correlation-ID"],
    )


def _require_readback(
    client: RuntimeHealthApiClient,
    token: str | None,
    receipt: AlertTargetMutationReceipt,
) -> AlertTargetView:
    target = next(
        (item for item in client.alert_targets(token) if item.target_id == receipt.target_id),
        None,
    )
    if target is None:
        raise LineAdminApiError(
            "伺服器 receipt 找不到對應告警對象，請以原操作識別重新查詢。",
            category="unavailable",
            code="runtime_alert_target_readback_missing",
            correlation_id=receipt.correlation_id,
            retryable=True,
        )
    if (
        target.current_version != receipt.current_version
        or target.state != receipt.resulting_state
    ):
        raise LineAdminApiError(
            "伺服器 receipt 與告警對象現況不一致，未顯示成功訊息。",
            category="unavailable",
            code="runtime_alert_target_readback_mismatch",
            correlation_id=receipt.correlation_id,
            retryable=True,
        )
    return target


def _details_summary(details: Mapping[str, object] | None) -> str:
    if not isinstance(details, Mapping) or not details:
        return "-"
    visible = [
        f"{key}={value}"
        for key, value in list(details.items())[:4]
        if str(key).lower() not in {"group_id", "admin_user_id", "user_id"}
    ]
    return "、".join(visible)


__all__ = ["render_runtime_manager"]
