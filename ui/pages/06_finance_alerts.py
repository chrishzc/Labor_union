"""
File: 06_finance_alerts.py
Description: 顯示canonical異常警示，並提供已核准的人工處理入口。
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
from ui.api_clients.import_warning_tracking_api_client import (
    ImportWarningTrackingApiClient,
    ImportWarningTrackingApiError,
)
from api.schemas.import_warning_tracking import WarningTransitionBody
from ui.api_clients.finance_import_api_client import FinanceImportApiClient
from ui.api_clients.client_refund_reversal_api_client import ClientRefundReversalApiClient
from ui.api_clients.client_receipt_reconciliation_api_client import ClientReceiptReconciliationApiClient
from api.schemas.client_receipt_reconciliation import ClientReceiptApplyBody, ClientReceiptPreviewBody
from api.schemas.client_refund_reversal import (
    ClientRefundApplyBody,
    ClientRefundPreviewBody,
    ClientOverRefundRecoveryMatchedApplyBody,
    ClientOverRefundRecoveryMatchedPreviewBody,
    ClientOverRefundRecoveryMatchingApplyBody,
    ClientOverRefundRecoveryMatchingPreviewBody,
)
from ui.api_clients.staff_payout_api_client import StaffPayoutApiClient, StaffPayoutApiError
from api.schemas.staff_payout import (
    StaffOverpaymentRecoveryMatchedApplyBody,
    StaffOverpaymentRecoveryMatchedPreviewBody,
    StaffOverpaymentRecoveryMatchingApplyBody,
    StaffOverpaymentRecoveryMatchingPreviewBody,
)
from ui.api_clients.government_subsidy_api_client import (
    GovernmentSubsidyApiClient,
    GovernmentSubsidyApiError,
)
from api.schemas.government_subsidy import (
    GovernmentSubsidyOverpaymentDispositionApplyBody,
    GovernmentSubsidyOverpaymentDispositionPreviewBody,
    GovernmentOverpaymentReturnReconciliationApplyBody,
    GovernmentOverpaymentReturnReconciliationPreviewBody,
    GovernmentSubsidyOverpaymentOffsetIntentView,
)
from ui.pages.shared import build_admin_headers, resolve_api_base_url


title = "異常警示中心"

_MATCHING_PAGE_TITLE = "多月嫂排班"
_MATCHING_QUEUE_TARGET_KEY = "multi_caregiver_matching_case_picker"
_FINANCE_RECOVERY_SELECTION_KEY = "finance_anomaly_recovery_selection"

_IMPORT_CODES = {
    "HISTORICAL-ORDER-001",
    "IMPORT-001",
    "IMPORT-003",
    "IMPORT-004",
    "IMPORT-006",
}
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
    "GOVSUB-006",
    "client_over_refund_recovery_open",
    "staff_overpayment_recovery_open",
    "staff_payout_underpayment",
    "staff_payout_overpayment",
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

_ALERT_CODE_LABELS = {
    "ORDER-001": "訂單未配對月嫂－資訊-1未發送",
    "ORDER-002": "訂單未配對月嫂－資訊-2未發送",
    "ORDER-003": "已發資訊-1但候選人未回覆",
    "ORDER-004": "已發資訊-2但候選人未回覆",
    "BECLASS-001": "客戶尚未填寫 BeClass 問卷",
    "LINE-001": "客戶尚未綁定 LINE",
    "LINE-005": "服務人員尚未綁定 LINE",
    "DOC-SEND-001": "履歷尚未發送給客戶",
    "IMPORT-001": "BeClass 匯入欄位驗證失敗",
    "IMPORT-003": "跨表整合去重/關聯衝突",
    "IMPORT-004": "HCM 匯入欄位驗證失敗",
    "IMPORT-006": "銀行對帳匯入完整性異常",
    "HISTORICAL-ORDER-001": "歷史訂單匯入待人工確認",
    "RECEIVABLE-001": "客戶應收帳款逾期未收齊",
    "CLIENTPAYABLE-001": "應付客戶款項逾期未付",
    "SUBSIDYADVANCE-001": "政府補助墊付款項待核對",
    "PAYOUT-001": "服務人員應付款逾期未匯",
    "PAYOUT-002": "服務人員應付款異常變更",
    "PAYOUT-003": "服務人員銀行帳戶資料異常",
    "RETURN-001": "補助款應退還客戶逾期未退",
    "LINE-002": "月嫂群組任務逾期未回覆",
    "LINE-004": "LINE 帳號重複綁定衝突",
    "SCHEDULE-001": "服務檔期跨國定假日，行政尚未決策放假與否",
    "SCHEDULE-002": "月嫂服務中途更換人員，需人工複核財務拆分",
    "SCHEDULE-003": "月嫂檔期重疊/雙重預約",
    "SCHEDULE-005": "國定假日休假偏好衝突",
    "SCHEDULE-006": "服務天數與實際排班天數不平衡",
    "finance_import_manual_review": "銀行對帳需人工分類",
    "CLIENTREFUND-001": "客戶退款案件下游異常",
    "GOVSUB-001": "政府補助收款無唯一批次",
    "GOVSUB-002": "政府補助收款分配歧義",
    "GOVSUB-003": "政府補助批次完整性異常",
    "GOVSUB-004": "政府補助沖正異常",
    "GOVSUB-005": "政府補助請款資料漂移",
    "GOVSUB-006": "政府補助溢撥待處置",
    "client_over_refund_recovery_open": "客戶退款超額追償待收回",
    "staff_overpayment_recovery_open": "月嫂超額付款追償待收回",
    "staff_payout_underpayment": "月嫂付款不足待補足",
    "staff_payout_overpayment": "月嫂付款超額待追償",
}
_STATUS_LABELS = {
    "open": "🟡 待處理",
    "claimed": "🔵 已認領",
    "resolved": "✅ 已解決",
}


def _alert_code_label(code: str) -> str:
    return _ALERT_CODE_LABELS.get(code, code)


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status)


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


def _import_warning_tracking_client() -> ImportWarningTrackingApiClient:
    return ImportWarningTrackingApiClient(
        base_url=resolve_api_base_url(), headers=build_admin_headers(), timeout=20
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
    for key in (
        "pending_staff_calendar_staff_id",
        "pending_staff_calendar_year",
        "pending_staff_calendar_month",
        "pending_staff_calendar_note",
    ):
        st.session_state.pop(key, None)
    st.session_state["matching_center_plan_navigation_token"] = uuid.uuid4().hex
    nav_helper.navigate_to(
        _MATCHING_PAGE_TITLE,
        queue_items=[{"case_no": case_no} for case_no in case_nos],
        queue_target_key=_MATCHING_QUEUE_TARGET_KEY,
    )


def _navigate_to_staff_calendar(staff_id: int, date_text: str, note: str) -> None:
    """跳到「多月嫂排班」→「服務人員月曆」，預先選好月嫂與該日期所在年月，
    並在上方顯示明確的異常原因。跟 _navigate_to_matching 不同，這裡不透過
    月嫂配對中心的佇列機制（那個只服務「洽談中」案件），而是直接把月嫂
    行事曆定位到出問題的月份，不受案件目前狀態影響。"""
    year, month = int(date_text[:4]), int(date_text[5:7])
    nav_helper.end_queue()
    st.session_state["pending_staff_calendar_staff_id"] = staff_id
    st.session_state["pending_staff_calendar_year"] = year
    st.session_state["pending_staff_calendar_month"] = month
    st.session_state["pending_staff_calendar_note"] = note
    nav_helper.navigate_to(_MATCHING_PAGE_TITLE)


def _navigate_to_assignment_repair(case_no: str) -> None:
    nav_helper.end_queue()
    st.session_state["pending_scheduling_case_no"] = case_no
    st.session_state["scheduling_workspace"] = "案件人力配置"
    nav_helper.navigate_to(_MATCHING_PAGE_TITLE)


def _filter(
    items: tuple[AnomalySummaryView, ...], codes: set[str]
) -> tuple[AnomalySummaryView, ...]:
    return tuple(item for item in items if item.definition_code in codes)


def _render_summary_table(items: tuple[AnomalySummaryView, ...]) -> None:
    st.dataframe(
        [
            {
                "警示類型": _display_alert_label(item),
                "案件/識別": _case_no(item),
                "狀態": _status_label(item.workflow_status),
            }
            for item in items
        ],
        hide_index=True,
        width="stretch",
    )


def _display_alert_label(item: AnomalySummaryView) -> str:
    issue_codes = _snapshot(item).get("issue_codes") or ()
    if item.definition_code == "IMPORT-004" and any(
        "hcm_duplicate_application" in str(code) for code in issue_codes
    ):
        return "疑似重複申請，請公會人員確認"
    return _alert_code_label(item.definition_code)


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
        action.label or "開啟修復",
        key=f"{key_prefix}_recovery_{action.action_key}",
    ):
        try:
            link = recovery_client.query_recovery_preview_link(
                summary.fingerprint, action.action_key
            )
        except (AnomalyRecoveryApiError, ValueError) as error:
            st.error(f"查詢修復入口失敗：{error}")
        else:
            _select_recovery(summary, link)


def _select_recovery(summary: AnomalySummaryView, link) -> None:
    renderer = _recovery_renderer(link.owning_domain, link.form_schema_key)
    if renderer is None:
        st.warning("recovery_action_not_supported：此異常尚未提供可直接處理的修復表單。")
        return
    st.session_state[_FINANCE_RECOVERY_SELECTION_KEY] = {
        "fingerprint": summary.fingerprint,
        "action_label": link.label,
        "owning_domain": link.owning_domain,
        "form_schema_key": link.form_schema_key,
        "source_bindings": link.source_bindings,
    }
    st.rerun()


def _recovery_renderer(owning_domain: str, form_schema_key: str):
    """Registry-key dispatch only; a descriptor never supplies a raw endpoint or callable."""
    renderers = {
        ("finance_import", "finance_import.correction.v1"):
            _render_finance_import_correction,
        ("government_subsidy", "government_subsidy.payer_refund_account.v1"):
            _render_government_refund_account,
        ("government_subsidy", "government_subsidy.overpayment.disposition.v1"):
            _render_government_overpayment_disposition,
        ("government_subsidy", "government_subsidy.overpayment.return_reconciliation.v1"):
            _render_government_return_reconciliation,
        ("client_finance", "client_finance.over_refund_recovery.collection.v1"):
            _render_client_over_refund_recovery_collection,
        ("client_finance", "client_finance.over_refund_recovery.matching.v1"):
            _render_client_over_refund_recovery_matching,
        ("client_finance", "client_finance.refund_overage.v1"):
            _render_client_refund_overage,
        ("client_finance", "client_finance.receipt_overage.v1"):
            _render_client_receipt_overage,
        ("staff_payables", "staff_payables.overpayment_recovery.collection.v1"):
            _render_staff_overpayment_recovery_collection,
        ("staff_payables", "staff_payables.overpayment_recovery.matching.v1"):
            _render_staff_overpayment_recovery_matching,
        ("staff_payables", "staff_payables.payout_difference.v1"):
            _render_staff_payout_difference,
    }
    return renderers.get((owning_domain, form_schema_key))


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
    show_manual_actions: bool = True,
) -> None:
    try:
        detail = registry_client.query_anomaly_detail(summary.fingerprint)
    except AnomalyRegistryApiError as error:
        st.warning(f"明細載入失敗 [{error.error.code}]：{error}")
        return
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
    # 這幾個分頁的異常會隨背景掃描自動解除，不需要人工認領/解除；
    # 保留 show_manual_actions 開關，未來要恢復手動處理只要傳 True。
    if show_manual_actions:
        _render_claim_resolve(summary, registry_client, key_prefix=key_prefix)
    for index, action in enumerate(detail.available_actions):
        _render_action(summary, action, recovery_client, key_prefix=f"{key_prefix}_{index}")


def _render_selectable_list(
    items: tuple[AnomalySummaryView, ...],
    registry_client: AnomalyRegistryApiClient,
    recovery_client: AnomalyRecoveryApiClient,
    *,
    key_prefix: str,
    show_manual_actions: bool = True,
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
                f"{_alert_code_label(item.definition_code)}｜{_case_no(item)}｜{_status_label(item.workflow_status)}"
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
        show_manual_actions=show_manual_actions,
    )


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
    _render_selected_finance_recovery()
    _render_selectable_list(
        paged_items,
        registry_client,
        recovery_client,
        key_prefix="finance",
        show_manual_actions=False,
    )


def _render_selected_finance_recovery() -> None:
    selection = st.session_state.get(_FINANCE_RECOVERY_SELECTION_KEY)
    if not isinstance(selection, dict):
        return
    action_label = selection.get("action_label")
    owning_domain = selection.get("owning_domain")
    form_schema_key = selection.get("form_schema_key")
    source_bindings = selection.get("source_bindings")
    if not isinstance(action_label, str) or not isinstance(owning_domain, str) or not isinstance(form_schema_key, str) or not isinstance(source_bindings, dict):
        st.session_state.pop(_FINANCE_RECOVERY_SELECTION_KEY, None)
        return
    st.divider()
    if st.button("取消本次帳務異常處理", key="cancel_finance_anomaly_recovery"):
        st.session_state.pop(_FINANCE_RECOVERY_SELECTION_KEY, None)
        st.rerun()
    renderer = _recovery_renderer(owning_domain, form_schema_key)
    if renderer is None:
        st.error("recovery_action_not_supported：修復表單版本尚未支援。")
        return
    renderer(source_bindings, action_label)


def _render_finance_import_correction(source_bindings: dict[str, object], action_label: str) -> None:
    row_identity = source_bindings.get("finance_import_row_identity")
    if not isinstance(row_identity, str) or not row_identity:
        st.error("recovery_source_binding_incomplete：修復動作缺少銀行流水識別。")
        return
    try:
        from ui.pages.finance_import.panel import render_finance_import_correction_panel

        client = FinanceImportApiClient(
            base_url=resolve_api_base_url(),
            headers=build_admin_headers(),
        )
        render_finance_import_correction_panel(
            client,
            row_identity=row_identity,
            action_label=action_label,
        )
    except Exception as error:
        st.error(f"帳務異常處理工作區載入失敗：{error}")


def _render_government_refund_account(source_bindings: dict[str, object], action_label: str) -> None:
    del source_bindings, action_label
    try:
        from ui.api_clients.government_subsidy_api_client import GovernmentSubsidyApiClient
        from ui.pages.government_subsidy.payer_master_panel import (
            render_government_refund_account_editor,
        )

        render_government_refund_account_editor(
            GovernmentSubsidyApiClient(
                base_url=resolve_api_base_url(),
                headers=build_admin_headers(),
            ),
            key_prefix="finance_anomaly_government_refund_account",
        )
    except Exception as error:
        st.error(f"政府退款帳戶工作區載入失敗：{error}")


def _render_government_overpayment_disposition(
    source_bindings: dict[str, object],
    action_label: str,
) -> None:
    identity = source_bindings.get("overpayment_identity")
    version = source_bindings.get("overpayment_version")
    if not isinstance(identity, str) or not identity or isinstance(version, bool) or not isinstance(version, int):
        st.error("recovery_source_binding_incomplete：缺少政府溢撥識別或版本。")
        return
    st.markdown(f"#### {action_label}")
    key_prefix = f"government_disposition_{identity}"
    disposition = st.radio("處置方式", ("offset", "return"), format_func=lambda value: "抵扣已核准補助" if value == "offset" else "建立政府退款應付", key=f"{key_prefix}_kind")
    evidence = st.text_input("法源／核准證據", key=f"{key_prefix}_evidence")
    reason = st.text_area("處置原因", key=f"{key_prefix}_reason")
    preview_body = _government_disposition_preview_body(
        identity,
        disposition,
        evidence,
        key_prefix,
    )
    if preview_body is None:
        return
    signature = (preview_body.model_dump_json(), reason.strip())
    preview_key = f"{key_prefix}_preview"
    client = GovernmentSubsidyApiClient(
        base_url=resolve_api_base_url(),
        headers=build_admin_headers(),
    )
    if st.button(
        "Preview 處置",
        key=f"{key_prefix}_preview_button",
        disabled=not reason.strip(),
    ):
        try:
            preview = client.preview_overpayment_disposition(
                preview_body,
                f"government-overpayment-disposition-preview-{uuid.uuid4().hex}",
            )
        except GovernmentSubsidyApiError as error:
            st.error(f"Preview 失敗 [{error.error.code}]：{error}")
        else:
            st.session_state[preview_key] = (signature, preview)
            st.rerun()
    stored = st.session_state.get(preview_key)
    if not isinstance(stored, tuple) or len(stored) != 2 or stored[0] != signature:
        st.info("請先成功 Preview；更動處置內容後必須重新 Preview。")
        return
    preview = stored[1]
    st.caption(f"本次處置 {preview.disposition_amount_ntd:,} 元，處置後剩餘 {preview.remaining_after_ntd:,} 元。")
    apply_body = GovernmentSubsidyOverpaymentDispositionApplyBody(
        **preview_body.model_dump(),
        expected_overpayment_version=version,
        preview_fingerprint=preview.preview_fingerprint,
        reason=reason,
    )
    if st.button("Apply 處置", key=f"{key_prefix}_apply", disabled=not reason.strip()):
        try:
            receipt = client.apply_overpayment_disposition(
                apply_body,
                f"government-overpayment-disposition-{uuid.uuid4().hex}",
                f"government-overpayment-disposition-apply-{uuid.uuid4().hex}",
            )
        except GovernmentSubsidyApiError as error:
            st.error(f"Apply 失敗 [{error.error.code}]：{error}")
        else:
            st.success(f"已完成處置；剩餘 {receipt.remaining_after_ntd:,} 元。")
            st.session_state.pop(preview_key, None)


def _render_government_return_reconciliation(
    source_bindings: dict[str, object], action_label: str,
) -> None:
    row_id = _matching_row_id(source_bindings)
    if row_id is None:
        return
    st.markdown(f"#### {action_label}")
    key_prefix = f"government_return_reconciliation_{row_id}"
    overpayment_identity = st.text_input("政府溢撥識別", key=f"{key_prefix}_overpayment")
    reason = st.text_area("核對原因", key=f"{key_prefix}_reason")
    evidence = st.text_input("對帳證據", key=f"{key_prefix}_evidence")
    if not overpayment_identity.strip():
        st.info("請選定唯一政府退款單所屬溢撥識別，再產生 Preview。")
        return
    preview_body = GovernmentOverpaymentReturnReconciliationPreviewBody(
        overpayment_identity=overpayment_identity.strip(), finance_import_row_id=row_id,
    )
    signature = (preview_body.model_dump_json(), reason.strip(), evidence.strip())
    preview_key = f"{key_prefix}_preview"
    client = GovernmentSubsidyApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers())
    if st.button("Preview 對帳", key=f"{preview_key}_button", disabled=not reason.strip() or not evidence.strip()):
        try:
            preview = client.preview_overpayment_return_reconciliation(
                preview_body, f"government-return-reconciliation-preview-{uuid.uuid4().hex}"
            )
        except GovernmentSubsidyApiError as error:
            st.error(f"Preview 失敗 [{error.error.code}]：{error}")
        else:
            st.session_state[preview_key] = (signature, preview)
            st.rerun()
    stored = st.session_state.get(preview_key)
    if not isinstance(stored, tuple) or len(stored) != 2 or stored[0] != signature:
        st.info("請先成功 Preview；變更退款單、原因或證據後必須重新 Preview。")
        return
    preview = stored[1]
    st.caption(f"此出款列核對 {preview.amount_ntd:,} 元；核對後退款單剩餘 {preview.remaining_after_ntd:,} 元。")
    apply_body = GovernmentOverpaymentReturnReconciliationApplyBody(
        **preview_body.model_dump(), expected_overpayment_version=preview.overpayment_version,
        preview_fingerprint=preview.preview_fingerprint, reason=reason.strip(),
        evidence_reference=evidence.strip(),
    )
    if st.button("Apply 對帳", key=f"{preview_key}_apply"):
        try:
            receipt = client.apply_overpayment_return_reconciliation(
                apply_body, f"government-return-reconciliation-{uuid.uuid4().hex}",
                f"government-return-reconciliation-apply-{uuid.uuid4().hex}",
            )
        except GovernmentSubsidyApiError as error:
            st.error(f"Apply 失敗 [{error.error.code}]：{error}")
        else:
            st.success(f"已核對退款單；剩餘 {receipt.remaining_after_ntd:,} 元。")
            st.session_state.pop(preview_key, None)


def _render_client_over_refund_recovery_collection(
    source_bindings: dict[str, object], action_label: str
) -> None:
    required_text = ("case_no", "recovery_identity", "finance_import_row_identity", "matching_identity")
    if any(not isinstance(source_bindings.get(key), str) or not source_bindings[key] for key in required_text):
        st.error("recovery_source_binding_incomplete：缺少客戶追償配對識別。")
        return
    required_versions = ("account_version", "recovery_version", "matching_version")
    if any(isinstance(source_bindings.get(key), bool) or not isinstance(source_bindings.get(key), int) for key in required_versions):
        st.error("recovery_source_binding_incomplete：缺少客戶追償版本。")
        return
    case_no = str(source_bindings["case_no"])
    recovery_identity = str(source_bindings["recovery_identity"])
    row_id = int(str(source_bindings["finance_import_row_identity"]))
    matching_identity = str(source_bindings["matching_identity"])
    matching_version = int(source_bindings["matching_version"])
    st.markdown(f"#### {action_label}")
    reason = st.text_area("收款核對原因", key=f"client_recovery_reason_{matching_identity}")
    evidence = st.text_input("收款證據", key=f"client_recovery_evidence_{matching_identity}")
    body = ClientOverRefundRecoveryMatchedPreviewBody(
        recovery_identity=recovery_identity, finance_import_row_id=row_id,
        matching_identity=matching_identity, matching_version=matching_version,
    )
    signature = (body.model_dump_json(), reason.strip(), evidence.strip())
    preview_key = f"client_recovery_preview_{matching_identity}"
    client = ClientRefundReversalApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers())
    if st.button("Preview 收款", key=f"{preview_key}_button", disabled=not reason.strip() or not evidence.strip()):
        try:
            preview = client.preview_matched_refund_overage_recovery(case_no, body)
        except Exception as error:
            st.error(f"Preview 失敗：{error}")
        else:
            st.session_state[preview_key] = (signature, preview)
            st.rerun()
    stored = st.session_state.get(preview_key)
    if not isinstance(stored, tuple) or len(stored) != 2 or stored[0] != signature:
        st.info("請先成功 Preview；變更原因或證據後必須重新 Preview。")
        return
    preview = stored[1]
    st.caption(f"本次收款 {preview.amount_received_ntd:,} 元；收款後剩餘 {preview.remaining_after_ntd:,} 元。")
    apply = ClientOverRefundRecoveryMatchedApplyBody(
        **body.model_dump(), expected_recovery_version=int(source_bindings["recovery_version"]),
        expected_account_version=int(source_bindings["account_version"]),
        preview_fingerprint=preview.preview_fingerprint, reason=f"{reason.strip()}｜evidence:{evidence.strip()}",
    )
    if st.button("Apply 收款", key=f"{preview_key}_apply"):
        try:
            receipt = client.apply_matched_refund_overage_recovery(case_no, apply, f"client-recovery-collect-{uuid.uuid4().hex}")
        except Exception as error:
            st.error(f"Apply 失敗：{error}")
        else:
            st.success(f"已核銷；追償餘額 {receipt.remaining_after_ntd:,} 元。")
            st.session_state.pop(preview_key, None)


def _render_client_over_refund_recovery_matching(
    source_bindings: dict[str, object], action_label: str
) -> None:
    row_id = _matching_row_id(source_bindings)
    if row_id is None:
        return
    key_prefix = f"client_recovery_matching_{row_id}"
    st.markdown(f"#### {action_label}")
    case_no = st.text_input("案件編號", key=f"{key_prefix}_case")
    recovery_identity = st.text_input("客戶追償識別", key=f"{key_prefix}_recovery")
    reason = st.text_area("配對原因", key=f"{key_prefix}_reason")
    evidence = st.text_input("配對證據", key=f"{key_prefix}_evidence")
    if not case_no.strip() or not recovery_identity.strip():
        st.info("請確認唯一案件與追償識別後，再產生 Preview。")
        return
    body = ClientOverRefundRecoveryMatchingPreviewBody(
        recovery_identity=recovery_identity.strip(), finance_import_row_id=row_id
    )
    signature = (case_no.strip(), body.model_dump_json(), reason.strip(), evidence.strip())
    preview_key = f"{key_prefix}_preview"
    client = ClientRefundReversalApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers())
    if st.button("Preview 配對", key=f"{preview_key}_button", disabled=not reason.strip() or not evidence.strip()):
        try:
            preview = client.preview_refund_overage_recovery_matching(case_no.strip(), body)
        except Exception as error:
            st.error(f"Preview 失敗：{error}")
        else:
            st.session_state[preview_key] = (signature, preview)
            st.rerun()
    stored = st.session_state.get(preview_key)
    if not isinstance(stored, tuple) or len(stored) != 2 or stored[0] != signature:
        st.info("請先成功 Preview；變更案件、追償、原因或證據後必須重新 Preview。")
        return
    preview = stored[1]
    st.caption("Preview 已確認此入款列、案件與追償可建立不可變配對。")
    apply = ClientOverRefundRecoveryMatchingApplyBody(
        **body.model_dump(), expected_recovery_version=preview.recovery_version,
        expected_account_version=preview.account_version,
        preview_fingerprint=preview.preview_fingerprint,
        reason=f"{reason.strip()}｜evidence:{evidence.strip()}",
    )
    if st.button("Apply 建立配對", key=f"{preview_key}_apply"):
        try:
            client.apply_refund_overage_recovery_matching(
                case_no.strip(), apply, f"client-recovery-match-{uuid.uuid4().hex}"
            )
        except Exception as error:
            st.error(f"Apply 失敗：{error}")
        else:
            st.success("已建立配對；異常中心將顯示正式收款動作。")
            st.session_state.pop(preview_key, None)


def _render_client_refund_overage(source_bindings: dict[str, object], action_label: str) -> None:
    row_id = _matching_row_id(source_bindings)
    if row_id is None:
        return
    st.markdown(f"#### {action_label}")
    key = f"client_refund_overage_{row_id}"
    case_no = st.text_input("案件編號", key=f"{key}_case")
    obligations = tuple(value.strip() for value in st.text_area("退款義務識別（每行一筆）", key=f"{key}_obligations").splitlines() if value.strip())
    reason = st.text_area("處理原因", key=f"{key}_reason")
    if not case_no.strip() or not obligations:
        st.info("請輸入唯一案件與退款義務識別。")
        return
    body = ClientRefundPreviewBody(finance_import_row_ids=[row_id], obligation_identities=list(obligations))
    client = ClientRefundReversalApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers())
    signature = (case_no.strip(), body.model_dump_json(), reason.strip())
    preview_key = f"{key}_preview"
    if st.button("Preview 退款多匯", key=f"{preview_key}_button", disabled=not reason.strip()):
        try: preview = client.preview_refund_overage(case_no.strip(), body)
        except Exception as error: st.error(f"Preview 失敗：{error}")
        else: st.session_state[preview_key] = (signature, preview); st.rerun()
    stored = st.session_state.get(preview_key)
    if not isinstance(stored, tuple) or len(stored) != 2 or stored[0] != signature:
        st.info("請先成功 Preview。")
        return
    preview = stored[1]
    apply = ClientRefundApplyBody(**body.model_dump(), expected_account_version=preview.account_version, preview_fingerprint=preview.preview_fingerprint, reason=reason.strip())
    if st.button("Apply 退款多匯", key=f"{preview_key}_apply"):
        try: client.apply_refund_overage(case_no.strip(), apply, f"client-refund-overage-{uuid.uuid4().hex}")
        except Exception as error: st.error(f"Apply 失敗：{error}")
        else: st.success("已建立客戶退款超額追償。"); st.session_state.pop(preview_key, None)


def _render_staff_overpayment_recovery_collection(source_bindings: dict[str, object], action_label: str) -> None:
    required_text = ("recovery_identity", "finance_import_row_identity", "matching_identity")
    required_numbers = ("recovery_version", "staff_payables_version", "matching_version")
    if any(not isinstance(source_bindings.get(key), str) or not source_bindings[key] for key in required_text) or any(isinstance(source_bindings.get(key), bool) or not isinstance(source_bindings.get(key), int) for key in required_numbers):
        st.error("recovery_source_binding_incomplete：缺少月嫂追償配對或版本。")
        return
    identity = str(source_bindings["matching_identity"])
    body = StaffOverpaymentRecoveryMatchedPreviewBody(recovery_identity=str(source_bindings["recovery_identity"]), finance_import_row_id=int(str(source_bindings["finance_import_row_identity"])), matching_identity=identity, matching_version=int(source_bindings["matching_version"]))
    st.markdown(f"#### {action_label}")
    reason = st.text_area("收款核對原因", key=f"staff_recovery_reason_{identity}")
    evidence = st.text_input("收款證據", key=f"staff_recovery_evidence_{identity}")
    signature = (body.model_dump_json(), reason.strip(), evidence.strip())
    preview_key = f"staff_recovery_preview_{identity}"
    client = StaffPayoutApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers())
    if st.button("Preview 收款", key=f"{preview_key}_button", disabled=not reason.strip() or not evidence.strip()):
        try: preview = client.preview_matched_overpayment_recovery_collection(body, f"staff-recovery-preview-{uuid.uuid4().hex}")
        except StaffPayoutApiError as error: st.error(f"Preview 失敗 [{error.error.code}]：{error}")
        else: st.session_state[preview_key] = (signature, preview); st.rerun()
    stored = st.session_state.get(preview_key)
    if not isinstance(stored, tuple) or len(stored) != 2 or stored[0] != signature:
        st.info("請先成功 Preview；變更原因或證據後必須重新 Preview。")
        return
    preview = stored[1]
    st.caption(f"本次收款 {preview.received_amount_ntd:,} 元；收款後剩餘 {preview.remaining_after_ntd:,} 元。")
    apply = StaffOverpaymentRecoveryMatchedApplyBody(**body.model_dump(), expected_recovery_version=int(source_bindings["recovery_version"]), expected_staff_payables_version=int(source_bindings["staff_payables_version"]), preview_fingerprint=preview.preview_fingerprint, reason=f"{reason.strip()}｜evidence:{evidence.strip()}")
    if st.button("Apply 收款", key=f"{preview_key}_apply"):
        try: receipt = client.apply_matched_overpayment_recovery_collection(apply, f"staff-recovery-collect-{uuid.uuid4().hex}", f"staff-recovery-apply-{uuid.uuid4().hex}")
        except StaffPayoutApiError as error: st.error(f"Apply 失敗 [{error.error.code}]：{error}")
        else: st.success(f"已核銷；追償餘額 {receipt.remaining_after_ntd:,} 元。"); st.session_state.pop(preview_key, None)


def _render_staff_overpayment_recovery_matching(
    source_bindings: dict[str, object], action_label: str
) -> None:
    row_id = _matching_row_id(source_bindings)
    if row_id is None:
        return
    key_prefix = f"staff_recovery_matching_{row_id}"
    st.markdown(f"#### {action_label}")
    recovery_identity = st.text_input("月嫂追償識別", key=f"{key_prefix}_recovery")
    reason = st.text_area("配對原因", key=f"{key_prefix}_reason")
    evidence = st.text_input("配對證據", key=f"{key_prefix}_evidence")
    if not recovery_identity.strip():
        st.info("請確認唯一月嫂追償識別後，再產生 Preview。")
        return
    body = StaffOverpaymentRecoveryMatchingPreviewBody(
        recovery_identity=recovery_identity.strip(), finance_import_row_id=row_id
    )
    signature = (body.model_dump_json(), reason.strip(), evidence.strip())
    preview_key = f"{key_prefix}_preview"
    client = StaffPayoutApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers())
    if st.button("Preview 配對", key=f"{preview_key}_button", disabled=not reason.strip() or not evidence.strip()):
        try:
            preview = client.preview_overpayment_recovery_matching(body, f"staff-recovery-match-preview-{uuid.uuid4().hex}")
        except StaffPayoutApiError as error:
            st.error(f"Preview 失敗 [{error.error.code}]：{error}")
        else:
            st.session_state[preview_key] = (signature, preview)
            st.rerun()
    stored = st.session_state.get(preview_key)
    if not isinstance(stored, tuple) or len(stored) != 2 or stored[0] != signature:
        st.info("請先成功 Preview；變更追償、原因或證據後必須重新 Preview。")
        return
    preview = stored[1]
    st.caption("Preview 已確認此入款列與月嫂追償可建立不可變配對。")
    apply = StaffOverpaymentRecoveryMatchingApplyBody(
        **body.model_dump(), expected_recovery_version=preview.recovery_version,
        expected_staff_payables_version=preview.staff_payables_version,
        preview_fingerprint=preview.preview_fingerprint,
        reason=f"{reason.strip()}｜evidence:{evidence.strip()}",
    )
    if st.button("Apply 建立配對", key=f"{preview_key}_apply"):
        try:
            client.apply_overpayment_recovery_matching(
                apply, f"staff-recovery-match-{uuid.uuid4().hex}",
                f"staff-recovery-match-apply-{uuid.uuid4().hex}",
            )
        except StaffPayoutApiError as error:
            st.error(f"Apply 失敗 [{error.error.code}]：{error}")
        else:
            st.success("已建立配對；異常中心將顯示正式收款動作。")
            st.session_state.pop(preview_key, None)


def _render_staff_payout_difference(
    source_bindings: dict[str, object], action_label: str,
) -> None:
    row_id = _matching_row_id(source_bindings)
    if row_id is None:
        return
    st.markdown(f"#### {action_label}")
    key_prefix = f"staff_payout_difference_{row_id}"
    mode = st.radio("實際出款差異", ("underpayment", "overpayment"), format_func=lambda value: "少匯" if value == "underpayment" else "多匯", key=f"{key_prefix}_mode")
    raw_obligations = st.text_area("月嫂應付識別（每行一筆）", key=f"{key_prefix}_obligations")
    reason = st.text_area("處理原因", key=f"{key_prefix}_reason")
    obligations = tuple(line.strip() for line in raw_obligations.splitlines() if line.strip())
    if not obligations:
        st.info("請輸入已確認同一月嫂的應付識別。")
        return
    client = StaffPayoutApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers())
    signature = (mode, obligations, reason.strip())
    preview_key = f"{key_prefix}_preview"
    if st.button("Preview 差額處理", key=f"{preview_key}_button", disabled=not reason.strip()):
        try:
            preview = client.preview_payout_difference([row_id], obligations, mode, f"staff-payout-difference-preview-{uuid.uuid4().hex}")
        except StaffPayoutApiError as error:
            st.error(f"Preview 失敗 [{error.error.code}]：{error}")
        else:
            st.session_state[preview_key] = (signature, preview)
            st.rerun()
    stored = st.session_state.get(preview_key)
    if not isinstance(stored, tuple) or len(stored) != 2 or stored[0] != signature:
        st.info("請先成功 Preview；變更模式、應付項目或原因後必須重新 Preview。")
        return
    preview = stored[1]
    st.caption("Preview 已驗證出款列、月嫂帳戶與所選應付項目的金額差異。")
    if st.button("Apply 差額處理", key=f"{preview_key}_apply"):
        try:
            client.apply_payout_difference([row_id], obligations, mode, preview, reason=reason.strip(), idempotency_key=f"staff-payout-difference-{uuid.uuid4().hex}", correlation_id=f"staff-payout-difference-apply-{uuid.uuid4().hex}")
        except StaffPayoutApiError as error:
            st.error(f"Apply 失敗 [{error.error.code}]：{error}")
        else:
            st.success("已送出正式月嫂付款差額處理。")
            st.session_state.pop(preview_key, None)


def _matching_row_id(source_bindings: dict[str, object]) -> int | None:
    identity = source_bindings.get("finance_import_row_identity")
    raw = identity.removeprefix("finance-import-row:") if isinstance(identity, str) else ""
    if not raw.isdigit() or int(raw) <= 0:
        st.error("recovery_source_binding_incomplete：缺少可用的銀行流水識別。")
        return None
    return int(raw)


def _render_client_receipt_overage(source_bindings: dict[str, object], action_label: str) -> None:
    row_id = _matching_row_id(source_bindings)
    if row_id is None:
        return
    st.markdown(f"#### {action_label}")
    key = f"client_receipt_overage_{row_id}"
    case_no = st.text_input("案件編號", key=f"{key}_case")
    stage = st.selectbox("收款階段", ("deposit", "first", "second", "adjustment"), key=f"{key}_stage")
    obligations = tuple(item.strip() for item in st.text_area("應收義務識別（每行一筆）", key=f"{key}_obligations").splitlines() if item.strip())
    reason = st.text_area("處理原因", key=f"{key}_reason")
    if not case_no.strip() or not obligations:
        st.info("請輸入案件與應收義務。")
        return
    body = ClientReceiptPreviewBody(payment_stage=stage, finance_import_row_ids=[row_id], obligation_identities=list(obligations))
    client = ClientReceiptReconciliationApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers())
    signature = (case_no.strip(), body.model_dump_json(), reason.strip())
    preview_key = f"{key}_preview"
    if st.button("Preview 收款超額", key=f"{preview_key}_button", disabled=not reason.strip()):
        try:
            preview = client.preview_overage(case_no.strip(), body)
        except Exception as error:
            st.error(f"Preview 失敗：{error}")
        else:
            st.session_state[preview_key] = (signature, preview)
            st.rerun()
    stored = st.session_state.get(preview_key)
    if not isinstance(stored, tuple) or len(stored) != 2 or stored[0] != signature:
        st.info("請先成功 Preview；變更案件、義務、階段或原因後必須重新 Preview。")
        return
    preview = stored[1]
    apply = ClientReceiptApplyBody(**body.model_dump(), expected_account_version=preview.account_version, preview_fingerprint=preview.preview_fingerprint, reason=reason.strip())
    if st.button("Apply 收款超額", key=f"{preview_key}_apply"):
        try:
            client.apply_overage(case_no.strip(), apply, f"client-receipt-overage-{uuid.uuid4().hex}")
        except Exception as error:
            st.error(f"Apply 失敗：{error}")
        else:
            st.success("已建立客戶超收退款應付。")
            st.session_state.pop(preview_key, None)


def _government_disposition_preview_body(
    identity: str,
    disposition: str,
    evidence: str,
    key_prefix: str,
) -> GovernmentSubsidyOverpaymentDispositionPreviewBody | None:
    if disposition == "return":
        due_date = st.date_input("退款到期日", key=f"{key_prefix}_due_date")
        try:
            return GovernmentSubsidyOverpaymentDispositionPreviewBody(
                overpayment_identity=identity,
                disposition="return",
                due_date=due_date.isoformat(),
                evidence_reference=evidence,
            )
        except ValueError as error:
            st.info(f"請補齊退還資料：{error}")
            return None
    targets = _government_offset_targets(key_prefix)
    if not targets:
        st.info("至少輸入一筆已核准、同付款方的 claim item 與抵扣金額。")
        return None
    try:
        return GovernmentSubsidyOverpaymentDispositionPreviewBody(
            overpayment_identity=identity,
            disposition="offset",
            targets=targets,
            evidence_reference=evidence,
        )
    except ValueError as error:
        st.info(f"請補齊抵扣資料：{error}")
        return None


def _government_offset_targets(
    key_prefix: str,
) -> list[GovernmentSubsidyOverpaymentOffsetIntentView]:
    targets: list[GovernmentSubsidyOverpaymentOffsetIntentView] = []
    st.caption("可同時輸入最多三筆抵扣 target；不足可先完成一筆，再對剩餘溢撥重新處置。")
    for index in range(3):
        columns = st.columns(2)
        item_id = columns[0].number_input(
            f"Claim item {index + 1}",
            min_value=0,
            step=1,
            key=f"{key_prefix}_target_item_{index}",
        )
        amount = columns[1].number_input(
            f"抵扣金額 {index + 1}",
            min_value=0,
            step=1,
            key=f"{key_prefix}_target_amount_{index}",
        )
        if item_id == 0 and amount == 0:
            continue
        if item_id == 0 or amount == 0:
            st.info(f"第 {index + 1} 筆 target 必須同時填 claim item 與金額。")
            return []
        targets.append(
            GovernmentSubsidyOverpaymentOffsetIntentView(
                claim_item_id=int(item_id),
                amount_ntd=int(amount),
            )
        )
    return targets


def _render_per_row_action_table(
    items: tuple[AnomalySummaryView, ...],
    *,
    button_label: str,
    key_prefix: str,
) -> None:
    """Per-row single-case action button, instead of a batch/queue-all button.

    需求提出者確認過：訂單配對／補發送資訊要逐筆單獨處理，一次把整批案件塞進
    同一個佇列跟實際使用狀況不符，所以這裡每一列各自導向只帶自己那一筆 case_no。
    """
    if not items:
        st.info("目前沒有符合條件的異常。")
        return
    header_cols = st.columns([1.6, 1.4, 3.6])
    header_cols[0].markdown(f"**{button_label}**")
    header_cols[1].markdown("**案件編號**")
    header_cols[2].markdown("**警示類型**")
    for item in items:
        with st.container(border=True):
            row_cols = st.columns([1.6, 1.4, 3.6])
            case_no = _case_no(item)
            if row_cols[0].button(button_label, key=f"{key_prefix}_row_{item.fingerprint[:8]}"):
                _navigate_to_matching([case_no])
            row_cols[1].write(case_no)
            row_cols[2].write(_alert_code_label(item.definition_code))


def _render_table_only(
    heading: str,
    caption: str,
    items: tuple[AnomalySummaryView, ...],
) -> None:
    """純表格：沒有可用的深連結頁面或動作，只需要人工檢視內容。"""
    if heading:
        st.subheader(heading)
    if caption:
        st.caption(caption)
    if not items:
        st.info("目前沒有符合條件的異常。")
        return
    _render_summary_table(items)


def _schedule_staff_calendar_target(item: AnomalySummaryView) -> tuple[int, str, str] | None:
    """回傳 (staff_id, 定位日期, 說明文字)；資料不齊全就回 None，改顯示純文字列。"""
    navigation = item.staff_calendar_navigation
    if navigation is None:
        return None
    snapshot = _snapshot(item)
    code = item.definition_code
    if code == "SCHEDULE-001":
        holiday_date = snapshot.get("holiday_date")
        holiday_name = snapshot.get("holiday_name")
        if not holiday_date:
            return None
        note = (
            f"案件 {snapshot.get('case_no')} 的服務期間內有國定假日「{holiday_name}」"
            f"（{holiday_date}），行政尚未決策該月嫂當天是否放假。"
        )
        return navigation.staff_id, navigation.target_date, note
    if code == "SCHEDULE-005":
        work_date = snapshot.get("work_date")
        holiday_name = snapshot.get("holiday_name")
        if not work_date:
            return None
        note = f"月嫂登記國定假日必休，但 {work_date}（{holiday_name}）排班仍是上班日。"
        return navigation.staff_id, navigation.target_date, note
    if code == "SCHEDULE-003":
        segment_a = snapshot.get("assignment_a") or {}
        segment_b = snapshot.get("assignment_b") or {}
        start_a = segment_a.get("start")
        if not start_a:
            return None
        note = (
            f"服務人員檔期重疊：案件 {segment_a.get('case_no')}"
            f"（{segment_a.get('start')}~{segment_a.get('end')}）與案件 "
            f"{segment_b.get('case_no')}（{segment_b.get('start')}~{segment_b.get('end')}）"
            "由同一月嫂承接且日期重疊。"
        )
        return navigation.staff_id, navigation.target_date, note
    return None


def _schedule_assignment_repair_case(item: AnomalySummaryView) -> str | None:
    if item.definition_code != "SCHEDULE-006":
        return None
    case_no = _case_no(item).strip()
    return case_no or None


def _render_staff_table(items: tuple[AnomalySummaryView, ...]) -> None:
    """服務人員分頁：SCHEDULE-001/003/005 有明確的月嫂＋日期，逐列給「前往處理」
    直接定位到「多月嫂排班→服務人員月曆」該月嫂當月行事曆（不受案件狀態影響）；
    SCHEDULE-006 導向既有的「案件人力配置」Preview/Apply；其餘沒有明確可深連結
    目的地的警示維持純表格列。"""
    if not items:
        st.info("目前沒有符合條件的異常。")
        return
    header_cols = st.columns([1.6, 1.4, 1.4, 3.6])
    header_cols[0].markdown("**前往處理**")
    header_cols[1].markdown("**案件/識別**")
    header_cols[2].markdown("**服務月嫂**")
    header_cols[3].markdown("**警示類型**")
    for item in items:
        with st.container(border=True):
            row_cols = st.columns([1.6, 1.4, 1.4, 3.6])
            target = _schedule_staff_calendar_target(item)
            if target is not None:
                staff_id, date_text, note = target
                if row_cols[0].button("🎯 前往處理", key=f"staff_row_{item.fingerprint[:8]}"):
                    _navigate_to_staff_calendar(staff_id, date_text, note)
            elif repair_case_no := _schedule_assignment_repair_case(item):
                if row_cols[0].button(
                    "🎯 前往正式人力配置",
                    key=f"staff_assignment_{item.fingerprint[:8]}",
                ):
                    _navigate_to_assignment_repair(repair_case_no)
            else:
                row_cols[0].caption("尚無對應頁面")
            row_cols[1].write(_case_no(item))
            row_cols[2].write(_snapshot(item).get("staff_name") or "—")
            row_cols[3].write(_alert_code_label(item.definition_code))


def _render_process_tab(items: tuple[AnomalySummaryView, ...]) -> None:
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
        st.caption("需要人工多步驟處理，請逐筆點「🎯 前往配對」個別處理。")
        _render_per_row_action_table(order_items, button_label="🎯 前往配對", key_prefix="order")
    with sub_missing:
        _render_table_only(
            "",
            "純資料有無判斷，補齊後下一輪背景掃描會自動解除，不需要手動認領/解除。",
            missing_items,
        )
    with sub_send:
        st.caption("已有候選月嫂願意接案，但履歷尚未發送給客戶；請逐筆點「前往配對」在配對頁完成發送。")
        _render_per_row_action_table(
            send_items, button_label="📨 前往配對頁面發送履歷", key_prefix="send"
        )
    with sub_overdue:
        _render_table_only(
            "",
            "客戶訂金/期款、補助款應退還客戶已過到期日但尚未結清；系統不執行金流動作，"
            "需搭配銀行對帳/實際匯款處理後，下一輪背景掃描才會自動解除。",
            overdue_items,
        )


def show() -> None:
    st.title(title)
    st.caption("異常中心僅顯示去敏警示與導向業面；正式資料只能在 owning Domain 的 Preview／Apply 處理。")
    try:
        registry_client = _registry_client()
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
        _render_import_tab(items)

    with process_tab:
        _render_process_tab(items)

    with finance_tab:
        _render_table_only(
            "帳務異常",
            "僅供檢視與後續導向；帳務 recovery、核銷與沖正必須在帳務作業中心執行。",
            _filter(items, _FINANCE_CODES),
        )

    with staff_tab:
        st.subheader("服務人員")
        st.caption(
            "排班覆核（國定假日決策/中途更換/檔期重疊/休假偏好衝突）、"
            "月嫂應付款逾期/異常變更/銀行帳戶問題。"
        )
        _render_staff_table(_filter(items, _STAFF_CODES))

    with line_tab:
        _render_table_only(
            "Line",
            "客戶/服務人員尚未綁定 LINE、群組任務推播無回覆、同一帳號同時綁定兩種身分。",
            _filter(items, _LINE_CODES),
        )


def _render_import_tab(items: tuple[AnomalySummaryView, ...]) -> None:
    _render_table_only(
        "資料匯入異常",
        "HCM／BeClass／歷史訂單欄位驗證與待確認、身分衝突、銀行對帳匯入完整性。",
        _filter(items, _IMPORT_CODES),
    )
    _render_beclass_review_navigation(_beclass_review_items(items))
    _render_import_warning_tracking_workspace()


def _render_import_warning_tracking_workspace() -> None:
    st.divider()
    st.subheader("匯入警示外部確認追蹤")
    st.caption("只記錄聯絡與重新提交進度；不會修改來源資料，也不代表正式資料已修正。")
    try:
        client = _import_warning_tracking_client()
        tasks = client.query_tasks()
    except ImportWarningTrackingApiError as error:
        st.info(f"匯入警示追蹤尚無可用資料 [{error}]。")
        return
    if not tasks:
        st.info("目前沒有待追蹤的匯入警示。")
        return
    st.dataframe([
        {"來源": item.owning_lane, "警示": item.display_message, "欄位": item.field_path,
         "去敏主體": item.masked_subject, "狀態": item.tracking_status, "版本": item.tracking_version}
        for item in tasks
    ], hide_index=True, width="stretch")
    selected = st.selectbox("選擇欄位級警示", tasks, format_func=lambda item: f"{item.display_message}｜{item.masked_subject}", key="import_warning_tracking_task")
    _render_import_warning_navigation(selected)
    targets = {
        "open": ("awaiting_external_confirmation", "closed"),
        "awaiting_external_confirmation": ("response_recorded", "closed"),
        "response_recorded": ("reimport_requested", "closed"),
        "reimport_requested": ("closed",),
    }.get(selected.tracking_status, ())
    if not targets:
        st.info("此警示已是終態，不能由人工再次轉態。")
        return
    target = st.selectbox("下一狀態", targets, key="import_warning_tracking_target")
    reason = st.text_input("處理原因代碼", key="import_warning_tracking_reason")
    note = st.text_area("去敏備註（選填）", key="import_warning_tracking_note")
    evidence = st.text_input("證據參考（選填）", key="import_warning_tracking_evidence")
    body = WarningTransitionBody(expected_version=selected.tracking_version, target_status=target, reason_code=reason or "pending_reason", note=note or None, evidence_reference=evidence or None)
    signature = body.model_dump_json()
    preview_key = f"import_warning_preview_{selected.occurrence_identity}"
    if st.button("Preview 狀態轉態", disabled=not reason.strip(), key="import_warning_tracking_preview"):
        try:
            st.session_state[preview_key] = (signature, client.preview(selected.occurrence_identity, body, idempotency_key=f"import-warning-preview-{uuid.uuid4().hex}", correlation_id=f"import-warning-preview-{uuid.uuid4().hex}"))
        except ImportWarningTrackingApiError as error:
            st.error(f"Preview 失敗 [{error}]")
        else:
            st.rerun()
    stored = st.session_state.get(preview_key)
    if isinstance(stored, tuple) and len(stored) == 2 and stored[0] == signature:
        st.success(f"Preview 完成：將更新為 {stored[1].resulting_status}。")
        if st.button("Apply 狀態轉態", key="import_warning_tracking_apply"):
            try:
                client.apply(selected.occurrence_identity, body, idempotency_key=f"import-warning-apply-{uuid.uuid4().hex}", correlation_id=f"import-warning-apply-{uuid.uuid4().hex}")
            except ImportWarningTrackingApiError as error:
                st.error(f"Apply 失敗 [{error}]")
            else:
                st.session_state.pop(preview_key, None)
                st.success("已記錄外部確認追蹤狀態；來源資料未被修改。")
                st.rerun()


def _render_import_warning_navigation(task) -> None:
    """Keep navigation as a thin local mapping; source mutation remains in the owner screen."""
    page_title = {
        "hcm_import_center": "📥 資料匯入中心",
        "historical_order_import_center": "📥 資料匯入中心",
        "client_beclass_import_center": "📥 資料匯入中心",
        "staff_beclass_import_center": "📥 資料匯入中心",
        "finance_import_recovery_center": "💰 帳務作業中心",
    }.get(task.navigation_action)
    if page_title is None:
        st.caption("目前沒有可安全導向的業面；請依警示內容聯絡或等待後續處理。")
        return
    label = {
        "hcm_import_center": "前往 HCM 匯入中心",
        "historical_order_import_center": "前往歷史訂單匯入中心",
        "client_beclass_import_center": "前往 Client BeClass 匯入中心",
        "staff_beclass_import_center": "前往 Staff BeClass 匯入中心",
        "finance_import_recovery_center": "前往帳務作業中心",
    }[task.navigation_action]
    if st.button(label, key=f"import_warning_navigate_{task.occurrence_identity}"):
        from ui.nav_helper import navigate_to

        navigate_to(page_title)


def _beclass_review_items(items: tuple[AnomalySummaryView, ...]) -> tuple[AnomalySummaryView, ...]:
    return _filter(items, {"IMPORT-001", "IMPORT-003"})


def _render_beclass_review_navigation(items: tuple[AnomalySummaryView, ...]) -> None:
    """Show BeClass review warnings here, but keep all source work in the owning import screen."""
    if not items:
        return
    st.caption("BeClass 來源需重新提交或由 owning 匯入流程處理；異常中心不接收修正欄位。")
    if st.button("前往資料匯入中心", key="beclass_review_navigate"):
        from ui.nav_helper import navigate_to

        navigate_to("📥 資料匯入中心")


if __name__ == "__main__":
    show()
