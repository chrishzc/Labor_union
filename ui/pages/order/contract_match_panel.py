"""Typed, read-only contract-completion status panel."""

from __future__ import annotations

from uuid import uuid4

import streamlit as st

from ui.api_clients.contract_completion_api_client import (
    ContractCompletionApiClient,
    ContractCompletionApiError,
)
from ui.api_clients.contract_signing_api_client import (
    ContractSigningApiClient,
    ContractSigningApiError,
)
from ui.pages.shared import build_admin_headers, resolve_api_base_url


def render_contract_match_panel(case_no, headers=None, *_args, **_kwargs):
    _render_contract_signing_state(case_no, headers)
    st.markdown("#### 📋 合約完成確認")
    try:
        query = ContractCompletionApiClient(base_url=resolve_api_base_url(), headers=headers or build_admin_headers()).query(case_no)
    except ContractCompletionApiError as error:
        st.warning(f"合約狀態查詢失敗：{error}")
        return
    columns = st.columns(2)
    columns[0].metric("合約已完成", "✅ 是" if query.contract_completed else "❌ 否")
    columns[1].metric("訂單生命週期狀態", query.lifecycle_status)
    st.caption(f"訂金已核銷：{'✅' if query.deposit_settled else '❌'} ｜ 服務時段條款完整：{'✅' if query.service_time_terms_complete else '❌'} ｜ 可執行合約完成：{'✅' if query.completion_available else '❌'}")
    if query.domain_blockers:
        st.warning("目前阻擋原因：" + "、".join(_blocker_label(value) for value in query.domain_blockers))


def _render_contract_signing_state(case_no, headers):
    st.markdown("#### ✍️ 契約簽署流程")
    try:
        client = ContractSigningApiClient(
            base_url=resolve_api_base_url(),
            headers=headers or build_admin_headers(),
        )
        query = client.query(case_no)
    except ContractSigningApiError as error:
        st.warning(f"契約簽署狀態查詢失敗：{error}")
        return
    staff_signed = sum(segment.signed_received for segment in query.staff_segments)
    columns = st.columns(3)
    columns[0].metric("月嫂簽回", f"{staff_signed}/{len(query.staff_segments)}")
    columns[1].metric("簽約前服務承諾", "✅ 已建立" if query.commitment_id else "❌ 尚未建立")
    columns[2].metric("客戶簽回", "✅ 已簽回" if query.client_signed_received else "❌ 尚未簽回")
    if query.contract_identity:
        st.caption("客戶簽回文件已成為正式契約識別；訂單成立仍取決於訂金核銷。")
    _render_document_versions(query, client)
    _render_contract_controls(case_no, query, client)


def _render_document_versions(query, client) -> None:
    if not query.documents:
        st.info("尚未建立契約文件版本。")
        return
    st.caption("不可變文件封存版本")
    st.dataframe([
        {
            "版本 ID": document.document_version_id,
            "範圍": document.scope,
            "角色": document.role,
            "版本": document.version_number,
            "範本": document.template_key or "簽回封存",
            "封存雜湊": document.archive_sha256,
            "格式": document.mime_type,
            "大小": document.file_size,
        }
        for document in query.documents
    ], hide_index=True, use_container_width=True)
    document_id = st.selectbox(
        "選擇要取得的不可變文件版本",
        options=[document.document_version_id for document in query.documents],
        key=f"contract-document-download-{query.case_no}",
    )
    if st.button("下載已稽核文件", key=f"contract-document-download-button-{query.case_no}"):
        try:
            content = client.download_document(query.case_no, document_id)
        except ContractSigningApiError as error:
            st.error(f"文件下載失敗：{error}")
        else:
            st.download_button("儲存文件", content, file_name=f"contract-document-{document_id}")


def _render_contract_controls(case_no, query, client) -> None:
    st.caption("操作會建立受控簽署命令；簽回時會原子建立 Contract Completion 與剩餘期款。")
    for segment in query.staff_segments:
        _render_staff_segment_controls(case_no, query, segment, client)
    if query.commitment_id is None:
        return
    _render_client_controls(case_no, query, client)


def _render_staff_segment_controls(case_no, query, segment, client) -> None:
    with st.expander(f"月嫂 {segment.staff_id} 契約", expanded=not segment.signed_received):
        if not segment.sent:
            url = st.text_input("安全下載網址", key=f"staff-url-{segment.segment_id}")
            if st.button("寄送月嫂契約", key=f"staff-send-{segment.segment_id}"):
                _run_contract_command(lambda: client.send_staff_contract(case_no, segment.segment_id, url))
        if segment.sent and not segment.signed_received:
            document = st.file_uploader("上傳月嫂簽回檔", key=f"staff-return-{segment.segment_id}")
            snapshot_key = f"staff-contract-version-{case_no}-{segment.segment_id}"
            submission = None if document is None else _document_version_snapshot(snapshot_key, document, _current_sent_document_version(query, "staff_segment", f"staff-segment:{segment.segment_id}"))
            if st.button("記錄月嫂簽回", key=f"staff-sign-{segment.segment_id}"):
                if document is None:
                    st.warning("請先選擇簽回檔案。")
                else:
                    error_code = _run_contract_command(lambda: client.record_staff_signed_return(case_no, segment.segment_id, document, document.name, document.type or "application/octet-stream", submission["document_version_id"], idempotency_key=submission["idempotency_key"]))
                    _clear_stale_document_snapshot(snapshot_key, error_code)


def _render_client_controls(case_no, query, client) -> None:
    with st.expander("客戶契約", expanded=not query.client_signed_received):
        if not query.client_document_sent:
            url = st.text_input("客戶安全下載網址", key="client-contract-url")
            if st.button("寄送客戶契約", key="client-contract-send"):
                _run_contract_command(lambda: client.send_client_contract(case_no, url))
        if query.client_document_sent and not query.client_signed_received:
            document = st.file_uploader("上傳客戶簽回檔", key="client-contract-return")
            snapshot_key = f"client-contract-version-{case_no}"
            submission = None if document is None else _document_version_snapshot(snapshot_key, document, _current_sent_document_version(query, "client_contract", "client-contract"))
            if st.button("記錄客戶簽回並完成合約", key="client-contract-sign"):
                if document is None:
                    st.warning("請先選擇簽回檔案。")
                else:
                    error_code = _run_contract_command(lambda: client.record_client_signed_return(case_no, document, document.name, document.type or "application/octet-stream", submission["document_version_id"], idempotency_key=submission["idempotency_key"]))
                    _clear_stale_document_snapshot(snapshot_key, error_code)


def _current_sent_document_version(query, scope: str, target_key: str) -> int:
    sent_documents = [
        document.document_version_id
        for document in query.documents
        if document.scope == scope
        and document.target_key == target_key
        and document.role == "template_generated"
    ]
    if not sent_documents:
        raise ContractSigningApiError(None, "找不到目前可簽回的契約版本，請先重新查詢。")
    return max(sent_documents)


def _document_version_snapshot(snapshot_key: str, document, document_version_id: int) -> dict[str, int | str]:
    signature = (document.name, document.size)
    snapshot = st.session_state.get(snapshot_key)
    if snapshot is None or snapshot["signature"] != signature:
        st.session_state[snapshot_key] = {
            "signature": signature,
            "document_version_id": document_version_id,
            "idempotency_key": f"ui-contract-return-{uuid4().hex}",
        }
    return st.session_state[snapshot_key]


def _clear_stale_document_snapshot(snapshot_key: str, error_code: str | None) -> None:
    if error_code != "contract_document_version_stale":
        return
    st.session_state.pop(snapshot_key, None)
    st.info("契約版本已更新，請重新確認後再次提交簽回檔。")


def _run_contract_command(command) -> str | None:
    try:
        receipt = command()
    except ContractSigningApiError as error:
        st.error(f"契約簽署操作失敗：{error}")
        if error.code:
            st.caption(f"錯誤代碼：{error.code}")
        return error.code
    st.success("契約簽署操作已完成，請重新整理以取得最新狀態。")
    st.caption(
        f"文件版本 #{receipt.document_version_id} ｜簽署事件 #{receipt.signing_event_id}"
        + (f" ｜承諾 #{receipt.commitment_id}" if receipt.commitment_id else "")
        + (" ｜已完成 Contract Completion" if receipt.contract_identity else "")
    )
    return None


def _blocker_label(code: str) -> str:
    return {"contract_identity_missing": "缺少外部契約識別", "official_service_dates_incomplete": "正式服務日尚未建立"}.get(code, code)
