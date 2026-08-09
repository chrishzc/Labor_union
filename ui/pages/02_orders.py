"""
================================================================================
檔案名稱: ui/pages/02_orders.py
功能說明: 訂單與帳務管理系統頁面殼層 (OrderUI)
================================================================================
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from time import monotonic

import streamlit as st

from ui.api_clients.order_summary_api_client import OrderSummaryApiClient
from ui.api_clients.staff_summary_api_client import StaffSummaryApiClient
from ui.pages.order.tab1_overview import _render_tab1_overview
from ui.pages.shared import build_admin_headers, resolve_api_base_url
from ui.request_state import (
    accept_request_result,
    begin_request,
    mark_request_stale,
    request_snapshot,
)

title = "📦 訂單與帳務管理系統"
INITIAL_QUERY_WORKERS = 2
REFERENCE_DATA_CACHE_SECONDS = 15
ORDER_WORKSPACES = (
    "📊 訂單資訊總覽",
    "💰 客戶收款核銷",
    "🧾 月嫂薪資調整",
    "🏦 月嫂付款核銷",
    "📤 應付帳款查詢/輸出",
    "核銷補助清冊",
)


def _render_order_page_shell(orders_data, clients, staff_list):
    workspace = st.radio(
        "訂單工作區",
        ORDER_WORKSPACES,
        horizontal=True,
        label_visibility="collapsed",
        key="orders_workspace",
    )
    if workspace == ORDER_WORKSPACES[0]:
        return _render_tab1_overview(orders_data)
    if workspace == ORDER_WORKSPACES[1]:
        _render_client_receipt_tab(orders_data)
        return None
    if workspace == ORDER_WORKSPACES[2]:
        return _render_payroll_adjustment_tab(orders_data, staff_list)
    if workspace == ORDER_WORKSPACES[3]:
        return _render_staff_payout_tab(staff_list)
    if workspace == ORDER_WORKSPACES[4]:
        return _render_accounts_payable_workspace()
    return _render_subsidy_reconciliation_workspace()


def _render_accounts_payable_workspace() -> None:
    if not st.toggle(
        "載入應付帳款查詢／輸出",
        value=False,
        key="load_accounts_payable",
    ):
        st.caption("需要查詢或輸出時再載入。")
        return
    from ui.pages.order.tab4_accounts_payable import (
        _render_tab4_accounts_payable,
    )

    _render_tab4_accounts_payable()


def _render_subsidy_reconciliation_workspace() -> None:
    if not st.toggle(
        "載入核銷補助清冊",
        value=False,
        key="load_subsidy_reconciliation",
    ):
        st.caption("需要查詢或下載時再載入。")
        return
    from ui.pages.order.tab5_subsidy_reconciliation import (
        _render_tab5_subsidy_reconciliation,
    )

    _render_tab5_subsidy_reconciliation()


# Kept cohesive because widget state and lazy imports form one optional panel.
def _render_staff_payout_tab(staff_list) -> None:
    staff_options = _staff_options(staff_list)
    if not staff_options:
        st.info("目前沒有可選擇的月嫂。")
        return
    try:
        from ui.api_clients.staff_payout_api_client import StaffPayoutApiClient
        from ui.pages.staff_payables.staff_payout_panel import (
            render_staff_payout_panel,
        )

        _apply_pending_staff_payout_selection(staff_options)
        selected_label = st.selectbox(
            "選擇月嫂",
            tuple(staff_options),
            key="staff_payout_staff_selector",
        )
        client = StaffPayoutApiClient(
            base_url=resolve_api_base_url(),
            headers=build_admin_headers(),
        )
        render_staff_payout_panel(staff_options[selected_label], client)
    except Exception as e:
        import traceback
        st.warning(f"⚠️ 模組載入失敗 (資料初始化不完整或架構遺失)：{e}")
        st.expander("查看詳細錯誤").code(traceback.format_exc())


def _apply_pending_staff_payout_selection(
    staff_options: dict[str, int],
) -> None:
    pending_staff_id = st.session_state.pop(
        "pending_staff_payout_staff_id",
        None,
    )
    selected_label = next(
        (
            label
            for label, staff_id in staff_options.items()
            if staff_id == pending_staff_id
        ),
        None,
    )
    if selected_label is not None:
        st.session_state["staff_payout_staff_selector"] = selected_label


# Kept cohesive because widget state and lazy imports form one optional panel.
def _render_client_receipt_tab(orders_data) -> None:
    case_no = _select_case_number(orders_data, "client_receipt_case")
    if case_no is None:
        return
    try:
        from ui.api_clients.client_receipt_reconciliation_api_client import (
            ClientReceiptReconciliationApiClient,
        )
        from ui.pages.order.client_receipt_reconciliation_panel import (
            render_client_receipt_reconciliation_panel,
        )

        client = ClientReceiptReconciliationApiClient(
            base_url=resolve_api_base_url(),
            headers=build_admin_headers(),
        )
        render_client_receipt_reconciliation_panel(case_no, client)
    except Exception as e:
        import traceback
        st.warning(f"⚠️ 模組載入失敗 (資料初始化不完整或架構遺失)：{e}")
        st.expander("查看詳細錯誤").code(traceback.format_exc())


# Kept cohesive because all three payroll views share one selected case snapshot.
def _render_payroll_adjustment_tab(orders_data, staff_list) -> None:
    case_no = _select_case_number(orders_data, "payroll_adjustment_case")
    if case_no is None:
        return
    try:
        from ui.api_clients.payroll_api_client import PayrollApiClient
        from ui.api_clients.payroll_rebuild_api_client import PayrollRebuildApiClient
        from ui.pages.payroll.adjustment_panel import (
            render_payroll_adjustment_panel,
        )
        from ui.pages.payroll.rebuild_panel import (
            render_payroll_rebuild_panel,
        )

        base_url = resolve_api_base_url()
        headers = build_admin_headers()
        rebuild_client = PayrollRebuildApiClient(base_url=base_url, headers=headers)
        render_payroll_rebuild_panel(case_no, rebuild_client)
        st.divider()
        render_payroll_adjustment_panel(
            case_no,
            PayrollApiClient(base_url=base_url, headers=headers),
        )
        st.divider()
        _render_staff_monthly_summary(staff_list, rebuild_client)
    except Exception as e:
        import traceback
        st.warning(f"⚠️ 模組載入失敗 (資料初始化不完整或架構遺失)：{e}")
        st.expander("查看詳細錯誤").code(traceback.format_exc())


# Kept cohesive because the three selectors define one bounded monthly query.
def _render_staff_monthly_summary(staff_list, client) -> None:
    from ui.pages.payroll.rebuild_panel import (
        render_staff_monthly_payroll_panel,
    )

    staff_options = _staff_options(staff_list)
    if not staff_options:
        return
    selected_label = st.selectbox(
        "月份加總月嫂",
        tuple(staff_options),
        key="payroll_monthly_staff",
    )
    current_date = date.today()
    columns = st.columns(2)
    year = int(
        columns[0].number_input(
            "年份",
            min_value=2020,
            max_value=2100,
            value=current_date.year,
        )
    )
    month = int(
        columns[1].number_input(
            "月份",
            min_value=1,
            max_value=12,
            value=current_date.month,
        )
    )
    render_staff_monthly_payroll_panel(
        staff_options[selected_label],
        year,
        month,
        client,
    )


def _select_case_number(orders_data, key: str) -> str | None:
    case_numbers = tuple(
        sorted(
            {
                str(order.get("case_no") or "").strip()
                for order in orders_data
                if str(order.get("case_no") or "").strip()
            }
        )
    )
    if not case_numbers:
        st.info("目前沒有可選擇的訂單。")
        return None
    return st.selectbox("選擇案件", case_numbers, key=key)


def _staff_options(staff_list) -> dict[str, int]:
    options = {}
    for staff in staff_list:
        staff_id = staff.get("id")
        if isinstance(staff_id, bool) or not isinstance(staff_id, int):
            continue
        label = f"{staff.get('name') or '未命名月嫂'}（#{staff_id}）"
        options[label] = staff_id
    return options


def show():
    st.title("📦 訂單與帳務管理系統")
    st.write("本系統串接了 `v_order_details` 整合計算檢視表，提供訂單生命週期、指派配對以及帳務實收狀態的管理。")
    search_text = st.text_input(
        "搜尋案件編號或客戶姓名",
        key="orders_summary_search_text",
    ).strip()
    _prepare_order_summary_page(search_text)
    _mark_order_summary_stale_if_refreshing(search_text)
    request = begin_request(st.session_state, "orders_summary_request")
    try:
        with st.spinner("正在載入案件摘要與月嫂清單…"):
            orders_data, staff_list = _load_initial_lists(search_text, request)
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
    _render_staff_summary_pagination()
    _render_order_summary_pagination()
    _render_order_page_shell(orders_data, [], staff_list)


def _load_initial_lists(search_text, request):
    base_url = resolve_api_base_url()
    header_items = tuple(sorted(build_admin_headers().items()))
    staff_cursor = st.session_state.get("staff_summary_after_id")
    order_cursor = st.session_state.get("orders_summary_after_case_no")
    cached = _cached_order_summary(search_text, order_cursor)
    with ThreadPoolExecutor(max_workers=INITIAL_QUERY_WORKERS) as executor:
        orders = (
            None
            if _cache_is_fresh(cached)
            else executor.submit(
                _request_order_summary,
                base_url,
                header_items,
                search_text or None,
                order_cursor,
                cached.get("etag") if cached else None,
            )
        )
        staff = executor.submit(_request_staff_summary, base_url, header_items, staff_cursor)
    return _resolve_order_summary(orders, search_text, cached, request), _resolve_staff_summary(
        staff.result()
    )


def _request_order_summary(base_url, header_items, query_text, after_case_no, etag):
    return OrderSummaryApiClient(
        base_url=base_url,
        headers=dict(header_items),
    ).query(
        page_size=50,
        after_case_no=after_case_no,
        query_text=query_text,
        etag=etag,
    )


def _request_staff_summary(base_url, header_items, after_id):
    page = StaffSummaryApiClient(
        base_url=base_url,
        headers=dict(header_items),
    ).query(after_id=after_id)
    return page


def _resolve_staff_summary(page):
    st.session_state["staff_summary_next_cursor"] = page.next_cursor
    return [item.model_dump(mode="json") for item in page.items]


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


def _resolve_order_summary(future, query_text, cached, request):
    if future is None:
        st.session_state["orders_summary_next_cursor"] = cached.get("next_cursor")
        items = list(cached["items"])
        return _accept_order_summary(request, items)
    result = future.result()
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
    previous_column, page_column, next_column = st.columns([1, 2, 1])
    if previous_column.button("上一頁案件", disabled=not history):
        st.session_state["orders_summary_after_case_no"] = history.pop()
        st.rerun()
    page_column.caption(f"案件摘要第 {len(history) + 1} 頁，每頁最多 50 筆")
    next_cursor = st.session_state.get("orders_summary_next_cursor")
    if next_column.button("下一頁案件", disabled=not next_cursor):
        history.append(cursor)
        st.session_state["orders_summary_after_case_no"] = next_cursor
        st.rerun()


def _render_staff_summary_pagination() -> None:
    cursor = st.session_state.get("staff_summary_after_id")
    history = st.session_state.setdefault("staff_summary_cursor_history", [])
    previous_column, page_column, next_column = st.columns([1, 2, 1])
    if previous_column.button("上一頁月嫂", disabled=not history):
        st.session_state["staff_summary_after_id"] = history.pop()
        st.rerun()
    page_column.caption(f"月嫂摘要第 {len(history) + 1} 頁，每頁最多 200 筆")
    next_cursor = st.session_state.get("staff_summary_next_cursor")
    if next_column.button("下一頁月嫂", disabled=not next_cursor):
        history.append(cursor)
        st.session_state["staff_summary_after_id"] = next_cursor
        st.rerun()
