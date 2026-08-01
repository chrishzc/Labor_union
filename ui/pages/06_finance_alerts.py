"""Typed administration UI for finance and current-state system alerts."""

from __future__ import annotations

from decimal import Decimal

import streamlit as st

from api.schemas.finance_alert_center import (
    AlertFamily,
    AlertQuery,
    AlertStatus,
    ClaimAlertCommand,
    FinanceAlertDetailViewModel,
    ImportReviewBatchViewModel,
    ResolveAlertCommand,
    ScanAlertsCommand,
    SystemAlertDetailViewModel,
)
from ui.api_clients.finance_alert_center_client import (
    FinanceAlertCenterApiClient,
    FinanceAlertCenterApiError,
)
from ui.pages.shared import build_admin_headers, resolve_api_base_url


title = "異常警示中心"


def _client() -> FinanceAlertCenterApiClient:
    return FinanceAlertCenterApiClient(
        base_url=resolve_api_base_url(),
        headers=build_admin_headers(),
        timeout=20,
    )


def _operator_default() -> str:
    profile = st.session_state.get("line_admin_profile") or {}
    if not isinstance(profile, dict):
        return ""
    return str(profile.get("username") or "").strip()


def _show_error(error: Exception) -> None:
    if isinstance(error, FinanceAlertCenterApiError):
        retry = "；可稍後重試" if error.error.retryable else ""
        st.error(f"{error.error.code.value}: {error.error.message}{retry}")
        if error.error.field_errors:
            for item in error.error.field_errors:
                st.caption(f"{item.field}: {item.message}")
        return
    st.error(str(error))


def _money(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


def _render_summary_table(items) -> None:
    st.dataframe(
        [
            {
                "ID": item.id,
                "警示代碼": item.alert_code,
                "名稱": item.label,
                "來源": item.source_domain,
                "來源識別": item.source_reference,
                "狀態": item.status.value,
                "原因": item.reason,
                "更新時間": item.updated_at or item.created_at,
            }
            for item in items
        ],
        hide_index=True,
        width="stretch",
    )


def _render_display_fields(fields) -> None:
    if not fields:
        st.caption("沒有可公開的補充欄位。")
        return
    st.dataframe(
        [{"欄位": field.name, "內容": field.value} for field in fields],
        hide_index=True,
        width="stretch",
    )


def _render_import_review(detail: ImportReviewBatchViewModel) -> None:
    st.warning(
        "IMPORT-006 代表銀行流水仍未分類成業務事件；"
        "這不等於已入帳，也不等於已完成核銷。"
    )
    left, middle, right = st.columns(3)
    left.metric("來源列 occurrence", detail.occurrence_count)
    middle.metric("去重流水 distinct", detail.distinct_count)
    right.metric("仍待人工分類", detail.remaining_count)
    st.caption(
        f"批次 #{detail.batch_id}｜格式 {detail.format_id or '未提供'}｜"
        f"批次狀態 {detail.batch_status or '未提供'}｜"
        f"來源批次列數 {detail.row_count if detail.row_count is not None else '未提供'}"
    )
    count_rows = [
        {"維度": "方向", "分類": item.key, "筆數": item.count}
        for item in detail.direction_counts
    ] + [
        {"維度": "原因", "分類": item.key, "筆數": item.count}
        for item in detail.reason_counts
    ]
    if count_rows:
        st.dataframe(count_rows, hide_index=True, width="stretch")
    if detail.sample_row_ids:
        st.caption(
            "抽樣 canonical row IDs（最多 20 筆）："
            + "、".join(str(item) for item in detail.sample_row_ids)
        )
    if detail.last_reprocess is not None:
        last = detail.last_reprocess
        st.markdown("#### 最近一次人工 CLI 重處理")
        st.write(
            {
                "run_id": last.run_id,
                "status": last.status,
                "selected": last.selected_count,
                "changed": last.changed_count,
                "dispatch": last.dispatch_count,
                "reconciled": last.reconciled_count,
                "pending": last.pending_count,
                "completed_at": last.completed_at,
            }
        )
    st.info(
        "本頁不提供姓名自動匹配、刪除 staging、force reconcile 或 reprocess apply；"
        "歷史重處理只由人工 CLI 執行。"
    )


def _render_detail(detail) -> None:
    st.markdown(f"### {detail.alert.label}")
    st.caption(
        f"{detail.alert.family.value}｜{detail.alert.source_domain}｜"
        f"{detail.alert.source_reference}｜{detail.alert.status.value}"
    )
    st.write(detail.alert.reason)
    if isinstance(detail, ImportReviewBatchViewModel):
        _render_import_review(detail)
    elif isinstance(detail, FinanceAlertDetailViewModel):
        amount_left, amount_middle, amount_right = st.columns(3)
        amount_left.metric("預期金額", _money(detail.expected_amount))
        amount_middle.metric("實際金額", _money(detail.actual_amount))
        amount_right.metric("差額", _money(detail.difference_amount))
        st.markdown("#### 候選快照（僅供人工判讀）")
        _render_display_fields(detail.candidate)
        st.caption("系統不會預選第一筆、同額或姓名相近候選，也不會從本頁建立正式交易。")
        if detail.events:
            st.markdown("#### 不可變事件歷程")
            st.dataframe(
                [
                    {
                        "事件": event.event_type,
                        "操作者": event.actor,
                        "原因": event.reason,
                        "發生時間": event.occurred_at,
                    }
                    for event in detail.events
                ],
                hide_index=True,
                width="stretch",
            )
    elif isinstance(detail, SystemAlertDetailViewModel):
        st.markdown("#### 已物化警示摘要")
        _render_display_fields(detail.details)


def _render_actions(
    *,
    client: FinanceAlertCenterApiClient,
    family: AlertFamily,
    detail,
    key_prefix: str,
) -> None:
    st.markdown("#### 人工處理")
    operator = st.text_input(
        "操作人員",
        value=_operator_default(),
        key=f"{key_prefix}_operator",
    )
    claim_col, resolve_col = st.columns(2)
    with claim_col:
        if st.button(
            "認領警示",
            key=f"{key_prefix}_claim",
            disabled=not operator.strip(),
        ):
            try:
                client.claim_alert(
                    ClaimAlertCommand(
                        alert_id=detail.alert.id,
                        operator=operator,
                    ),
                    family=family,
                )
            except (FinanceAlertCenterApiError, ValueError) as error:
                _show_error(error)
            else:
                st.success("警示已認領。")
                st.rerun()
    with resolve_col:
        reason = st.text_area(
            "解除原因",
            key=f"{key_prefix}_resolve_reason",
        )
        acknowledged = st.checkbox(
            "我了解解除警示不等於完成核銷或建立正式帳務",
            key=f"{key_prefix}_resolve_ack",
        )
        if st.button(
            "解除警示",
            key=f"{key_prefix}_resolve",
            disabled=(
                not operator.strip()
                or not reason.strip()
                or not acknowledged
            ),
        ):
            try:
                client.resolve_alert(
                    ResolveAlertCommand(
                        alert_id=detail.alert.id,
                        operator=operator,
                        reason=reason,
                    ),
                    family=family,
                )
            except (FinanceAlertCenterApiError, ValueError) as error:
                _show_error(error)
            else:
                st.success("警示已解除；正式核銷狀態未因此改變。")
                st.rerun()


def _render_alert_family(
    *,
    client: FinanceAlertCenterApiClient,
    family: AlertFamily,
    key_prefix: str,
    fixed_alert_code: str | None = None,
) -> None:
    filter_columns = st.columns(4)
    status_label = filter_columns[0].selectbox(
        "狀態",
        ["全部", "open", "claimed", "resolved"],
        key=f"{key_prefix}_status",
    )
    alert_code = filter_columns[1].text_input(
        "警示代碼",
        value=fixed_alert_code or "",
        disabled=fixed_alert_code is not None,
        key=f"{key_prefix}_code",
    )
    source_domain = filter_columns[2].text_input(
        "來源領域",
        key=f"{key_prefix}_domain",
    )
    page = filter_columns[3].number_input(
        "頁次",
        min_value=1,
        value=1,
        step=1,
        key=f"{key_prefix}_page",
    )
    limit = 50
    query = AlertQuery(
        family=family,
        status=None if status_label == "全部" else AlertStatus(status_label),
        alert_code=alert_code.strip() or None,
        source_domain=source_domain.strip() or None,
        limit=limit,
        offset=(int(page) - 1) * limit,
    )
    try:
        result = client.list_alerts(query)
    except (FinanceAlertCenterApiError, ValueError) as error:
        _show_error(error)
        return
    if not result.items:
        st.info("目前沒有符合條件的警示。")
        return
    _render_summary_table(result.items)
    selected_id = st.selectbox(
        "選擇警示",
        [item.id for item in result.items],
        format_func=lambda value: next(
            (
                f"#{item.id}｜{item.label}｜{item.source_reference}"
                for item in result.items
                if item.id == value
            ),
            str(value),
        ),
        key=f"{key_prefix}_selected",
    )
    try:
        detail = client.get_alert(family=family, alert_id=selected_id)
    except (FinanceAlertCenterApiError, ValueError) as error:
        _show_error(error)
        return
    _render_detail(detail)
    _render_actions(
        client=client,
        family=family,
        detail=detail,
        key_prefix=f"{key_prefix}_{selected_id}",
    )


def _render_import_tab(client: FinanceAlertCenterApiClient) -> None:
    st.subheader("資料匯入異常")
    st.caption(
        "本頁只讀取已物化警示，不會在每次 render 時掃描原始匯入流水。"
    )
    if st.button("明確重新掃描匯入異常", key="finance_alert_import_scan"):
        try:
            summary = client.scan_alerts(ScanAlertsCommand())
        except (FinanceAlertCenterApiError, ValueError) as error:
            _show_error(error)
        else:
            import_item = next(
                (item for item in summary.items if item.alert_code == "IMPORT-006"),
                None,
            )
            if import_item is None:
                st.error("掃描結果缺少 IMPORT-006，請勿將本次掃描視為完成。")
            else:
                st.success(
                    "IMPORT-006 掃描完成："
                    f"新增 {import_item.created}、更新 {import_item.updated}、"
                    f"重開 {import_item.reopened}、解除 {import_item.resolved}。"
                )
                st.rerun()
    _render_alert_family(
        client=client,
        family=AlertFamily.SYSTEM,
        key_prefix="finance_alert_import",
        fixed_alert_code="IMPORT-006",
    )


def show() -> None:
    st.title(title)
    st.caption(
        "人工檢視、認領與解除警示；本頁不建立、修改或強制對平正式帳務。"
    )
    try:
        client = _client()
    except (RuntimeError, ValueError) as error:
        _show_error(error)
        return
    import_tab, process_tab, finance_tab = st.tabs(
        ["資料匯入異常", "流程與系統警示", "帳務異常"]
    )
    with import_tab:
        _render_import_tab(client)
    with process_tab:
        st.subheader("流程與系統警示")
        _render_alert_family(
            client=client,
            family=AlertFamily.SYSTEM,
            key_prefix="finance_alert_system",
        )
    with finance_tab:
        st.subheader("帳務異常")
        st.caption(
            "CLIENT、RETURN、SUBSIDY、STAFF、COMMON 的業務分類下游異常；"
            "與尚未分類的 IMPORT-006 分開顯示。"
        )
        _render_alert_family(
            client=client,
            family=AlertFamily.FINANCE,
            key_prefix="finance_alert_finance",
        )


if __name__ == "__main__":
    show()
