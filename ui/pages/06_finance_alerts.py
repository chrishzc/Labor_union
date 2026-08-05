"""Typed administration UI for finance and current-state system alerts."""

from __future__ import annotations

import streamlit as st

from ui.api_clients.anomaly_registry_api_client import AnomalyRegistryApiClient
from ui.api_clients.beclass_import_review_api_client import (
    BeClassImportReviewApiClient,
)
from ui.api_clients.finance_import_api_client import FinanceImportApiClient
from ui.api_clients.government_subsidy_api_client import (
    GovernmentSubsidyApiClient,
)
from ui.api_clients.anomaly_recovery_api_client import (
    AnomalyRecoveryApiClient,
)
from ui.pages.anomalies.registry_panel import render_anomaly_registry_panel
from ui.pages.anomalies.beclass_import_review_panel import (
    render_beclass_import_review_panel,
)
from ui.pages.finance_import.panel import render_finance_import_panel
from ui.pages.government_subsidy.ledger_panel import (
    render_government_subsidy_ledger_panel,
)
from ui.pages.government_subsidy.claim_panel import (
    render_government_subsidy_claim_panel,
)
from ui.pages.shared import build_admin_headers, resolve_api_base_url
from ui.nav_helper import navigate_to


title = "異常警示中心"


def _show_error(error: Exception) -> None:
    st.error(str(error))


def show() -> None:
    st.title(title)
    st.caption(
        "異常由根事實投影；正式匯入與人工修正一律先 Preview 再 Apply。"
    )
    try:
        base_url = resolve_api_base_url()
        headers = build_admin_headers()
    except (RuntimeError, ValueError) as error:
        _show_error(error)
        return
    _render_finance_operation_center(base_url, headers)


def _render_finance_operation_center(base_url, headers) -> None:
    _apply_pending_center_mode()
    center_mode = st.radio(
        "工作區",
        ("異常處理中心", "銀行流水匯入與修正", "BeClass 匯入修正"),
        horizontal=True,
        key="finance_operation_center_mode",
    )
    if center_mode == "異常處理中心":
        _render_canonical_anomaly_center(base_url, headers)
        return
    if center_mode == "銀行流水匯入與修正":
        _render_canonical_finance_import(base_url, headers)
        return
    _render_beclass_import_review(base_url, headers)


def _render_shared_anomaly_registry(base_url, headers) -> None:
    render_anomaly_registry_panel(
        AnomalyRegistryApiClient(
            base_url=base_url,
            headers=headers,
            timeout=20,
        ),
        AnomalyRecoveryApiClient(
            base_url=base_url,
            headers=headers,
            timeout=20,
        ),
        on_recovery_action_selected=_queue_recovery_navigation,
        on_domain_action_selected=_queue_domain_navigation,
    )


def _render_canonical_anomaly_center(base_url, headers) -> None:
    _render_shared_anomaly_registry(base_url, headers)


def _render_canonical_finance_import(base_url, headers) -> None:
    _render_shared_anomaly_registry(base_url, headers)
    render_finance_import_panel(
        FinanceImportApiClient(
            base_url=base_url,
            headers=headers,
            timeout=20,
        )
    )
    subsidy_client = GovernmentSubsidyApiClient(
        base_url=base_url,
        headers=headers,
        timeout=20,
    )
    render_government_subsidy_claim_panel(subsidy_client)
    render_government_subsidy_ledger_panel(subsidy_client)


def _render_beclass_import_review(base_url, headers) -> None:
    _render_shared_anomaly_registry(base_url, headers)
    render_beclass_import_review_panel(
        BeClassImportReviewApiClient(
            base_url=base_url,
            headers=headers,
            timeout=20,
        )
    )


def _apply_pending_center_mode() -> None:
    pending = st.session_state.pop("pending_finance_operation_center_mode", None)
    if pending in {
        "異常處理中心",
        "銀行流水匯入與修正",
        "BeClass 匯入修正",
    }:
        st.session_state["finance_operation_center_mode"] = pending


def _queue_domain_navigation(summary, action) -> None:
    handlers = {
        "case_import": _queue_case_import_navigation,
        "government_subsidy": _queue_government_subsidy_navigation,
        "staff_payables": _queue_staff_payables_navigation,
        "scheduling": _queue_scheduling_navigation,
    }
    handler = handlers.get(action.owning_domain)
    if handler is None:
        st.error("此修復入口尚未綁定可替換前端頁面。")
        return
    handler(summary, action)


def _queue_case_import_navigation(summary, _action) -> None:
    snapshot = _display_snapshot(summary)
    review_identity = snapshot.get("review_item_id")
    if not isinstance(review_identity, str) or not review_identity.strip():
        st.error("beclass_import_review_identity_missing：異常缺少修正資料識別。")
        return
    st.session_state["beclass_import_review_identity"] = review_identity
    _rerun_finance_workspace("BeClass 匯入修正")


def _queue_government_subsidy_navigation(summary, action) -> None:
    snapshot = _display_snapshot(summary)
    batch_id = _positive_integer(snapshot.get("batch_id"))
    bank_row_id = _identity_integer(
        snapshot.get("bank_fact_identity")
        or snapshot.get("reversal_bank_fact_identity"),
        "finance-import-row:",
    )
    _seed_government_subsidy_widgets(action, snapshot, batch_id, bank_row_id)
    _rerun_finance_workspace("銀行流水匯入與修正")


def _seed_government_subsidy_widgets(
    action,
    snapshot,
    batch_id,
    bank_row_id,
) -> None:
    if batch_id is not None:
        st.session_state["government_subsidy_batch_id"] = batch_id
        st.session_state["government_subsidy_pending_query_batch_id"] = batch_id
    if bank_row_id is not None:
        st.session_state["government_subsidy_bank_row"] = bank_row_id
    source_receipt_id = _positive_integer(snapshot.get("source_receipt_id"))
    if source_receipt_id is not None:
        st.session_state["government_subsidy_source_receipt"] = source_receipt_id
    st.session_state["government_subsidy_action"] = (
        "政府沖正"
        if action.command_name == "PreviewGovernmentSubsidyReversal"
        else "政府入款"
    )


def _queue_staff_payables_navigation(summary, _action) -> None:
    snapshot = _display_snapshot(summary)
    staff_id = _positive_integer(snapshot.get("staff_id"))
    if staff_id is None:
        staff_id = _identity_integer(summary.source_identity, "staff:")
    if staff_id is None:
        st.error("staff_payables_staff_identity_missing：異常缺少月嫂識別。")
        return
    st.session_state["orders_workspace"] = "🏦 月嫂付款核銷"
    st.session_state["load_staff_payout"] = True
    st.session_state["pending_staff_payout_staff_id"] = staff_id
    navigate_to("📦 訂單與帳務管理系統")


def _queue_scheduling_navigation(summary, _action) -> None:
    snapshot = _display_snapshot(summary)
    case_no = _canonical_text(snapshot.get("case_no"))
    if case_no is None:
        case_no = _identity_text(summary.source_identity, "case:")
    if case_no is None:
        st.error("scheduling_case_identity_missing：異常缺少案件識別。")
        return
    st.session_state["scheduling_workspace"] = "案件人力配置"
    st.session_state["pending_scheduling_case_no"] = case_no
    navigate_to("多月嫂排班")


def _rerun_finance_workspace(workspace: str) -> None:
    st.session_state["pending_finance_operation_center_mode"] = workspace
    st.rerun()


def _display_snapshot(summary) -> dict:
    return (
        summary.display_snapshot
        if isinstance(summary.display_snapshot, dict)
        else {}
    )


def _positive_integer(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return None


def _identity_integer(value, prefix: str) -> int | None:
    suffix = _identity_text(value, prefix)
    return _positive_integer(suffix)


def _identity_text(value, prefix: str) -> str | None:
    canonical = _canonical_text(value)
    if canonical is None or not canonical.startswith(prefix):
        return None
    return _canonical_text(canonical[len(prefix) :])


def _canonical_text(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _queue_recovery_navigation(action) -> None:
    if action.preview_endpoint != "/api/v1/finance-import/corrections/preview":
        st.error("此修復入口尚未綁定可替換前端頁面。")
        return
    st.session_state["finance_import_correction_row"] = (
        action.subject_identity
    )
    st.session_state["finance_import_recovery_context"] = {
        "action_code": action.action_code,
        "owning_domain": action.owning_domain,
        "command_name": action.command_name,
        "source_version": action.subject_version,
        "required_inputs": list(action.required_inputs),
    }
    st.session_state["pending_finance_import_mode"] = "待確認帳務修正"
    st.session_state["pending_finance_operation_center_mode"] = (
        "銀行流水匯入與修正"
    )
    st.rerun()


if __name__ == "__main__":
    show()
