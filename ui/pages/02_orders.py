"""
================================================================================
檔案名稱: ui/pages/02_orders.py
功能說明: 訂單管理頁面殼層 (OrderUI)
================================================================================
"""

from time import monotonic

import streamlit as st

from ui.api_clients.order_summary_api_client import OrderSummaryApiClient
from ui.pages.order.tab1_overview import _render_tab1_overview
from ui.pages.shared import build_admin_headers, resolve_api_base_url
from ui.request_state import (
    accept_request_result,
    begin_request,
    mark_request_stale,
    request_snapshot,
)

title = "📦 訂單管理"
REFERENCE_DATA_CACHE_SECONDS = 15
ORDER_SUMMARY_PAGE_SIZE = 200
def show():
    st.title(title)
    st.write("管理訂單生命週期、條款與指派配對。帳務作業請使用「帳務作業中心」。")
    search_text = st.text_input(
        "搜尋案件編號或客戶姓名",
        key="orders_summary_search_text",
    ).strip()
    _prepare_order_summary_page(search_text)
    _mark_order_summary_stale_if_refreshing(search_text)
    request = begin_request(st.session_state, "orders_summary_request")
    try:
        with st.spinner("正在載入案件摘要與月嫂清單…"):
            orders_data = _load_initial_orders(search_text, request)
    except Exception as error:
        accept_request_result(
            st.session_state,
            "orders_summary_request",
            request,
            item_count=0,
            error_message=str(error),
        )
        st.error(f"初始化載入資料失敗: {error}")
        return
    if not _render_order_summary_state(request, orders_data):
        return
    _render_order_summary_pagination()
    _render_tab1_overview(orders_data)


def _load_initial_orders(search_text, request):
    base_url = resolve_api_base_url()
    header_items = tuple(sorted(build_admin_headers().items()))
    order_cursor = st.session_state.get("orders_summary_after_case_no")
    cached = _cached_order_summary(search_text, order_cursor)
    result = (
        None
        if _cache_is_fresh(cached)
        else _request_order_summary(
            base_url,
            header_items,
            search_text or None,
            order_cursor,
            cached.get("etag") if cached else None,
        )
    )
    return _resolve_order_summary(result, search_text, cached, request)


def _request_order_summary(base_url, header_items, query_text, after_case_no, etag):
    return OrderSummaryApiClient(
        base_url=base_url,
        headers=dict(header_items),
    ).query(
        page_size=ORDER_SUMMARY_PAGE_SIZE,
        after_case_no=after_case_no,
        query_text=query_text,
        etag=etag,
    )


def _cached_order_summary(query_text, after_case_no):
    cache = st.session_state.get("orders_summary_cache", {})
    if not isinstance(cache, dict):
        return None
    candidate = cache.get(_order_summary_cache_key(query_text, after_case_no))
    return candidate if isinstance(candidate, dict) else None


def _mark_order_summary_stale_if_refreshing(query_text) -> None:
    cached = _cached_order_summary(
        query_text,
        st.session_state.get("orders_summary_after_case_no"),
    )
    if cached is not None and not _cache_is_fresh(cached):
        mark_request_stale(st.session_state, "orders_summary_request")


def _cache_is_fresh(cached) -> bool:
    if not cached:
        return False
    loaded_at = cached.get("loaded_at")
    return isinstance(loaded_at, float) and (
        monotonic() - loaded_at < REFERENCE_DATA_CACHE_SECONDS
    )


def _resolve_order_summary(result, query_text, cached, request):
    if result is None:
        st.session_state["orders_summary_next_cursor"] = cached.get("next_cursor")
        items = list(cached["items"])
        return _accept_order_summary(request, items)
    if result.not_modified:
        if not cached:
            raise ValueError("訂單摘要 304 缺少本機快取")
        cached["loaded_at"] = monotonic()
        return _accept_order_summary(request, list(cached["items"]))
    return _accept_order_summary(request, _store_order_summary(
        query_text,
        st.session_state.get("orders_summary_after_case_no"),
        result,
    ))


def _accept_order_summary(request, items):
    accepted = accept_request_result(
        st.session_state,
        "orders_summary_request",
        request,
        item_count=len(items),
    )
    return items if accepted else []


def _render_order_summary_state(request, orders_data) -> bool:
    snapshot = request_snapshot(st.session_state, "orders_summary_request")
    if snapshot.generation != request.generation:
        st.info("已忽略過期的案件摘要回應，正在使用較新的查詢。")
        return False
    if snapshot.status == "empty":
        st.info("目前沒有符合條件的案件摘要。")
    return True


def _store_order_summary(query_text, after_case_no, result):
    if result.page is None:
        raise ValueError("訂單摘要回應缺少資料")
    items = [item.model_dump(mode="json") for item in result.page.items]
    cache = st.session_state.setdefault("orders_summary_cache", {})
    cache[_order_summary_cache_key(query_text, after_case_no)] = {
        "etag": result.etag,
        "items": items,
        "next_cursor": result.page.next_cursor,
        "loaded_at": monotonic(),
    }
    st.session_state["orders_summary_next_cursor"] = result.page.next_cursor
    return items


def _order_summary_cache_key(query_text, after_case_no):
    return (query_text or "", after_case_no or "")


def _prepare_order_summary_page(query_text) -> None:
    previous_query = st.session_state.get("orders_summary_query_text")
    if previous_query == query_text:
        return
    st.session_state["orders_summary_query_text"] = query_text
    st.session_state["orders_summary_after_case_no"] = None
    st.session_state["orders_summary_cursor_history"] = []


def _render_order_summary_pagination() -> None:
    cursor = st.session_state.get("orders_summary_after_case_no")
    history = st.session_state.setdefault("orders_summary_cursor_history", [])
    next_cursor = st.session_state.get("orders_summary_next_cursor")
    if not history and not next_cursor:
        return
    previous_column, page_column, next_column = st.columns([1, 2, 1])
    if previous_column.button("上一頁案件", disabled=not history):
        st.session_state["orders_summary_after_case_no"] = history.pop()
        st.rerun()
    page_column.caption(
        f"案件摘要第 {len(history) + 1} 頁，每頁最多 {ORDER_SUMMARY_PAGE_SIZE} 筆"
    )
    if next_column.button("下一頁案件", disabled=not next_cursor):
        history.append(cursor)
        st.session_state["orders_summary_after_case_no"] = next_cursor
        st.rerun()
