"""Thin Streamlit display for canonical Finance Import commands."""

from __future__ import annotations

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


_BATCH_APPLY_STATE_KEY = "finance_import_batch_apply_state"
_CORRECTION_APPLY_STATE_KEY = "finance_import_correction_apply_state"


def render_finance_import_panel(client: FinanceImportApiClient) -> None:
    st.subheader("銀行流水匯入與帳務修正")
    st.caption("銀行資料先入庫，再由後端 Preview／Apply；UI 不計算或直接寫入帳務。")
    _render_ingestion(client)
    _render_batch_preview_and_apply(client)
    _render_historical_reprocess(client)
    _render_manual_correction(client)


def _render_ingestion(client: FinanceImportApiClient) -> None:
    with st.expander("1. 匯入銀行 Excel", expanded=False):
        workbook = st.file_uploader("銀行 Excel", type=["xlsx", "xls"])
        if st.button("上傳並建立待確認批次", key="finance_import_ingest"):
            if workbook is None:
                st.error("請先選擇銀行 Excel 檔案。")
                return
            try:
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
        if st.button("產生歷史重處理 Preview", key="historical_reprocess_preview_btn"):
            _preview_historical_reprocess(client, batch_identity)
        preview = _stored_preview(
            "historical_reprocess_preview",
            FinanceImportHistoricalReprocessPlanView,
        )
        if preview is None:
            return
        st.json(preview.model_dump())
        reason = st.text_input("重處理原因", key="historical_reprocess_reason")
        if st.button("依 Preview 執行歷史重處理", key="historical_reprocess_apply"):
            _apply_historical_reprocess(client, preview, reason)


def _preview_historical_reprocess(client: FinanceImportApiClient, batch_identity: str) -> None:
    try:
        st.session_state["historical_reprocess_preview"] = (
            client.preview_historical_reprocess(
                batch_identity,
                _new_key("historical-reprocess-preview"),
            )
        )
    except (FinanceImportApiError, ValueError) as error:
        _show_api_error(error)


def _apply_historical_reprocess(client: FinanceImportApiClient, preview, reason: str) -> None:
    try:
        receipt = client.apply_historical_reprocess(
            preview,
            reason=reason,
            idempotency_key=_new_key("historical-reprocess-apply"),
            correlation_id=_new_key("historical-reprocess-apply-correlation"),
        )
    except (FinanceImportApiError, ValueError) as error:
        _show_api_error(error)
        return
    st.success(f"歷史重處理完成，run #{receipt.reprocess_run_id}")
    st.json(receipt.model_dump())


def _render_manual_correction(client: FinanceImportApiClient) -> None:
    with st.expander("4. 待確認銀行列人工帳務修正", expanded=False):
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
        refund_ledger = _refund_ledger_input(classification)
        reason = st.text_input("修正原因", key="finance_import_correction_reason")
        evidence = st.text_area(
            "人工證據（每行一項）",
            key="finance_import_correction_evidence",
        )
        if st.button("產生人工修正 Preview", key="finance_import_correction_preview"):
            _preview_correction(
                client,
                row_identity,
                classification,
                targets,
                refund_ledger,
                reason,
                evidence,
            )
        _render_correction_apply_status(client)


def _refund_ledger_input(classification: str) -> str | None:
    if classification != "client_refund_return":
        return None
    return st.text_input(
        "原退款 ledger identity",
        key="finance_import_correction_refund_ledger",
    )


def _preview_correction(client, row_identity, classification, targets, ledger, reason, evidence) -> None:
    try:
        preview = client.preview_correction(
            row_identity,
            classification,
            _line_items(targets),
            reason,
            _line_items(evidence),
            _new_key("finance-import-correction-preview"),
            ledger,
        )
    except (FinanceImportApiError, ValueError) as error:
        _show_api_error(error)
        return
    st.session_state["finance_import_correction_preview"] = preview
    st.session_state.pop(_CORRECTION_APPLY_STATE_KEY, None)
    st.json(preview.model_dump())


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
        job = client.apply_correction(
            preview,
            idempotency_key=command["idempotency_key"],
            correlation_id=command["correlation_id"],
        )
    except (FinanceImportApiError, ValueError) as error:
        _show_api_error(error)
        return
    command["job_id"] = job.job_id
    st.info(f"人工修正工作已受理：{job.job_id}")


def _render_correction_job_status(client, command) -> None:
    if command.get("terminal"):
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
        status = client.get_job_status(command["job_id"])
    except FinanceImportApiError as error:
        _show_api_error(error)
        return
    if status.status in {"queued", "running"}:
        st.info(f"人工修正仍在處理：{status.status}")
        return
    command["terminal"] = True
    if status.status == "succeeded":
        st.success("人工修正已完成。")
        st.json(status.receipt_payload)
        return
    st.error(f"人工修正未完成：{status.status}")
    st.json(status.error_payload)


def _line_items(value: str) -> list[str]:
    return [item.strip() for item in value.splitlines() if item.strip()]


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
