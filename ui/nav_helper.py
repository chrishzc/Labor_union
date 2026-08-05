"""Shared navigation + processing-queue helper for the sidebar-radio page switcher.

ui/app.py drives page switching with a single st.sidebar.radio bound to the
NAV_KEY session_state key. Any page can therefore switch the active page by
writing NAV_KEY and calling st.rerun() -- this module centralizes that so
pages don't duplicate the session_state wiring.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

NAV_KEY = "nav_choice"
_PENDING_NAV_KEY = "pending_nav_choice"
QUEUE_KEY = "alert_processing_queue"
_PENDING_TAB_KEY = "pending_page_tab"


def navigate_to(
    page_title: str,
    *,
    queue_items: list[dict[str, Any]] | None = None,
    queue_target_key: str | None = None,
) -> None:
    """Request a switch to page_title, optionally carrying a processing queue.

    Cannot write NAV_KEY directly here: by the time a page's own render code
    runs, app.py has already instantiated the sidebar radio bound to NAV_KEY
    for this run, and Streamlit forbids mutating a widget's key after it has
    been instantiated. Writing a separate "pending" key instead, which
    apply_pending_navigation() consumes at the top of the NEXT run (before
    the radio widget is created), avoids that restriction.
    """
    st.session_state[_PENDING_NAV_KEY] = page_title
    if queue_items is not None:
        st.session_state[QUEUE_KEY] = {
            "items": queue_items,
            "index": 0,
            "target_key": queue_target_key,
        }
    st.rerun()


def apply_pending_navigation() -> None:
    """Consume a pending navigate_to() request. Call before creating the radio widget."""
    pending = st.session_state.pop(_PENDING_NAV_KEY, None)
    if pending is not None:
        st.session_state[NAV_KEY] = pending


def current_queue(target_key: str) -> dict[str, Any] | None:
    """Return the active queue dict if it exists and targets target_key, else None."""
    queue = st.session_state.get(QUEUE_KEY)
    if not queue or queue.get("target_key") != target_key:
        return None
    if queue["index"] >= len(queue["items"]):
        st.session_state.pop(QUEUE_KEY, None)
        return None
    return queue


def current_queue_item(target_key: str) -> dict[str, Any] | None:
    queue = current_queue(target_key)
    if queue is None:
        return None
    return queue["items"][queue["index"]]


def advance_queue(target_key: str) -> None:
    queue = st.session_state.get(QUEUE_KEY)
    if not queue or queue.get("target_key") != target_key:
        return
    queue["index"] += 1
    if queue["index"] >= len(queue["items"]):
        st.session_state.pop(QUEUE_KEY, None)


def end_queue() -> None:
    st.session_state.pop(QUEUE_KEY, None)


def request_tab(tab_id: str) -> None:
    """要求目標頁面在下次渲染時直接跳到指定分頁（跳過分頁列本身），
    給沒有 items 清單、單純「落地時要停在哪個分頁」的深連結情境使用
    （例如 AI 助理回答連結）。跟 QUEUE_KEY 的差別：後者是給異常警示中心那種
    「一批案件、依序處理」的情境，這裡只是單次的「落地分頁」提示，不帶案件清單。"""
    st.session_state[_PENDING_TAB_KEY] = tab_id


def consume_pending_tab() -> str | None:
    """讀取並清除 request_tab() 設定的分頁提示；只能被消費一次，避免使用者之後
    在同一頁手動切換到分頁列時，又被重複拉回這個分頁。"""
    return st.session_state.pop(_PENDING_TAB_KEY, None)
