"""Administrator panel for viewing anomalies and steering downstream workflows."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import streamlit as st

from api.schemas.anomaly_registry import (
    AnomalySummaryView,
    DomainActionView,
)
from ui.api_clients.anomaly_registry_api_client import (
    AnomalyRegistryApiClient,
    AnomalyRegistryApiError,
)
from ui.api_clients.anomaly_recovery_api_client import (
    AnomalyRecoveryApiClient,
    AnomalyRecoveryApiError,
)
from api.schemas.anomaly_recovery import RecoveryActionView

OnDomainAction = Callable[[AnomalySummaryView, DomainActionView], None]
OnRecoveryAction = Callable[[RecoveryActionView], None]


def render_anomaly_registry_panel(
    registry_client: AnomalyRegistryApiClient,
    recovery_client: AnomalyRecoveryApiClient,
    *,
    on_recovery_action_selected: OnRecoveryAction | None = None,
    on_domain_action_selected: OnDomainAction | None = None,
) -> None:
    st.subheader("異常警示中心")
    st.caption(
        "異常來自根事實快照與公告化投影；流程先認領，再關閉，支援直接導向下游修正入口。"
    )
    query = _query_controls()
    try:
        summaries = registry_client.query_anomalies(
            active_only=query["active_only"],
            include_snapshot=query["include_snapshot"],
            limit=query["limit"],
            offset=query["offset"],
        )
    except AnomalyRegistryApiError as error:
        st.error(f"異常清單讀取失敗 [{error.error.code}]：{error}")
        return
    if not summaries:
        st.info("目前沒有可顯示的異常。")
        return
    _render_summary_table(summaries)
    for summary in summaries:
        _render_summary_card(
            summary,
            registry_client,
            recovery_client,
            on_recovery_action_selected=on_recovery_action_selected,
            on_domain_action_selected=on_domain_action_selected,
        )


def _query_controls() -> dict[str, object]:
    with st.container(border=True):
        with st.expander("異常查詢", expanded=True):
            active_only = st.toggle("僅顯示未結束異常", value=True, key="anomaly_active_only")
            include_snapshot = st.toggle(
                "查詢結果包含 display_snapshot",
                value=False,
                key="anomaly_include_snapshot",
            )
            columns = st.columns(2)
            limit = columns[0].number_input(
                "每頁筆數",
                min_value=1,
                max_value=200,
                value=100,
                step=1,
                key="anomaly_limit",
            )
            offset = columns[1].number_input(
                "位移",
                min_value=0,
                max_value=5000,
                value=0,
                step=1,
                key="anomaly_offset",
            )
    return {
        "active_only": active_only,
        "include_snapshot": include_snapshot,
        "limit": int(limit),
        "offset": int(offset),
    }


def _render_summary_table(summaries) -> None:
    st.dataframe(
        [
            {
                "定義": item.definition_code,
                "網域": item.source_domain,
                "主體": item.source_identity,
                "狀態": item.workflow_status,
                "版本": item.workflow_version,
                "是否持續": "是" if item.predicate_active else "否",
            }
            for item in summaries
        ],
        hide_index=True,
        width="stretch",
    )


def _render_summary_card(
    summary: AnomalySummaryView,
    registry_client: AnomalyRegistryApiClient,
    recovery_client: AnomalyRecoveryApiClient,
    *,
    on_recovery_action_selected: OnRecoveryAction | None,
    on_domain_action_selected: OnDomainAction | None,
) -> None:
    title = f"{summary.definition_code}｜{summary.source_domain}｜{summary.source_identity[:32]}"
    with st.expander(title, expanded=False):
        _render_basic_summary(summary)
        detail = _load_detail(registry_client, summary.fingerprint)
        if detail is None:
            return
        _render_workflow_controls(summary, registry_client)
        if detail.available_actions:
            _render_actions(
                summary,
                summary.fingerprint,
                detail.available_actions,
                recovery_client,
                on_recovery_action_selected,
                on_domain_action_selected,
            )


def _render_basic_summary(summary: AnomalySummaryView) -> None:
    columns = st.columns(3)
    columns[0].metric("指紋", summary.fingerprint[:8])
    columns[1].metric("來源識別", summary.source_identity)
    columns[2].metric("workflow 版本", summary.workflow_version)
    st.write(
        {
            "severity": summary.severity,
            "workflow_status": summary.workflow_status,
            "source_version": summary.source_version,
            "predicate_active": summary.predicate_active,
        }
    )
    if isinstance(summary.display_snapshot, dict):
        st.json(summary.display_snapshot)


def _render_workflow_controls(
    summary: AnomalySummaryView,
    client: AnomalyRegistryApiClient,
) -> None:
    with st.container(border=True):
        can_claim = summary.workflow_status == "open"
        can_resolve = summary.workflow_status != "resolved"
        if st.button("認領", key=f"anomaly_claim_{summary.fingerprint}", disabled=not can_claim):
            if can_claim:
                _claim(summary, client)
        reason = st.text_input(
            "解決原因（標記已處理）",
            key=f"anomaly_resolve_reason_{summary.fingerprint}",
        )
        if st.button("標記為已處理", key=f"anomaly_resolve_{summary.fingerprint}", disabled=not can_resolve):
            if can_resolve and reason.strip():
                _resolve(summary, client, reason.strip())
            elif not reason.strip():
                st.error("請先填寫原因。")


def _render_actions(
    summary: AnomalySummaryView,
    fingerprint: str,
    actions: list[DomainActionView],
    recovery_client: AnomalyRecoveryApiClient,
    on_recovery_action_selected: OnRecoveryAction | None,
    on_domain_action_selected: OnDomainAction | None,
) -> None:
    with st.container(border=True):
        st.write("可用修復動作")
        for index, action in enumerate(actions, start=1):
            if action.requires_preview:
                if st.button(
                    f"前往修復：{action.command_name}",
                    key=f"anomaly_recovery_action_{fingerprint}_{index}",
                ):
                    _resolve_to_action(
                        fingerprint,
                        action,
                        recovery_client,
                        on_recovery_action_selected,
                    )
                continue
            if on_domain_action_selected is None:
                st.warning(
                    f"可繼續動作：{action.action_code}（未綁定前端導向）"
                )
                continue
            if st.button(
                f"導向：{action.command_name}",
                key=f"anomaly_domain_action_{fingerprint}_{index}",
            ):
                on_domain_action_selected(summary, action)


def _load_detail(client: AnomalyRegistryApiClient, fingerprint: str):
    try:
        return client.query_anomaly_detail(fingerprint)
    except AnomalyRegistryApiError as error:
        st.warning(f"異常明細載入失敗 [{error.error.code}]：{error}")
        return None


def _resolve_to_action(
    fingerprint: str,
    action,
    recovery_client: AnomalyRecoveryApiClient,
    on_recovery_action_selected: OnRecoveryAction | None,
) -> None:
    if on_recovery_action_selected is None:
        st.warning("修復導向入口尚未綁定。")
        return
    try:
        recovery_action = recovery_client.query_recovery_preview_link(
            fingerprint,
            action.action_code,
        )
    except (AnomalyRecoveryApiError, ValueError) as error:
        st.error(f"查詢修復入口失敗：{error}")
        return
    on_recovery_action_selected(recovery_action)


def _claim(summary: AnomalySummaryView, client: AnomalyRegistryApiClient) -> None:
    try:
        client.claim_anomaly(
            summary.fingerprint,
            expected_workflow_version=summary.workflow_version,
            idempotency_key=f"anomaly-claim-{uuid.uuid4().hex}",
            correlation_id=f"anomaly-claim-{uuid.uuid4().hex}",
        )
        st.success("異常認領完成。")
        st.rerun()
    except AnomalyRegistryApiError as error:
        st.error(f"認領失敗 [{error.error.code}]：{error}")


def _resolve(summary: AnomalySummaryView, client: AnomalyRegistryApiClient, reason: str) -> None:
    try:
        client.resolve_anomaly(
            summary.fingerprint,
            expected_workflow_version=summary.workflow_version,
            reason=reason,
            idempotency_key=f"anomaly-resolve-{uuid.uuid4().hex}",
            correlation_id=f"anomaly-resolve-{uuid.uuid4().hex}",
        )
        st.success("異常已標記為已處理。")
        st.rerun()
    except AnomalyRegistryApiError as error:
        st.error(f"標記已處理失敗 [{error.error.code}]：{error}")
