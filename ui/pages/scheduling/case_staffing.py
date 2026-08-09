"""Case-centred thin shell for the authoritative Assignment Plan API."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.api_clients.assignment_plan_api_client import AssignmentPlanApiClient
from ui.api_clients.case_architecture_bootstrap_api_client import (
    CaseArchitectureBootstrapApiClient,
)
from ui.pages.order.case_architecture_bootstrap_panel import (
    ensure_case_architecture_ready,
)
from ui.pages.scheduling.assignment_plan_panel import (
    render_assignment_plan_panel,
)
from ui.pages.shared import build_admin_headers, resolve_api_base_url


# Kept cohesive because selected-case state and bootstrap readiness form one UI transaction.
def render_case_staffing(
    *,
    orders: list[dict[str, Any]] | None = None,
    staff: list[dict[str, Any]] | None = None,
) -> None:
    st.subheader("案件人力配置")
    orders = orders if orders is not None else []
    staff = staff if staff is not None else []
    if orders is None or staff is None:
        return
    selectable_orders = _selectable_orders(orders)
    if not selectable_orders:
        st.info("目前沒有可設定正式人力的案件。")
        return
    _apply_pending_case_selection(selectable_orders)
    selected_label = st.selectbox(
        "案件",
        list(selectable_orders),
        key="staffing_case",
    )
    selected_order = selectable_orders[selected_label]
    case_no = str(selected_order["case_no"])
    base_url = resolve_api_base_url()
    headers = build_admin_headers()
    bootstrap_client = CaseArchitectureBootstrapApiClient(
        base_url=base_url,
        headers=headers,
    )
    if not ensure_case_architecture_ready(case_no, bootstrap_client):
        st.info("案件根狀態與正式服務時間完成後，才會開放 Assignment Plan。")
        return
    client = AssignmentPlanApiClient(
        base_url=base_url,
        headers=headers,
    )
    render_assignment_plan_panel(
        case_no,
        client,
        staff_choices=_staff_choices(staff),
    )


def _apply_pending_case_selection(
    selectable_orders: dict[str, dict[str, Any]],
) -> None:
    pending_case_no = st.session_state.pop(
        "pending_scheduling_case_no",
        None,
    )
    selected_label = next(
        (
            label
            for label, order in selectable_orders.items()
            if str(order.get("case_no")) == pending_case_no
        ),
        None,
    )
    if selected_label is not None:
        st.session_state["staffing_case"] = selected_label


def _selectable_orders(
    orders: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        _order_label(order): order
        for order in orders
        if order.get("order_status") in {"訂單成立", "服務中"}
        and order.get("case_no")
    }


def _order_label(order: dict[str, Any]) -> str:
    return (
        f"{order.get('case_no')}｜{order.get('client_name', '')}｜"
        f"{order.get('order_status', '')}"
    )


def _staff_choices(staff: list[dict[str, Any]]) -> dict[str, int]:
    return {
        f"#{item['id']}｜{item.get('name', '')}": item["id"]
        for item in staff
        if isinstance(item.get("id"), int) and item["id"] > 0
    }
