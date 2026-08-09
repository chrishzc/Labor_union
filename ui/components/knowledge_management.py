"""Thin Streamlit panel for reviewed knowledge, indexes, jobs, and cited answers."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ui.api_clients.knowledge_retrieval_api_client import KnowledgeRetrievalApiClient
from ui.api_clients.line_api_client import LineAdminApiError
from ui.components.line_ui_support import complete_operation, has_capability, operation_headers


STATUS_LABELS = {
    "draft": "草稿",
    "reviewed": "已審核",
    "published": "已發布",
    "retired": "已停用",
}
JOB_STATUS_LABELS = {
    "pending": "等待處理",
    "processing": "處理中",
    "retry_pending": "等待重試",
    "completed": "已完成",
    "failed": "失敗",
}
INDEX_STATUS_LABELS = {
    "requested": "等待建立",
    "building": "建立中",
    "ready": "可使用",
    "stale": "需要更新",
    "failed": "失敗",
}


def render_knowledge_management(client, token, profile: dict[str, Any]) -> None:
    st.subheader("LINE 知識內容")
    st.caption("只有已審核並發布的內容可進入索引；自動回答一律標示為非權威資訊。")
    if not profile.get("runtime_availability", {}).get("knowledge_worker_enabled"):
        st.warning("知識背景處理目前未啟用；草稿可管理，但索引與回答工作不會自動執行。")
    workspace = st.radio("知識工作區", ["內容管理", "索引與工作", "測試提問"], horizontal=True)
    if workspace == "內容管理":
        _render_items(client, token, profile)
        return
    if workspace == "索引與工作":
        _render_indexes_and_jobs(client, token, profile)
        return
    _render_question(client, token)


def _render_items(client, token, profile) -> None:
    status_label = st.selectbox("內容狀態", ["全部", *STATUS_LABELS.values()])
    status = next((key for key, label in STATUS_LABELS.items() if label == status_label), None)
    try:
        items = client.items(token, status=status)
    except LineAdminApiError as error:
        st.error(f"無法載入知識內容：{error}")
        return
    if items:
        st.dataframe(pd.DataFrame(_item_rows(items)), width="stretch", hide_index=True)
        _render_item_action(client, token, profile, items)
    else:
        st.info("目前沒有符合條件的知識內容。")
    if has_capability(profile, "knowledge.manage"):
        _render_ingest_form(client, token)


def _item_rows(items):
    return [
        {
            "編號": item["id"],
            "名稱": item["title"],
            "來源識別": item["source_identity"],
            "狀態": STATUS_LABELS.get(item["lifecycle_status"], item["lifecycle_status"]),
            "版本": item["current_version"],
            "內容摘要碼": str(item.get("source_digest") or "")[:12],
            "來源網址": item.get("source_uri") or "-",
            "更新時間": item.get("updated_at_utc"),
        }
        for item in items
    ]


def _render_ingest_form(client, token) -> None:
    with st.expander("新增知識草稿"):
        with st.form("knowledge_ingest"):
            source_identity = st.text_input("來源識別", help="例如：union-service-policy")
            title = st.text_input("內容名稱")
            source_uri = st.text_input("來源網址（選填）")
            content = st.text_area("正式內容", height=220)
            submitted = st.form_submit_button("建立草稿", type="primary")
        if not submitted:
            return
        payload = {
            "source_identity": source_identity.strip(),
            "title": title.strip(),
            "source_uri": source_uri.strip() or None,
            "content": content.strip(),
        }
        _run_operation(client.ingest, token, "knowledge-ingest", payload, payload)


def _render_item_action(client, token, profile, items) -> None:
    item_id = st.selectbox("查看或處理一筆內容", [item["id"] for item in items])
    selected = next(item for item in items if item["id"] == item_id)
    try:
        detail = client.item(token, item_id)
    except LineAdminApiError as error:
        st.error(f"無法載入內容：{error}")
        return
    with st.expander("查看目前版本內容"):
        st.text(detail.get("content") or "")
    action = _allowed_action(selected["lifecycle_status"], profile)
    if action is None:
        return
    reason = st.text_input("處理原因", key=f"knowledge_reason_{item_id}").strip()
    confirmed = st.checkbox("我已閱讀並確認這份內容", key=f"knowledge_confirm_{item_id}")
    if not st.button(action[1], disabled=not (confirmed and reason), key=f"knowledge_action_{item_id}"):
        return
    payload = {"expected_version": selected["current_version"], "reason": reason}
    operation = f"knowledge-{action[0]}:{item_id}:{selected['current_version']}"
    _run_operation(client.transition, token, operation, payload, item_id, action[0], payload)


def _allowed_action(status, profile):
    if status == "draft" and has_capability(profile, "knowledge.manage"):
        return "review", "完成審核"
    if status == "reviewed" and has_capability(profile, "knowledge.publish"):
        return "publish", "發布內容"
    if status == "published" and has_capability(profile, "knowledge.publish"):
        return "retire", "停用內容"
    return None


def _render_indexes_and_jobs(client, token, profile) -> None:
    try:
        indexes = client.indexes(token)
        jobs = client.jobs(token)
    except LineAdminApiError as error:
        st.error(f"無法載入索引工作：{error}")
        return
    st.markdown("#### 索引狀態")
    st.dataframe(pd.DataFrame(_index_rows(indexes)), width="stretch", hide_index=True) if indexes else st.caption("尚未建立索引。")
    if has_capability(profile, "knowledge.reindex") and st.button("建立新版知識索引"):
        _run_operation(client.build_index, token, "knowledge-index-build", {}, headers_only=True)
    st.markdown("#### 背景工作")
    st.dataframe(pd.DataFrame(_job_rows(jobs)), width="stretch", hide_index=True) if jobs else st.caption("目前沒有知識工作。")
    failed = [item for item in jobs if item.get("processing_status") == "failed"]
    if failed and has_capability(profile, "knowledge.reindex"):
        job_id = st.selectbox("選擇失敗工作", [item["id"] for item in failed])
        if st.button("重新執行失敗工作"):
            _run_operation(client.retry_job, token, f"knowledge-job-retry:{job_id}", {}, job_id)


def _render_question(client, token) -> None:
    question = st.text_area("測試問題")
    if st.button("送出測試問題", disabled=not question.strip()):
        result = _run_operation(client.ask, token, "knowledge-question", {"question": question}, question)
        if result:
            st.session_state["knowledge_request_id"] = result["request_id"]
    request_id = st.session_state.get("knowledge_request_id")
    if not request_id:
        return
    try:
        answer = client.answer(token, request_id)
    except LineAdminApiError as error:
        st.error(f"無法讀取回答結果：{error}")
        return
    st.info(f"目前狀態：{answer['request_status']}")
    if answer.get("answer_text"):
        st.write(answer["answer_text"])
        st.warning("此回答僅供參考，不是工會的正式個案、法律或付款決策。")
        st.dataframe(
            pd.DataFrame(_citation_rows(answer.get("citations", []))),
            width="stretch",
            hide_index=True,
        )


def _index_rows(indexes):
    return [
        {
            "索引版本": item["index_version"],
            "狀態": INDEX_STATUS_LABELS.get(item["index_status"], item["index_status"]),
            "內容集合摘要": str(item.get("content_set_digest") or "")[:12],
            "完成時間": item.get("built_at_utc"),
        }
        for item in indexes
    ]


def _job_rows(jobs):
    return [
        {
            "工作編號": item["id"],
            "工作類型": "建立索引" if item["job_type"] == "index_build" else "產生回答",
            "狀態": JOB_STATUS_LABELS.get(item["processing_status"], item["processing_status"]),
            "嘗試次數": item.get("attempt_count"),
            "錯誤": item.get("last_error_code") or "",
            "建立時間": item.get("created_at_utc"),
        }
        for item in jobs
    ]


def _citation_rows(citations):
    return [
        {
            "來源": item["source_identity"],
            "來源版本": item["source_version"],
            "引用內容": item["safe_excerpt"],
        }
        for item in citations
    ]


# This boundary centralizes stable operation identities for every knowledge mutation.
def _run_operation(method, token, operation, fingerprint_payload, *args, headers_only=False):
    headers = operation_headers(operation, fingerprint_payload)
    try:
        if headers_only:
            result = method(token, headers=headers)
        else:
            result = method(token, *args, headers=headers)
    except LineAdminApiError as error:
        st.error(f"操作失敗：{error}")
        return None
    complete_operation(operation)
    st.success("操作已送出。")
    return result


__all__ = ["render_knowledge_management"]
