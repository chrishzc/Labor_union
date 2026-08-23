"""
File: test_react_orders_entry_cutover.py
Description: 驗證 Orders entry 治理映射、八個 GET allowlist 與 Phase2B conditional 邊界。
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = ROOT / "validation/scenarios/react_admin_entrypoints.json"
RETIREMENT_REQUIREMENTS = ROOT / "validation/scenarios/react_admin_retirement_requirements.json"
INITIAL_TARGETS = ROOT / "config/admin_entry_targets.initial.json"
REVIEW_QUEUE = (
    ROOT
    / "document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl"
)
ORDERS_ENTRY = "ui-react:#orders"
ORDER_TRACKER_ENTRY = "ui-react:#order-tracker"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_queue() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in REVIEW_QUEUE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_orders_and_order_tracker_registry_queue_and_rollback_are_separate() -> None:
    registry = _read_json(ENTRYPOINTS)
    retirement = _read_json(RETIREMENT_REQUIREMENTS)
    registry_entries = registry["react_entries"]
    retirement_entries = retirement["react_entries"]

    assert isinstance(registry_entries, list)
    assert isinstance(retirement_entries, list)
    assert len(registry_entries) == len(set(registry_entries)) == 15
    assert len(retirement_entries) == len(set(retirement_entries)) == 15
    assert set(registry_entries) == set(retirement_entries)
    for entry_id in (ORDERS_ENTRY, ORDER_TRACKER_ENTRY):
        assert registry_entries.count(entry_id) == 1
        assert retirement_entries.count(entry_id) == 1

    assert registry["rollback_links"][ORDERS_ENTRY] == "/?entry=orders"
    assert registry["rollback_links"][ORDER_TRACKER_ENTRY] == (
        "/?entry=form-management&view=order-tracker"
    )

    queue = _read_queue()
    expected = {
        ORDERS_ENTRY: {
            "replacement_group": "orders",
            "streamlit_entry": "ui:02_orders.py",
            "rollback_deep_link": "/?entry=orders",
        },
        ORDER_TRACKER_ENTRY: {
            "replacement_group": "order-workbench",
            "streamlit_entry": "ui:05_form_management.py",
            "rollback_deep_link": "/?entry=form-management&view=order-tracker",
        },
    }
    for entry_id, expected_values in expected.items():
        matches = [entry for entry in queue if entry.get("entry_id") == entry_id]
        assert len(matches) == 1
        entry = matches[0]
        assert entry["kind"] == "ui-react"
        assert entry["replacement_group"] == expected_values["replacement_group"]
        assert entry["status"] == "review_required"
        assert entry["streamlit_entry"] == expected_values["streamlit_entry"]
        assert entry["rollback_deep_link"] == expected_values["rollback_deep_link"]
        assert entry["source_path"] == "ui_react/src/components/MasterLayout.tsx"
        assert entry["witnesses"] == {
            "nav": "ui_react/src/components/MasterLayout.tsx",
            "render": "ui_react/src/App.tsx",
        }
        assert all(
            entry.get(field) in (None, False)
            for field in ("active", "replacement", "cutover_ready", "cutover-ready")
            if field in entry
        )
    assert expected[ORDERS_ENTRY]["replacement_group"] != expected[ORDER_TRACKER_ENTRY]["replacement_group"]


def test_orders_and_order_tracker_frozen_targets_remain_streamlit_without_receipts() -> None:
    state = _read_json(INITIAL_TARGETS)
    entries = state["entries"]

    assert isinstance(entries, list)
    assert len(entries) == 11
    expected = {
        ORDERS_ENTRY: {
            "entry_id": ORDERS_ENTRY,
            "replacement_group": "orders",
            "current_target": "streamlit",
            "streamlit_target": "/?entry=orders",
            "react_target": "/admin/#orders",
            "required_react_artifact": None,
            "entry_revision": 1,
        },
        ORDER_TRACKER_ENTRY: {
            "entry_id": ORDER_TRACKER_ENTRY,
            "replacement_group": "order-workbench",
            "current_target": "streamlit",
            "streamlit_target": "/?entry=form-management&view=order-tracker",
            "react_target": "/admin/#order-tracker",
            "required_react_artifact": None,
            "entry_revision": 1,
        },
    }
    for entry_id, expected_entry in expected.items():
        assert [entry for entry in entries if entry["entry_id"] == entry_id] == [
            expected_entry
        ]
    assert all(entry["current_target"] == "streamlit" for entry in entries)
    assert all(entry["required_react_artifact"] is None for entry in entries)
    assert state["receipts"] == []


def test_orders_is_an_eight_get_query_candidate_and_phase2b_is_conditional() -> None:
    app_source = (ROOT / "ui_react/src/App.tsx").read_text(encoding="utf-8")
    nav_source = (ROOT / "ui_react/src/components/MasterLayout.tsx").read_text(
        encoding="utf-8"
    )
    page_source = (ROOT / "ui_react/src/pages/OrdersPage.tsx").read_text(
        encoding="utf-8"
    )
    client_source = (
        ROOT / "ui_react/src/api/orders/order_query_client.ts"
    ).read_text(encoding="utf-8")

    assert re.search(
        r"\{currentPage\s*===\s*'orders'\s*&&\s*<OrdersPage\s*/>\}",
        app_source,
    )
    assert re.search(
        r"\{currentPage\s*===\s*'order-tracker'\s*&&\s*<OrderTrackerPage\s*/>\}",
        app_source,
    )
    assert re.search(
        r"\{\s*id:\s*'orders'\s*,[^}]*section:\s*'operations'\s*\}",
        nav_source,
    )
    assert re.search(
        r"\{\s*id:\s*'order-tracker'\s*,[^}]*section:\s*'operations'\s*\}",
        nav_source,
    )
    assert "'orders': 'operations'" in nav_source
    assert "'order-tracker': 'operations'" in nav_source

    expected_get_routes = (
        "'/api/v1/orders/summaries'",
        "`/api/v1/orders/${encodeURIComponent(validCaseNo)}`",
        "`/api/v1/orders/${encodeURIComponent(validCaseNo)}/calendar-detail`",
        "`/api/v1/orders/${encodeURIComponent(validCaseNo)}/terms`",
        "`/api/v1/orders/${encodeURIComponent(validCaseNo)}/form-management-context`",
        "`/api/v1/orders/${encodeURIComponent(validCaseNo)}/actual-start`",
        "`/api/v1/orders/${encodeURIComponent(validCaseNo)}/contract-completion`",
        "`/api/v1/orders/${encodeURIComponent(validCaseNo)}/assignment-plan`",
    )
    for route in expected_get_routes:
        assert route in client_source
    assert client_source.count("/api/v1/orders/") == 9
    assert "decodePayload" in client_source
    assert "transport.get" in client_source
    assert not re.search(r"\btransport\.(post|put|patch|delete)\b", client_source)
    assert not re.search(r"\bfetch\s*\(", client_source)

    assert "ordersQueryClient.getOrderSummaries" in page_source
    assert "FormManagementPage" not in page_source
    assert "mockData" not in page_source
    assert not re.search(r"\bMOCK_[A-Z0-9_]+\b", page_source)
    assert not re.search(r"\bfetch\s*\(", page_source)
    assert not re.search(r"\b(?:alert|confirm|prompt)\s*\(", page_source)
    assert "ORDERS_TYPED_PROJECTION_UNAVAILABLE" in page_source
    assert "後端尚未提供 typed 七階段投影" in page_source
    assert "disabled={!isLoadedScope}" in page_source

    for method in (
        "getOrderSummaries",
        "getOrderDetail",
        "getOrderCalendarDetail",
        "getOrderTerms",
        "getFormManagementContext",
        "getActualStart",
        "getContractCompletion",
        "getAssignmentPlan",
    ):
        assert method in client_source

    # These controls are intentionally conditional Phase2B scope, not this GET subgate.
    for control_id in (
        "orders.card.reopen",
        "orders.date.service-date-select",
        "orders.date.service-date-preview",
        "orders.date.service-date-apply",
        "orders.reopen.reason",
        "orders.reopen.apply",
    ):
        assert f'data-control-id="{control_id}"' in page_source
    for phase2b_flow in (
        "previewServiceDatesFlow",
        "applyServiceDatesFlow",
        "previewReopenFlow",
        "applyReopenFlow",
    ):
        assert phase2b_flow in page_source
    assert "order_mutation_adapter" in page_source
    assert "確認服務日期" in page_source
    assert "重啟訂單" in page_source

    # Query-only unavailable/side-effect slots remain visibly fail-closed.
    assert "disabled={true}" in page_source
    assert "查詢模式不支援手動發送" in page_source
    assert "orders.matching.assignment-plan-unavailable" in page_source
