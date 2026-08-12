"""Thin Customer Service management UI."""

from __future__ import annotations

from uuid import uuid4

import streamlit as st

from ui.api_clients.customer_service_api_client import CustomerServiceApiClient
from ui.api_clients.line_api_client import LineAdminApiError
from ui.components.line_ui_support import has_capability


_STATUS_LABELS = {"waiting": "等待客服", "handling": "處理中", "resolved": "已完成"}
_CATEGORY_LABELS = {"service_flow": "服務流程", "payment_subsidy": "收費與補助", "service_progress": "服務進度", "profile_update": "修改資料", "contact_union": "聯絡工會", "other": "其他問題"}


def render_customer_service_manager(client, token, profile) -> None:
    bounded_client = CustomerServiceApiClient(client)
    st.subheader("客服管理中心")
    st.caption("處理一般用戶由 LINE「服務說明」提出的需求，回覆會排入 canonical LINE worker。")
    try:
        _render_center(bounded_client, token, profile)
    except LineAdminApiError as error:
        st.error(f"客服中心目前無法使用：{error}")


def _render_center(client, token, profile):
    summary = client.summary(token)
    columns = st.columns(3)
    columns[0].metric("等待客服", summary.waiting)
    columns[1].metric("處理中", summary.handling)
    columns[2].metric("今日完成", summary.resolved_today)
    status = st.selectbox("處理狀態", ["waiting", "handling", "resolved"], format_func=_STATUS_LABELS.get)
    category = st.selectbox("問題類型", [""] + list(_CATEGORY_LABELS), format_func=lambda value: "全部" if not value else _CATEGORY_LABELS[value])
    search = st.text_input("搜尋案件編號或客服單號")
    page = client.tickets(token, {"status": status, "category": category, "search": search, "page": 1, "page_size": 50})
    if not page.items:
        st.info("目前沒有符合條件的客服需求。")
        return
    selected = st.selectbox("客服需求", page.items, format_func=_ticket_label)
    _render_detail(client, token, profile, selected.ticket_id)


def _ticket_label(ticket):
    return f"#{ticket.ticket_id}｜{_CATEGORY_LABELS.get(ticket.category, ticket.category)}｜{ticket.case_no or '未綁定案件'}"


def _render_detail(client, token, profile, ticket_id):
    detail = client.detail(token, ticket_id)
    ticket = detail.ticket
    st.write(f"客戶：{ticket.client_name or '未綁定'}　電話：{ticket.client_phone or '無'}")
    st.write(f"LINE：{ticket.line_user_id_masked}　案件：{ticket.case_no or '無'}　版本：{ticket.version}")
    for event in detail.events:
        st.chat_message("assistant" if event.event_type == "agent_reply" else "user").write(event.message_text or event.event_type)
    if not has_capability(profile, "line.customer_service.handle"):
        return
    _render_commands(client, token, ticket)


def _render_commands(client, token, ticket):
    with st.form(f"customer-service-{ticket.ticket_id}"):
        status = st.selectbox("狀態", list(_STATUS_LABELS), index=list(_STATUS_LABELS).index(ticket.status), format_func=_STATUS_LABELS.get)
        note = st.text_area("內部備註", ticket.internal_note or "")
        reply = st.text_area("回覆客戶")
        resolve = st.checkbox("回覆後標示為已完成")
        save = st.form_submit_button("儲存狀態與備註")
        send = st.form_submit_button("送出 LINE 回覆", type="primary")
    if save:
        _run(lambda: client.update(token, ticket.ticket_id, {"status": status, "internal_note": note, "expected_version": ticket.version, "idempotency_key": str(uuid4())}), "客服需求已更新")
    if send:
        if not reply.strip():
            st.warning("請輸入回覆內容。")
            return
        _run(lambda: client.reply(token, ticket.ticket_id, {"reply_text": reply, "resolve": resolve, "internal_note": note, "expected_version": ticket.version, "idempotency_key": str(uuid4())}), "已排入 LINE 回覆")


def _run(operation, success_message):
    try:
        operation()
    except LineAdminApiError as error:
        st.error(str(error))
        return
    st.success(success_message)
    st.rerun()


__all__ = ["render_customer_service_manager"]
