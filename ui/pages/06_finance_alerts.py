"""異常警示中心：5 個分頁（資料匯入異常／流程與系統警示／帳務異常／服務人員／
Line），還原 2026-07-29 版本的資訊架構，但資料來源改為 canonical 異常註冊中心
（/api/v1/anomalies，見 api/routes/anomaly_registry.py），取代已退役、未掛載的
/api/v1/finance-alerts、/api/v1/system-alerts。

ORDER-001~004（訂單配對）、DOC-SEND-001（補發送履歷）目前都導向「多月嫂排班」
頁面的處理佇列（ui/nav_helper.py），不再走一鍵直接動作：舊版
/api/v1/orders/{case_no}/send-resume 端點已標記為 retired writer，
可靠的履歷發送已改為配對方案（matching plan）擁有。
"""

from __future__ import annotations

import uuid
from typing import Any

import streamlit as st

from api.schemas.anomaly_registry import AnomalySummaryView
from ui import nav_helper
from ui.api_clients.anomaly_recovery_api_client import (
    AnomalyRecoveryApiClient,
    AnomalyRecoveryApiError,
)
from ui.api_clients.anomaly_registry_api_client import (
    AnomalyRegistryApiClient,
    AnomalyRegistryApiError,
)
from ui.pages.shared import build_admin_headers, resolve_api_base_url


title = "異常警示中心"

_MATCHING_PAGE_TITLE = "多月嫂排班"
_MATCHING_QUEUE_TARGET_KEY = "multi_caregiver_matching_case_picker"

_IMPORT_CODES = {"IMPORT-001", "IMPORT-003", "IMPORT-004", "IMPORT-006"}
_ORDER_MATCH_CODES = {"ORDER-001", "ORDER-002", "ORDER-003", "ORDER-004"}
_MISSING_DATA_CODES = {"BECLASS-001"}
_DOC_SEND_CODES = {"DOC-SEND-001"}
_OVERDUE_CODES = {"RECEIVABLE-001", "CLIENTPAYABLE-001", "RETURN-001", "SUBSIDYADVANCE-001"}
_FINANCE_CODES = {
    "finance_import_manual_review",
    "CLIENTREFUND-001",
    "GOVSUB-001",
    "GOVSUB-002",
    "GOVSUB-003",
    "GOVSUB-004",
    "GOVSUB-005",
}
_STAFF_CODES = {
    "SCHEDULE-001",
    "SCHEDULE-002",
    "SCHEDULE-003",
    "SCHEDULE-005",
    "SCHEDULE-006",
    "PAYOUT-001",
    "PAYOUT-002",
    "PAYOUT-003",
}
_LINE_CODES = {"LINE-001", "LINE-002", "LINE-004", "LINE-005"}


def _registry_client() -> AnomalyRegistryApiClient:
    return AnomalyRegistryApiClient(
        base_url=resolve_api_base_url(),
        headers=build_admin_headers(),
        timeout=20,
    )


def _recovery_client() -> AnomalyRecoveryApiClient:
    return AnomalyRecoveryApiClient(
        base_url=resolve_api_base_url(),
        headers=build_admin_headers(),
        timeout=20,
    )


def _operator_default() -> str:
    profile = st.session_state.get("line_admin_profile") or {}
    if not isinstance(profile, dict):
        return ""
    return str(profile.get("username") or "").strip()


def _load_all(
    client: AnomalyRegistryApiClient, *, active_only: bool
) -> tuple[AnomalySummaryView, ...] | None:
    try:
        return client.query_anomalies(
            active_only=active_only, limit=200, offset=0, include_snapshot=True
        )
    except AnomalyRegistryApiError as error:
        st.error(f"異常清單讀取失敗 [{error.error.code}]：{error}")
        return None


def _snapshot(summary: AnomalySummaryView) -> dict[str, Any]:
    return summary.display_snapshot or {}


def _case_no(summary: AnomalySummaryView) -> str:
    snapshot = _snapshot(summary)
    value = snapshot.get("case_no")
    return str(value) if value else summary.source_identity


def _navigate_to_matching(case_nos: list[str]) -> None:
    nav_helper.navigate_to(
        _MATCHING_PAGE_TITLE,
        queue_items=[{"case_no": case_no} for case_no in case_nos],
        queue_target_key=_MATCHING_QUEUE_TARGET_KEY,
    )


def _filter(
    items: tuple[AnomalySummaryView, ...], codes: set[str]
) -> tuple[AnomalySummaryView, ...]:
    return tuple(item for item in items if item.definition_code in codes)


def _render_summary_table(items: tuple[AnomalySummaryView, ...]) -> None:
    st.dataframe(
        [
            {
                "定義": item.definition_code,
                "案件/識別": _case_no(item),
                "狀態": item.workflow_status,
                "嚴重度": item.severity,
                "是否持續": "是" if item.predicate_active else "否",
                "版本": item.workflow_version,
            }
            for item in items
        ],
        hide_index=True,
        width="stretch",
    )


def _render_claim_resolve(
    summary: AnomalySummaryView, client: AnomalyRegistryApiClient, *, key_prefix: str
) -> None:
    st.markdown("#### 人工處理")
    operator = st.text_input(
        "操作人員", value=_operator_default(), key=f"{key_prefix}_operator"
    )
    can_claim = summary.workflow_status == "open"
    can_resolve = summary.workflow_status != "resolved"
    claim_col, resolve_col = st.columns(2)
    with claim_col:
        if st.button(
            "認領",
            key=f"{key_prefix}_claim",
            disabled=not can_claim or not operator.strip(),
        ):
            try:
                client.claim_anomaly(
                    summary.fingerprint,
                    expected_workflow_version=summary.workflow_version,
                    idempotency_key=f"finance-alert-claim-{uuid.uuid4().hex}",
                    correlation_id=f"finance-alert-claim-{uuid.uuid4().hex}",
                )
            except AnomalyRegistryApiError as error:
                st.error(f"認領失敗 [{error.error.code}]：{error}")
            else:
                st.success("已認領。")
                st.rerun()
    with resolve_col:
        reason = st.text_area("解除原因", key=f"{key_prefix}_reason")
        if st.button(
            "解除",
            key=f"{key_prefix}_resolve",
            disabled=not can_resolve or not reason.strip(),
        ):
            try:
                client.resolve_anomaly(
                    summary.fingerprint,
                    expected_workflow_version=summary.workflow_version,
                    reason=reason.strip(),
                    idempotency_key=f"finance-alert-resolve-{uuid.uuid4().hex}",
                    correlation_id=f"finance-alert-resolve-{uuid.uuid4().hex}",
                )
            except AnomalyRegistryApiError as error:
                st.error(f"解除失敗 [{error.error.code}]：{error}")
            else:
                st.success("已解除；正式核銷狀態未因此改變。")
                st.rerun()


def _render_recovery_action(
    summary: AnomalySummaryView,
    action,
    recovery_client: AnomalyRecoveryApiClient,
    *,
    key_prefix: str,
) -> None:
    if st.button(
        f"前往修復：{action.command_name}", key=f"{key_prefix}_recovery_{action.action_code}"
    ):
        try:
            link = recovery_client.query_recovery_preview_link(
                summary.fingerprint, action.action_code
            )
        except (AnomalyRecoveryApiError, ValueError) as error:
            st.error(f"查詢修復入口失敗：{error}")
        else:
            st.info(f"請前往：{link.command_name}（{link.preview_endpoint}）")


def _render_action(
    summary: AnomalySummaryView,
    action,
    recovery_client: AnomalyRecoveryApiClient,
    *,
    key_prefix: str,
) -> None:
    if action.requires_preview:
        _render_recovery_action(summary, action, recovery_client, key_prefix=key_prefix)
        return
    if action.action_code == "navigate_to_matching":
        if st.button("🎯 前往配對", key=f"{key_prefix}_navigate"):
            _navigate_to_matching([_case_no(summary)])
        return
    if action.action_code == "send_resume":
        if st.button("📨 前往配對頁面發送履歷", key=f"{key_prefix}_send_resume"):
            _navigate_to_matching([_case_no(summary)])
        return
    st.warning(f"可繼續動作：{action.action_code}（未綁定前端導向）")


def _render_detail(
    summary: AnomalySummaryView,
    registry_client: AnomalyRegistryApiClient,
    recovery_client: AnomalyRecoveryApiClient,
    *,
    key_prefix: str,
) -> None:
    try:
        detail = registry_client.query_anomaly_detail(summary.fingerprint)
    except AnomalyRegistryApiError as error:
        st.warning(f"明細載入失敗 [{error.error.code}]：{error}")
        return
    snapshot = _snapshot(summary)
    if snapshot:
        st.markdown("#### 快照內容（僅供人工判讀）")
        st.json(snapshot)
    if detail.timeline:
        st.markdown("#### 事件歷程")
        st.dataframe(
            [
                {
                    "動作": event.get("action"),
                    "操作者": event.get("actor"),
                    "原因": event.get("reason"),
                    "時間": str(event.get("created_at")),
                }
                for event in detail.timeline
            ],
            hide_index=True,
            width="stretch",
        )
    _render_claim_resolve(summary, registry_client, key_prefix=key_prefix)
    for index, action in enumerate(detail.available_actions):
        _render_action(summary, action, recovery_client, key_prefix=f"{key_prefix}_{index}")


def _render_selectable_list(
    items: tuple[AnomalySummaryView, ...],
    registry_client: AnomalyRegistryApiClient,
    recovery_client: AnomalyRecoveryApiClient,
    *,
    key_prefix: str,
) -> None:
    if not items:
        st.info("目前沒有符合條件的異常。")
        return
    _render_summary_table(items)
    selected_fingerprint = st.selectbox(
        "選擇異常",
        [item.fingerprint for item in items],
        format_func=lambda value: next(
            (
                f"{item.definition_code}｜{_case_no(item)}｜{item.workflow_status}"
                for item in items
                if item.fingerprint == value
            ),
            value,
        ),
        key=f"{key_prefix}_select",
    )
    selected = next(item for item in items if item.fingerprint == selected_fingerprint)
    _render_detail(
        selected,
        registry_client,
        recovery_client,
        key_prefix=f"{key_prefix}_{selected_fingerprint[:8]}",
    )


def _render_group(
    heading: str,
    caption: str,
    items: tuple[AnomalySummaryView, ...],
    registry_client: AnomalyRegistryApiClient,
    recovery_client: AnomalyRecoveryApiClient,
    *,
    key_prefix: str,
) -> None:
    if heading:
        st.subheader(heading)
    if caption:
        st.caption(caption)
    _render_selectable_list(items, registry_client, recovery_client, key_prefix=key_prefix)


def _render_finance_tab(
    items: tuple[AnomalySummaryView, ...],
    registry_client: AnomalyRegistryApiClient,
    recovery_client: AnomalyRecoveryApiClient,
) -> None:
    st.subheader("帳務異常")
    st.caption(
        "CLIENT、RETURN、SUBSIDY、STAFF、COMMON 的業務分類下游異常；"
        "與尚未分類的 IMPORT-006 分開顯示。"
    )
    filter_columns = st.columns(4)
    status_label = filter_columns[0].selectbox(
        "狀態",
        ["全部", "open", "claimed", "resolved"],
        key="finance_tab_status",
    )
    alert_code = filter_columns[1].text_input("警示代碼", key="finance_tab_code")
    source_domain = filter_columns[2].text_input("來源領域", key="finance_tab_domain")
    page = filter_columns[3].number_input(
        "頁次", min_value=1, value=1, step=1, key="finance_tab_page"
    )

    finance_items = _filter(items, _FINANCE_CODES)
    if status_label != "全部":
        finance_items = tuple(
            item for item in finance_items if item.workflow_status == status_label
        )
    if alert_code.strip():
        needle = alert_code.strip().lower()
        finance_items = tuple(
            item for item in finance_items if needle in item.definition_code.lower()
        )
    if source_domain.strip():
        needle = source_domain.strip().lower()
        finance_items = tuple(
            item for item in finance_items if needle in item.source_domain.lower()
        )

    limit = 50
    start = (int(page) - 1) * limit
    paged_items = finance_items[start : start + limit]
    _render_selectable_list(paged_items, registry_client, recovery_client, key_prefix="finance")


def _render_process_tab(
    items: tuple[AnomalySummaryView, ...],
    registry_client: AnomalyRegistryApiClient,
    recovery_client: AnomalyRecoveryApiClient,
) -> None:
    order_items = _filter(items, _ORDER_MATCH_CODES)
    missing_items = _filter(items, _MISSING_DATA_CODES)
    send_items = _filter(items, _DOC_SEND_CODES)
    overdue_items = _filter(items, _OVERDUE_CODES)

    sub_order, sub_missing, sub_send, sub_overdue = st.tabs(
        [
            f"🤝 訂單配對 ({len(order_items)})",
            f"📝 待補資料 ({len(missing_items)})",
            f"📤 補發送資訊 ({len(send_items)})",
            f"💸 帳務逾期提醒 ({len(overdue_items)})",
        ]
    )
    with sub_order:
        st.caption("需要人工多步驟處理，可個別「前往配對」，或一次跳轉全部案件依序處理。")
        if order_items and st.button("🎯 全部前往配對", key="order_queue_all"):
            _navigate_to_matching([_case_no(item) for item in order_items])
        _render_group("", "", order_items, registry_client, recovery_client, key_prefix="order")
    with sub_missing:
        _render_group(
            "",
            "純資料有無判斷，補齊後下一輪背景掃描會自動解除，不需要手動認領/解除。",
            missing_items,
            registry_client,
            recovery_client,
            key_prefix="missing",
        )
    with sub_send:
        _render_group(
            "",
            "已有候選月嫂願意接案，但履歷尚未發送給客戶；點「前往配對」在配對頁完成發送。",
            send_items,
            registry_client,
            recovery_client,
            key_prefix="send",
        )
    with sub_overdue:
        _render_group(
            "",
            "客戶訂金/期款、補助款應退還客戶已過到期日但尚未結清；系統不執行金流動作，"
            "需搭配銀行對帳/實際匯款處理後，下一輪背景掃描才會自動解除。",
            overdue_items,
            registry_client,
            recovery_client,
            key_prefix="overdue",
        )


def show() -> None:
    st.title(title)
    st.caption("人工檢視、認領與解除異常；本頁不建立、修改或強制對平正式帳務。")
    try:
        registry_client = _registry_client()
        recovery_client = _recovery_client()
    except (RuntimeError, ValueError) as error:
        st.error(str(error))
        return

    active_only = st.toggle("僅顯示未結束異常", value=True, key="finance_alert_active_only")
    items = _load_all(registry_client, active_only=active_only)
    if items is None:
        return

    import_tab, process_tab, finance_tab, staff_tab, line_tab = st.tabs(
        ["資料匯入異常", "流程與系統警示", "帳務異常", "服務人員", "Line"]
    )

    with import_tab:
        _render_group(
            "資料匯入異常",
            "HCM／BeClass 欄位驗證、身分衝突、銀行對帳匯入完整性。",
            _filter(items, _IMPORT_CODES),
            registry_client,
            recovery_client,
            key_prefix="import",
        )

    with process_tab:
        _render_process_tab(items, registry_client, recovery_client)

    with finance_tab:
        _render_finance_tab(items, registry_client, recovery_client)

    with staff_tab:
        _render_group(
            "服務人員",
            "排班覆核（國定假日決策/中途更換/檔期重疊/休假偏好衝突）、月嫂應付款逾期/異常變更/銀行帳戶問題。",
            _filter(items, _STAFF_CODES),
            registry_client,
            recovery_client,
            key_prefix="staff",
        )

    with line_tab:
        _render_group(
            "Line",
            "客戶/服務人員尚未綁定 LINE、群組任務推播無回覆、同一帳號同時綁定兩種身分。",
            _filter(items, _LINE_CODES),
            registry_client,
            recovery_client,
            key_prefix="line",
        )


if __name__ == "__main__":
    show()
