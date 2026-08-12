"""Thin Streamlit display for canonical Finance Import commands."""

from __future__ import annotations

import json
from uuid import uuid4

import streamlit as st

from api.schemas.finance_import import (
    FinanceImportBatchPreviewView,
    FinanceImportCorrectionPreviewView,
    FinanceImportHistoricalReprocessPlanView,
)
from ui.api_clients.finance_import_api_client import (
    FinanceImportApiClient,
    FinanceImportApiError,
)
from ui import nav_helper


_BATCH_APPLY_STATE_KEY = "finance_import_batch_apply_state"
_CORRECTION_APPLY_STATE_KEY = "finance_import_correction_apply_state"
_HISTORICAL_REPROCESS_APPLY_STATE_KEY = "historical_reprocess_apply_state"
_JOB_STATUS_POLL_INTERVAL_SECONDS = 5


def render_finance_import_panel(client: FinanceImportApiClient) -> None:
    st.subheader("銀行流水匯入")
    st.caption("上傳正常銀行資料並執行批次 Preview／Apply；待人工處理項目請至異常警示中心。")
    _render_pending_review_summary(client)
    _render_ingestion(client)
    _render_batch_preview_and_apply(client)


def _render_pending_review_summary(client: FinanceImportApiClient) -> None:
    with st.expander("待人工處理的銀行列", expanded=True):
        batches = _query_batches(client)
        if not batches:
            st.info("目前沒有已建立的銀行匯入批次。")
            return
        batch_identity = _select_review_batch(batches)
        if batch_identity is None:
            st.info("目前沒有可讀取的正式銀行匯入批次。")
            return
        _render_review_rows(client, batch_identity)


def _query_batches(client: FinanceImportApiClient):
    try:
        return tuple(client.list_batches())
    except FinanceImportApiError as error:
        _show_api_error(error)
        return ()


def _select_review_batch(batches) -> str | None:
    identities = tuple(
        batch.batch_identity
        for batch in batches
        if batch.batch_identity is not None
    )
    if not identities:
        return None
    return st.selectbox("已建立批次", identities, key="finance_import_review_batch")


def _render_review_rows(client: FinanceImportApiClient, batch_identity: str) -> None:
    try:
        rows = client.list_review_rows(batch_identity).items
    except FinanceImportApiError as error:
        _show_api_error(error)
        return
    if not rows:
        st.success("此批次沒有待人工確認的銀行列。")
        return
    st.dataframe([row.model_dump() for row in rows], hide_index=True)
    st.warning(f"此批次有 {len(rows)} 筆需人工處理；請在異常警示中心依異常類型處置。")
    if st.button("前往帳務異常中心", key="finance_import_go_to_alerts"):
        nav_helper.navigate_to("異常警示中心")


def _render_ingestion(client: FinanceImportApiClient) -> None:
    with st.expander("1. 匯入銀行 Excel", expanded=False):
        workbook = st.file_uploader("銀行 Excel", type=["xlsx", "xls"])
        if st.button("上傳並建立待確認批次", key="finance_import_ingest"):
            if workbook is None:
                st.error("請先選擇銀行 Excel 檔案。")
                return
            try:
                with st.spinner("正在上傳並建立待確認批次…"):
                    receipt = client.ingest_workbook(
                        workbook.name,
                        workbook.getvalue(),
                        idempotency_key=_new_key("finance-import-ingest"),
                        correlation_id=_new_key("finance-import-correlation"),
                    )
            except FinanceImportApiError as error:
                _show_api_error(error)
                return
            st.success(f"已建立批次：{receipt.batch_identity}")
            st.json(receipt.model_dump())


def _render_batch_preview_and_apply(client: FinanceImportApiClient) -> None:
    with st.expander("2. 正常批次 Preview／Apply", expanded=True):
        batch_identity = st.text_input("批次識別碼", key="finance_import_batch_identity")
        if st.button("產生批次 Preview", key="finance_import_preview"):
            _preview_batch(client, batch_identity)
        preview = _stored_preview(
            "finance_import_batch_preview",
            FinanceImportBatchPreviewView,
        )
        if preview is None:
            return
        st.json(preview.model_dump())
        reason = st.text_input("正式入帳原因", key="finance_import_apply_reason")
        if st.button("依 Preview 正式入帳", key="finance_import_apply"):
            _apply_batch(client, preview, reason)
        _render_batch_apply_status(client)


def _preview_batch(client: FinanceImportApiClient, batch_identity: str) -> None:
    try:
        with st.spinner("正在產生批次 Preview…"):
            st.session_state["finance_import_batch_preview"] = client.preview_batch(
                batch_identity,
                _new_key("finance-import-preview"),
            )
        st.session_state.pop(_BATCH_APPLY_STATE_KEY, None)
    except (FinanceImportApiError, ValueError) as error:
        _show_api_error(error)


def _apply_batch(client: FinanceImportApiClient, preview, reason: str) -> None:
    state = st.session_state
    job, error = _submit_batch_apply_request(client, preview, reason, state)
    if error is not None:
        _show_batch_apply_error(error)
        return
    st.info(f"正式入帳工作已受理，等待完成確認：{job.job_id}")


def _submit_batch_apply_request(client, preview, reason: str, state):
    if not isinstance(state.get(_BATCH_APPLY_STATE_KEY), dict) and not reason.strip():
        return None, ValueError("正式入帳原因不可空白")
    command = _batch_apply_command(state, preview, reason)
    try:
        with st.spinner("正在受理正式入帳工作…"):
            job = client.apply_batch(
                preview,
                reason=command["reason"],
                idempotency_key=command["idempotency_key"],
                correlation_id=command["correlation_id"],
            )
    except (FinanceImportApiError, ValueError) as error:
        return None, error
    command["job_id"] = job.job_id
    state[_BATCH_APPLY_STATE_KEY] = command
    return job, None


def _batch_apply_command(state, preview, reason: str) -> dict:
    existing = state.get(_BATCH_APPLY_STATE_KEY)
    if isinstance(existing, dict) and not existing.get("terminal"):
        return existing
    command = {
        "batch_identity": preview.batch_identity,
        "preview_fingerprint": preview.preview_fingerprint,
        "reason": reason.strip(),
        "idempotency_key": _new_key("finance-import-apply"),
        "correlation_id": _new_key("finance-import-apply-correlation"),
        "job_id": None,
        "terminal": False,
    }
    state[_BATCH_APPLY_STATE_KEY] = command
    return command


@st.fragment(run_every=_JOB_STATUS_POLL_INTERVAL_SECONDS)
def _render_batch_apply_status(client: FinanceImportApiClient) -> None:
    command = st.session_state.get(_BATCH_APPLY_STATE_KEY)
    if not isinstance(command, dict) or command.get("terminal"):
        return
    job_id = command.get("job_id")
    if not job_id:
        st.warning("正式入帳回應未確認；請以相同命令重送，系統不會建立第二筆工作。")
        if st.button("重送相同正式入帳請求", key="finance_import_apply_retry"):
            _retry_batch_apply(client, command)
        return
    st.info(f"正式入帳處理中，工作編號：{job_id}")
    if st.button("查詢正式入帳狀態", key="finance_import_apply_status"):
        _refresh_batch_apply_status(client, command)


def _retry_batch_apply(client, command) -> None:
    preview = st.session_state.get("finance_import_batch_preview")
    if preview is None:
        st.error("找不到原始 Preview，無法安全重送。")
        return
    job, error = _submit_batch_apply_request(client, preview, command["reason"], st.session_state)
    if error is not None:
        _show_batch_apply_error(error)
        return
    st.info(f"正式入帳工作已受理，等待完成確認：{job.job_id}")


def _refresh_batch_apply_status(client, command) -> None:
    try:
        with st.spinner("正在查詢正式入帳工作狀態…"):
            status = client.get_job_status(command["job_id"])
    except FinanceImportApiError as error:
        _show_api_error(error)
        return
    if status.status in {"queued", "running"}:
        st.info(f"正式入帳仍在處理：{status.status}")
        return
    command["terminal"] = True
    if status.status == "succeeded":
        st.success("正式入帳已完成。")
        st.json(status.receipt_payload)
        return
    st.error(f"正式入帳未完成：{status.status}")
    st.json(status.error_payload)


def _show_batch_apply_error(error: Exception) -> None:
    if isinstance(error, FinanceImportApiError) and error.error.retryable:
        st.warning("正式入帳結果尚未確認；可重送相同命令。")
    _show_api_error(error)


def _render_historical_reprocess(client: FinanceImportApiClient) -> None:
    with st.expander("3. 歷史待確認資料重處理", expanded=False):
        st.caption("只處理 completed 批次中仍待確認的資料；政府補助沒有唯一標的時會停止。")
        batch_identity = st.text_input("歷史批次識別碼", key="historical_reprocess_batch_identity")
        owner_selection_json = st.text_area(
            "人工選案證據 JSON",
            help="只有無法由既有強證據判定 owner 的列才需要填寫；每列需有 row_identity、case_no、obligation_identity、reason、evidence_references。",
            key="historical_reprocess_owner_selections",
        )
        if st.button("產生歷史重處理 Preview", key="historical_reprocess_preview_btn"):
            _preview_historical_reprocess(client, batch_identity, owner_selection_json)
        preview = _stored_preview(
            "historical_reprocess_preview",
            FinanceImportHistoricalReprocessPlanView,
        )
        if preview is None:
            return
        st.json(preview.model_dump())
        reason = st.text_input("重處理原因", key="historical_reprocess_reason")
        _render_historical_reprocess_apply(client, preview, reason)


def _preview_historical_reprocess(client: FinanceImportApiClient, batch_identity: str, owner_selection_json: str) -> None:
    try:
        selections = _historical_owner_selection_input(owner_selection_json)
        st.session_state["historical_reprocess_preview"] = (
            client.preview_historical_reprocess(
                batch_identity,
                _new_key("historical-reprocess-preview"),
                selections,
            )
        )
        st.session_state.pop(_HISTORICAL_REPROCESS_APPLY_STATE_KEY, None)
    except (FinanceImportApiError, ValueError) as error:
        _show_api_error(error)


def _render_historical_reprocess_apply(client, preview, reason: str) -> None:
    command = st.session_state.get(_HISTORICAL_REPROCESS_APPLY_STATE_KEY)
    if not isinstance(command, dict):
        if st.button("依 Preview 執行歷史重處理", key="historical_reprocess_apply"):
            _apply_historical_reprocess(client, preview, reason)
        return
    _render_historical_reprocess_job_status(client, command)


def _apply_historical_reprocess(client: FinanceImportApiClient, preview, reason: str) -> None:
    if not reason.strip():
        st.error("重處理原因不可空白")
        return
    command = {
        "reason": reason.strip(),
        "idempotency_key": _new_key("historical-reprocess-apply"),
        "correlation_id": _new_key("historical-reprocess-apply-correlation"),
        "job_id": None,
        "terminal": False,
    }
    st.session_state[_HISTORICAL_REPROCESS_APPLY_STATE_KEY] = command
    _submit_historical_reprocess(client, preview, command)


def _submit_historical_reprocess(client, preview, command) -> None:
    try:
        with st.spinner("正在受理歷史重處理工作…"):
            job = client.apply_historical_reprocess(
                preview,
                reason=command["reason"],
                idempotency_key=command["idempotency_key"],
                correlation_id=command["correlation_id"],
            )
    except (FinanceImportApiError, ValueError) as error:
        _show_api_error(error)
        return
    command["job_id"] = job.job_id
    st.info(f"歷史重處理工作已受理：{job.job_id}")


@st.fragment(run_every=_JOB_STATUS_POLL_INTERVAL_SECONDS)
def _render_historical_reprocess_job_status(client, command) -> None:
    if command.get("terminal"):
        return
    job_id = command.get("job_id")
    if not job_id:
        st.warning("歷史重處理結果尚未確認；可安全重送同一命令。")
        if st.button("重送相同歷史重處理請求", key="historical_reprocess_retry"):
            preview = st.session_state.get("historical_reprocess_preview")
            if preview is not None:
                _submit_historical_reprocess(client, preview, command)
        return
    st.info(f"歷史重處理處理中，工作編號：{job_id}")
    if st.button("查詢歷史重處理狀態", key="historical_reprocess_status"):
        _refresh_historical_reprocess_status(client, command)


def _refresh_historical_reprocess_status(client, command) -> None:
    try:
        with st.spinner("正在查詢歷史重處理工作狀態…"):
            status = client.get_job_status(command["job_id"])
    except FinanceImportApiError as error:
        _show_api_error(error)
        return
    if status.status in {"queued", "running"}:
        st.info(f"歷史重處理仍在處理：{status.status}")
        return
    command["terminal"] = True
    if status.status == "succeeded":
        st.success("歷史重處理已完成。")
        st.json(status.receipt_payload)
        return
    st.error(f"歷史重處理未完成：{status.status}")
    st.json(status.error_payload)


def render_finance_import_correction_panel(
    client: FinanceImportApiClient,
    *,
    row_identity: str,
    action_label: str,
) -> None:
    """Render the only manual correction form from an anomaly-owned bank row."""

    _prepare_anomaly_correction(row_identity)
    st.markdown(f"#### {action_label}")
    st.caption("系統已帶入異常來源銀行列；請補足必要證據並先產生 Preview。")
    _render_manual_correction(client, expanded=True)


def _prepare_anomaly_correction(row_identity: str) -> None:
    current_row = st.session_state.get("finance_import_correction_row")
    if current_row == row_identity:
        return
    st.session_state["finance_import_correction_row"] = row_identity
    st.session_state["finance_import_correction_row_identity"] = row_identity
    st.session_state.pop("finance_import_correction_preview", None)
    st.session_state.pop(_CORRECTION_APPLY_STATE_KEY, None)


def _render_manual_correction(
    client: FinanceImportApiClient,
    *,
    expanded: bool,
) -> None:
    with st.expander("銀行列人工帳務修正", expanded=expanded):
        st.caption(
            "先固定不可變銀行列，再明示 obligation 與證據。退款、補助退還與退匯皆不可由案件頁直接配對。"
        )
        row_identity = st.text_input(
            "銀行列 identity",
            value=str(st.session_state.get("finance_import_correction_row") or ""),
            key="finance_import_correction_row_identity",
        )
        classification = st.selectbox(
            "帳務類型",
            (
                "client_receipt",
                "client_refund",
                "client_subsidy_return",
                "client_refund_return",
                "government_subsidy",
                "staff_payout",
            ),
            key="finance_import_correction_classification",
        )
        targets = st.text_area(
            "義務 identity（每行一筆）",
            key="finance_import_correction_targets",
        )
        allow_partial_refund_recovery = _partial_refund_recovery_input(classification)
        allow_refund_overage_recovery = _refund_overage_recovery_input(classification)
        allow_client_receipt_overage = _client_receipt_overage_input(classification)
        refund_ledger = _refund_ledger_input(classification)
        reason = st.text_input("修正原因", key="finance_import_correction_reason")
        evidence = st.text_area(
            "人工證據（每行一項）",
            key="finance_import_correction_evidence",
        )
        if st.button("產生人工修正 Preview", key="finance_import_correction_preview_button"):
            _preview_correction(
                client,
                row_identity,
                classification,
                targets,
                refund_ledger,
                reason,
                evidence,
                allow_partial_refund_recovery,
                allow_refund_overage_recovery,
                allow_client_receipt_overage,
            )
        _render_correction_apply_status(client)


def _refund_ledger_input(classification: str) -> str | None:
    if classification != "client_refund_return":
        return None
    return st.text_input(
        "原退款 ledger identity",
        key="finance_import_correction_refund_ledger",
    )


def _partial_refund_recovery_input(classification: str) -> bool:
    if classification != "client_refund":
        return False
    return st.checkbox(
        "此筆已實際匯少，改走部分退款補救流程",
        key="finance_import_correction_partial_refund_recovery",
    )


def _refund_overage_recovery_input(classification: str) -> bool:
    if classification != "client_refund":
        return False
    return st.checkbox(
        "此筆實際多匯，建立客戶追償應收",
        key="finance_import_correction_refund_overage_recovery",
    )


def _client_receipt_overage_input(classification: str) -> bool:
    if classification != "client_receipt":
        return False
    return st.checkbox(
        "此筆客戶實收超額，建立退款應付",
        key="finance_import_correction_client_receipt_overage",
    )


def _preview_correction(
    client,
    row_identity,
    classification,
    targets,
    ledger,
    reason,
    evidence,
    allow_partial_refund_recovery,
    allow_refund_overage_recovery,
    allow_client_receipt_overage,
) -> None:
    try:
        preview = client.preview_correction(
            row_identity,
            classification,
            _line_items(targets),
            reason,
            _line_items(evidence),
            _new_key("finance-import-correction-preview"),
            ledger,
            allow_partial_refund_recovery,
            allow_refund_overage_recovery,
            allow_client_receipt_overage,
        )
    except (FinanceImportApiError, ValueError) as error:
        _show_api_error(error)
        return
    st.session_state["finance_import_correction_preview"] = preview
    st.session_state.pop(_CORRECTION_APPLY_STATE_KEY, None)
    st.json(preview.model_dump())


@st.fragment(run_every=_JOB_STATUS_POLL_INTERVAL_SECONDS)
def _render_correction_apply_status(client) -> None:
    preview = _stored_preview(
        "finance_import_correction_preview",
        FinanceImportCorrectionPreviewView,
    )
    if preview is None:
        return
    state = st.session_state.get(_CORRECTION_APPLY_STATE_KEY)
    if not isinstance(state, dict):
        if st.button("依 Preview 套用人工修正", key="finance_import_correction_apply"):
            _apply_correction(client, preview)
        return
    _render_correction_job_status(client, state)


def _apply_correction(client, preview) -> None:
    command = {
        "idempotency_key": _new_key("finance-import-correction-apply"),
        "correlation_id": _new_key("finance-import-correction-apply-correlation"),
        "job_id": None,
        "terminal": False,
    }
    st.session_state[_CORRECTION_APPLY_STATE_KEY] = command
    _submit_correction(client, preview, command)


def _submit_correction(client, preview, command) -> None:
    try:
        with st.spinner("正在受理人工修正工作…"):
            job = client.apply_correction(
                preview,
                idempotency_key=command["idempotency_key"],
                correlation_id=command["correlation_id"],
            )
    except (FinanceImportApiError, ValueError) as error:
        _show_api_error(error)
        return
    command["job_id"] = job.job_id
    command["terminal"] = False
    st.info(f"人工修正工作已受理：{job.job_id}")


def _render_correction_job_status(client, command) -> None:
    if command.get("terminal"):
        _render_correction_terminal_result(command)
        st.caption("已保留 immutable Preview command；重送只會查回同一個工作。")
        if st.button("重送相同人工修正請求", key="finance_import_correction_replay"):
            preview = st.session_state.get("finance_import_correction_preview")
            if preview is not None:
                _submit_correction(client, preview, command)
        return
    if not command.get("job_id"):
        st.warning("人工修正結果尚未確認；可安全重送同一命令。")
        if st.button("重送相同人工修正請求", key="finance_import_correction_retry"):
            preview = st.session_state.get("finance_import_correction_preview")
            if preview is not None:
                _submit_correction(client, preview, command)
        return
    st.info(f"人工修正處理中，工作編號：{command['job_id']}")
    if st.button("查詢人工修正狀態", key="finance_import_correction_status"):
        _refresh_correction_status(client, command)


def _refresh_correction_status(client, command) -> None:
    try:
        with st.spinner("正在查詢人工修正工作狀態…"):
            status = client.get_job_status(command["job_id"])
    except FinanceImportApiError as error:
        _show_api_error(error)
        return
    if status.status in {"queued", "running"}:
        st.info(f"人工修正仍在處理：{status.status}")
        return
    command["terminal"] = True
    command["status"] = status.status
    command["receipt_payload"] = status.receipt_payload
    command["error_payload"] = status.error_payload
    if status.status == "succeeded":
        st.success("人工修正已完成。")
        st.json(status.receipt_payload)
        return
    st.error(f"人工修正未完成：{status.status}")
    st.json(status.error_payload)


def _render_correction_terminal_result(command) -> None:
    if command.get("status") == "succeeded":
        st.success("人工修正已完成。")
        st.json(command.get("receipt_payload"))
        return
    if command.get("status"):
        st.error(f"人工修正未完成：{command['status']}")
        st.json(command.get("error_payload"))


def _line_items(value: str) -> list[str]:
    return [item.strip() for item in value.splitlines() if item.strip()]


def _historical_owner_selection_input(value: str) -> list[dict]:
    if not value.strip():
        return []
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("人工選案證據必須是 JSON array") from error
    if not isinstance(decoded, list):
        raise ValueError("人工選案證據必須是 JSON array")
    if any(not isinstance(item, dict) for item in decoded):
        raise ValueError("人工選案證據每一項必須是 JSON object")
    return decoded


def _stored_preview(key: str, expected_type):
    preview = st.session_state.get(key)
    if preview is None or isinstance(preview, expected_type):
        return preview
    st.session_state.pop(key, None)
    st.info("已清除與目前版本不相容的舊預覽；請重新產生 Preview。")
    return None


def _new_key(prefix: str) -> str:
    return f"{prefix}:{uuid4()}"


def _show_api_error(error: Exception) -> None:
    if isinstance(error, FinanceImportApiError):
        st.error(f"{error.error.code}: {error.error.message}")
        return
    st.error(str(error))
