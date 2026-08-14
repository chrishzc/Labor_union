"""
File: 09_data_import.py
Description: 顯示資料匯入中心並以 typed API 上傳 HCM 與訂單歷史 workbook。
"""

from hashlib import sha256
import os
from uuid import uuid4

import streamlit as st

from ui.api_clients.hcm_import_api_client import HcmImportApiClient, HcmImportApiError
from ui.api_clients.historical_order_adoption_api_client import HistoricalOrderAdoptionApiClient, HistoricalOrderAdoptionApiError
from ui.pages.shared import build_admin_headers, resolve_api_base_url


def show() -> None:
    st.title("📥 資料匯入中心")
    st.caption("每一類資料使用自己的欄位契約與 typed Preview／Apply；髒列不阻擋同檔合法列。")
    _render_hcm_card()
    _render_historical_order_card()
    _render_future_cards()


def _render_hcm_card() -> None:
    with st.expander("HCM 案件匯入", expanded=True):
        st.caption("上傳 .xlsx；相同檔案重試會回放 receipt，錯誤列會建立 HCM review。")
        workbook = st.file_uploader("選擇 HCM Excel", type=["xlsx"], key="hcm_workbook")
        content = None if workbook is None else workbook.getvalue()
        key = None if content is None else _resolve_command_key(content)
        if not st.button("上傳並處理 HCM", key="hcm_workbook_upload"):
            return
        if workbook is None or content is None or key is None:
            st.error("請先選擇 HCM .xlsx 檔案。")
            return
        try:
            receipt = HcmImportApiClient(
                base_url=resolve_api_base_url(), headers=build_admin_headers()
            ).ingest_workbook(workbook.name, content, idempotency_key=key, correlation_id=f"hcm-ui:{uuid4()}")
        except HcmImportApiError as error:
            st.error(f"上傳未完成：{error.code}")
            return
        st.success("已完成 HCM 逐列處理。")
        st.json(receipt.model_dump())


def _command_key(content: bytes) -> str:
    return f"hcm-workbook:{sha256(content).hexdigest()}"


def _resolve_command_key(content: bytes) -> str:
    default_key = _command_key(content)
    if not _is_development_environment():
        return default_key
    override = st.text_input("開發驗收 command key（留白使用檔案 digest）", key="hcm_upload_command_key")
    return override.strip() or default_key


def _is_development_environment() -> bool:
    app_environment = (os.getenv("APP_ENV", "development") or "development").strip().lower()
    return app_environment in {"development", "dev", "local", "test"}


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


def _render_future_cards() -> None:
    st.subheader("後續類別")
    st.info("Client BeClass、Staff BeClass 與銀行流水會各自接入 typed API；目前不會從此頁呼叫 legacy script。")
