"""
File: 09_data_import.py
Description: 顯示資料匯入中心並組合 HCM、訂單歷史與 Finance Import typed category cards。
"""

from hashlib import sha256
import os
from uuid import uuid4

import streamlit as st

from ui.api_clients.hcm_import_api_client import HcmImportApiClient, HcmImportApiError
from ui.api_clients.client_beclass_import_api_client import ClientBeClassImportApiClient, ClientBeClassImportApiError
from ui.api_clients.historical_order_adoption_api_client import HistoricalOrderAdoptionApiClient, HistoricalOrderAdoptionApiError
from ui.api_clients.finance_import_api_client import FinanceImportApiClient
from ui.api_clients.staff_historical_import_api_client import StaffHistoricalImportApiClient, StaffHistoricalImportApiError
from ui.pages.finance_import.panel import render_finance_import_panel
from ui.pages.shared import build_admin_headers, resolve_api_base_url


def show() -> None:
    st.title("📥 資料匯入中心")
    st.caption("每一類資料使用自己的欄位契約與 typed Preview／Apply；髒列不阻擋同檔合法列。")
    _render_hcm_card()
    _render_hcm_historical_card()
    _render_client_beclass_card()
    _render_staff_historical_card()
    _render_historical_order_card()
    _render_finance_card()


def _render_hcm_card() -> None:
    with st.expander("HCM 案件匯入", expanded=True):
        st.caption("上傳 .xlsx；先 Preview，再 Apply。有案件編號的欄位錯誤列仍建立正式案件，錯誤欄位保持空值。")
        workbook = st.file_uploader("選擇 HCM Excel", type=["xlsx"], key="hcm_workbook")
        if workbook is None:
            return
        content = workbook.getvalue()
        state = _hcm_import_state(content)
        key = _resolve_command_key(content)
        client = HcmImportApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers())
        if st.button("Preview HCM 案件", key="hcm_workbook_preview"):
            try:
                state["preview"] = client.preview_workbook(workbook.name, content)
            except HcmImportApiError as error:
                st.error(f"Preview 未完成：{error.code}")
            else:
                st.success("Preview 已完成，請確認結果後再 Apply。")
        preview = state.get("preview")
        if preview is None:
            return
        st.json(preview.model_dump())
        confirmation = st.text_input("輸入 APPLY 以確認 HCM 匯入", key="hcm_apply_confirmation")
        if not st.button("Apply HCM 案件", key="hcm_workbook_apply"):
            return
        if confirmation != "APPLY":
            st.error("請輸入 APPLY 後再執行。")
            return
        _apply_hcm_workbook(client, workbook.name, content, preview, key)


def _apply_hcm_workbook(client, filename, content, preview, command_key) -> None:
    try:
        receipt = client.apply_workbook(
            filename, content, preview_fingerprint=preview.preview_fingerprint,
            idempotency_key=command_key, correlation_id=f"hcm-ui:{uuid4()}",
        )
    except HcmImportApiError as error:
        st.error(f"Apply 未完成：{error.code}")
        return
    st.success("HCM 案件 Apply 已完成。")
    st.json(receipt.model_dump())
    _render_pending_source_notice(receipt.review_required_count)


def _render_hcm_historical_card() -> None:
    with st.expander("HCM 歷史過渡匯入", expanded=False):
        st.caption("依報名時間由舊到新覆寫 HCM 欄位；不改訂單狀態、帳務、薪資、排程或配對資料。")
        workbook = st.file_uploader("選擇 HCM 歷史 Excel", type=["xlsx"], key="hcm_historical_workbook")
        if workbook is None:
            return
        content = workbook.getvalue()
        state = _workbook_state("hcm_historical_import_state", content)
        client = HcmImportApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers())
        if st.button("Preview HCM 歷史資料", key="hcm_historical_preview"):
            try:
                state["preview"] = client.preview_historical_workbook(workbook.name, content)
            except HcmImportApiError as error:
                st.error(f"Preview 未完成：{error.code}")
        preview = state.get("preview")
        if preview is None:
            return
        st.json(preview.model_dump())
        confirmation = st.text_input("輸入 APPLY 以確認 HCM 歷史匯入", key="hcm_historical_confirmation")
        command_key = _resolve_development_key(
            f"hcm-historical:{sha256(content).hexdigest()}", "hcm_historical_command_key",
        )
        if st.button("Apply HCM 歷史資料", key="hcm_historical_apply"):
            _apply_hcm_historical_workbook(client, workbook.name, content, preview, confirmation, command_key)


def _apply_hcm_historical_workbook(client, filename, content, preview, confirmation, command_key) -> None:
    if confirmation != "APPLY":
        st.error("請輸入 APPLY 後再執行。")
        return
    try:
        receipt = client.apply_historical_workbook(
            filename, content, preview_fingerprint=preview.preview_fingerprint,
            idempotency_key=command_key, correlation_id=f"hcm-history-ui:{uuid4()}",
        )
    except HcmImportApiError as error:
        st.error(f"Apply 未完成：{error.code}")
        return
    st.success("HCM 歷史資料 Apply 已完成。")
    st.json(receipt.model_dump())
    _render_pending_source_notice(receipt.review_required_count)


def _command_key(content: bytes) -> str:
    return f"hcm-workbook:{sha256(content).hexdigest()}"


def _hcm_import_state(content: bytes) -> dict[str, object]:
    digest = sha256(content).hexdigest()
    state = st.session_state.setdefault("hcm_import_state", {})
    if state.get("digest") != digest:
        state.clear()
        state["digest"] = digest
    return state


def _resolve_command_key(content: bytes) -> str:
    default_key = _command_key(content)
    if not _is_development_environment():
        return default_key
    override = st.text_input("開發驗收 command key（留白使用檔案 digest）", key="hcm_upload_command_key")
    return override.strip() or default_key


def _is_development_environment() -> bool:
    app_environment = (os.getenv("APP_ENV", "development") or "development").strip().lower()
    return app_environment in {"development", "dev", "local", "test"}


def _render_client_beclass_card() -> None:
    with st.expander("Client BeClass 暫時匯入", expanded=False):
        st.caption("LIFF current writer 驗收前的暫時入口；先 Preview，再 Apply。")
        workbook = st.file_uploader("選擇 Client BeClass Excel", type=["xlsx"], key="client_beclass_workbook")
        if workbook is None:
            return
        content = workbook.getvalue()
        state = _workbook_state("client_beclass_import_state", content)
        client = ClientBeClassImportApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers())
        if st.button("Preview Client BeClass", key="client_beclass_preview"):
            try:
                state["preview"] = client.preview_workbook(workbook.name, content)
            except ClientBeClassImportApiError as error:
                st.error(f"Preview 未完成：{error.code}")
        preview = state.get("preview")
        if preview is None:
            return
        st.json(preview.model_dump())
        confirmation = st.text_input("輸入 APPLY 以確認 Client BeClass 匯入", key="client_beclass_confirmation")
        command_key = _resolve_development_key(
            f"client-beclass:{sha256(content).hexdigest()}",
            "client_beclass_command_key",
        )
        if st.button("Apply Client BeClass", key="client_beclass_apply"):
            _apply_client_beclass(client, workbook.name, content, preview, confirmation, command_key)


def _apply_client_beclass(client, filename, content, preview, confirmation, command_key) -> None:
    if confirmation != "APPLY":
        st.error("請輸入 APPLY 後再執行。")
        return
    try:
        receipt = client.apply_workbook(
            filename, content, preview_fingerprint=preview.preview_fingerprint,
            idempotency_key=command_key,
            correlation_id=f"client-beclass-ui:{uuid4()}",
        )
    except ClientBeClassImportApiError as error:
        st.error(f"Apply 未完成：{error.code}")
        return
    st.success("Client BeClass Apply 已完成。")
    st.json(receipt.model_dump())
    _render_pending_source_notice(
        receipt.review_required_count + receipt.existing_conflict_count,
    )


def _workbook_state(state_key: str, content: bytes) -> dict[str, object]:
    digest = sha256(content).hexdigest()
    state = st.session_state.setdefault(state_key, {})
    if state.get("digest") != digest:
        state.clear()
        state["digest"] = digest
    return state


def _resolve_development_key(default_key: str, widget_key: str) -> str:
    if not _is_development_environment():
        return default_key
    override = st.text_input("開發驗收 command key（留白使用檔案 digest）", key=widget_key)
    return override.strip() or default_key


def _render_staff_historical_card() -> None:
    with st.expander("Staff BeClass 歷史匯入（暫時入口）", expanded=False):
        st.caption(
            "僅 historical adoption；符合身分綁定的較新歷史快照可更新既有 Staff，"
            "不建立永久 current writer。"
        )
        revision = st.text_input("來源版本（同一批更新資料時填入新版本）", key="staff_source_revision").strip() or None
        workbook = st.file_uploader("選擇 Staff BeClass Excel", type=["xlsx"], key="staff_historical_workbook")
        if workbook is None:
            return
        content = workbook.getvalue()
        state = _workbook_state("staff_historical_import_state", content + str(revision).encode("utf-8"))
        client = StaffHistoricalImportApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers())
        if st.button("Preview Staff 歷史資料", key="staff_historical_preview"):
            try:
                state["preview"] = client.preview_workbook(workbook.name, content, revision)
            except StaffHistoricalImportApiError as error:
                st.error(f"Preview 未完成：{error.code}")
        preview = state.get("preview")
        if preview is None:
            return
        st.json(preview.model_dump())
        confirmation = st.text_input("輸入 APPLY 以確認 Staff 歷史採納", key="staff_historical_confirmation")
        command_digest = sha256(content + str(revision).encode("utf-8")).hexdigest()
        command_key = _resolve_development_key(
            f"staff-historical:{command_digest}",
            "staff_historical_command_key",
        )
        if st.button("Apply Staff 歷史資料", key="staff_historical_apply"):
            _apply_staff_historical(client, workbook.name, content, revision, preview, confirmation, command_key)


def _apply_staff_historical(client, filename, content, revision, preview, confirmation, command_key) -> None:
    if confirmation != "APPLY":
        st.error("請輸入 APPLY 後再執行。")
        return
    try:
        receipt = client.apply_workbook(
            filename, content, source_revision=revision,
            preview_fingerprint=preview.preview_fingerprint,
            idempotency_key=command_key,
            correlation_id=f"staff-historical-ui:{uuid4()}",
        )
    except StaffHistoricalImportApiError as error:
        st.error(f"Apply 未完成：{error.code}")
        return
    st.success("Staff 歷史資料 Apply 已完成。")
    st.json(receipt.model_dump())
    _render_pending_source_notice(receipt.review_required_count)


def _render_historical_order_card() -> None:
    with st.expander("訂單狀態與月嫂歷史配對", expanded=True):
        st.caption("僅補既有訂單的狀態、月嫂配對 evidence 與可空實際日期；先 Preview 再 Apply。")
        workbook = st.file_uploader("選擇訂單歷史 Excel", type=["xlsx"], key="historical_order_workbook")
        if workbook is None:
            return
        content = workbook.getvalue()
        state = _historical_order_state(content)
        command_key = _resolve_historical_order_command_key(content)
        client = HistoricalOrderAdoptionApiClient(base_url=resolve_api_base_url(), headers=build_admin_headers())
        if st.button("Preview 訂單歷史資料", key="historical_order_preview"):
            try:
                state["preview"] = client.preview_workbook(workbook.name, content)
            except HistoricalOrderAdoptionApiError as error:
                st.error(f"Preview 未完成：{error.code}")
            else:
                st.success("Preview 已完成，請確認結果後再 Apply。")
        preview = state.get("preview")
        if preview is None:
            return
        st.json(preview.model_dump())
        confirmation = st.text_input("輸入 APPLY 以確認訂單歷史採納", key="historical_order_apply_confirmation")
        if not st.button("Apply 訂單狀態與月嫂配對", key="historical_order_apply"):
            return
        if confirmation != "APPLY":
            st.error("請輸入 APPLY 後再執行。")
            return
        try:
            receipt = client.apply_workbook(
                workbook.name, content, preview_fingerprint=preview.preview_fingerprint,
                idempotency_key=command_key, correlation_id=f"historical-order-ui:{uuid4()}",
            )
        except HistoricalOrderAdoptionApiError as error:
            st.error(f"Apply 未完成：{error.code}")
            return
        st.success("訂單歷史資料 Apply 已完成。")
        st.json(receipt.model_dump())
        _render_pending_source_notice(receipt.review_required_count)


def _render_pending_source_notice(review_required_count: int) -> None:
    if review_required_count < 1:
        return
    st.warning(f"此檔有 {review_required_count} 筆待人工確認；來源警示已保留。")


def _historical_order_state(content: bytes) -> dict[str, object]:
    digest = sha256(content).hexdigest()
    state = st.session_state.setdefault("historical_order_import_state", {})
    if state.get("digest") != digest:
        state.clear()
        state["digest"] = digest
    return state


def _historical_order_command_key(content: bytes) -> str:
    return f"historical-order-workbook:{sha256(content).hexdigest()}"


def _resolve_historical_order_command_key(content: bytes) -> str:
    default_key = _historical_order_command_key(content)
    if not _is_development_environment():
        return default_key
    override = st.text_input("開發驗收 command key（留白使用檔案 digest）", key="historical_order_command_key")
    return override.strip() or default_key


def _render_finance_card() -> None:
    st.divider()
    render_finance_import_panel(
        FinanceImportApiClient(
            base_url=resolve_api_base_url(),
            headers=build_admin_headers(),
        )
    )
