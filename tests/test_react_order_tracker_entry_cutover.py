"""
File: test_react_order_tracker_entry_cutover.py
Description: 驗證 Order Tracker entry 的治理映射、GET-only 查詢與非完整 Form Management 邊界。
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
ORDER_TRACKER_ENTRY = "ui-react:#order-tracker"
ORDERS_ENTRY = "ui-react:#orders"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_queue() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in REVIEW_QUEUE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_order_tracker_and_orders_have_distinct_registry_queue_rollbacks() -> None:
    registry = _read_json(ENTRYPOINTS)
    retirement = _read_json(RETIREMENT_REQUIREMENTS)
    registry_entries = registry["react_entries"]
    retirement_entries = retirement["react_entries"]

    assert isinstance(registry_entries, list)
    assert isinstance(retirement_entries, list)
    assert len(registry_entries) == len(set(registry_entries)) == 15
    assert len(retirement_entries) == len(set(retirement_entries)) == 15
    assert set(registry_entries) == set(retirement_entries)
    for entry_id in (ORDER_TRACKER_ENTRY, ORDERS_ENTRY):
        assert registry_entries.count(entry_id) == 1
        assert retirement_entries.count(entry_id) == 1

    assert registry["rollback_links"][ORDER_TRACKER_ENTRY] == (
        "/?entry=form-management&view=order-tracker"
    )
    assert registry["rollback_links"][ORDERS_ENTRY] == "/?entry=orders"

    queue = _read_queue()
    expected = {
        ORDER_TRACKER_ENTRY: {
            "replacement_group": "order-workbench",
            "streamlit_entry": "ui:05_form_management.py",
            "rollback_deep_link": "/?entry=form-management&view=order-tracker",
        },
        ORDERS_ENTRY: {
            "replacement_group": "orders",
            "streamlit_entry": "ui:02_orders.py",
            "rollback_deep_link": "/?entry=orders",
        },
    }
    for entry_id, expected_values in expected.items():
        matches = [entry for entry in queue if entry.get("entry_id") == entry_id]
        assert len(matches) == 1
        entry = matches[0]
        assert entry["kind"] == "ui-react"
        assert entry["replacement_group"] == expected_values["replacement_group"]
        assert entry["status"] == "active"
        assert entry["terminal_disposition"] == "active_canonical"
        assert entry["replacement"] == entry_id
        assert entry["streamlit_entry"] == expected_values["streamlit_entry"]
        assert entry["rollback_deep_link"] == expected_values["rollback_deep_link"]
        assert entry["source_path"] == "ui_react/src/components/MasterLayout.tsx"
        assert entry["witnesses"] == {
            "nav": "ui_react/src/components/MasterLayout.tsx",
            "render": "ui_react/src/App.tsx",
        }
        assert entry["replacement_readback"] == f"current canonical entry readback: {entry_id}"
    assert expected[ORDER_TRACKER_ENTRY]["replacement_group"] != expected[ORDERS_ENTRY]["replacement_group"]


def test_order_tracker_and_orders_control_plane_keep_react_identity_metadata() -> None:
    state = _read_json(INITIAL_TARGETS)
    entries = state["entries"]

    assert isinstance(entries, list)
    assert len(entries) == 12
    for entry_id, target in ((ORDER_TRACKER_ENTRY, "/admin/#order-tracker"), (ORDERS_ENTRY, "/admin/#orders")):
        matches = [entry for entry in entries if entry["entry_id"] == entry_id]
        assert len(matches) == 1
        assert matches[0]["react_target"] == target


def test_order_tracker_is_a_get_only_query_slice_not_full_form_management() -> None:
    app_source = (ROOT / "ui_react/src/App.tsx").read_text(encoding="utf-8")
    nav_source = (ROOT / "ui_react/src/components/MasterLayout.tsx").read_text(
        encoding="utf-8"
    )
    page_source = (ROOT / "ui_react/src/pages/OrderTrackerPage.tsx").read_text(
        encoding="utf-8"
    )
    adapter_source = (
        ROOT / "ui_react/src/adapters/orders/order_tracker_adapter.ts"
    ).read_text(encoding="utf-8")
    client_source = (ROOT / "ui_react/src/api/orders/order_query_client.ts").read_text(
        encoding="utf-8"
    )

    assert re.search(
        r"\{currentPage\s*===\s*'order-tracker'\s*&&\s*<OrderTrackerPage\s*/>\}",
        app_source,
    )
    assert re.search(
        r"\{currentPage\s*===\s*'orders'\s*&&\s*<OrdersPage\s*/>\}",
        app_source,
    )
    assert re.search(
        r"\{\s*id:\s*'order-tracker'\s*,[^}]*section:\s*'operations'\s*\}",
        nav_source,
    )
    assert re.search(
        r"\{\s*id:\s*'orders'\s*,[^}]*section:\s*'operations'\s*\}",
        nav_source,
    )
    assert "'order-tracker': 'operations'" in nav_source
    assert "'orders': 'operations'" in nav_source

    assert "ordersQueryClient.getOrderSummaries" in page_source
    assert "adaptOrderTrackerPage" in page_source
    assert "FormManagementPage" not in page_source
    assert "form-management" not in page_source
    assert not re.search(r"\bfetch\s*\(", page_source)
    assert not re.search(r"\btransport\.(post|put|patch|delete)\b", page_source)
    assert not re.search(r"\b(?:alert|confirm|prompt)\s*\(", page_source)
    assert "mockData" not in page_source
    assert not re.search(r"\bMOCK_[A-Z0-9_]+\b", page_source)
    assert "TRACKER_STAGE_PROJECTION_UNAVAILABLE" in adapter_source
    assert "TRACKER_ROOT_FACT_LINEAGE_UNAVAILABLE" in adapter_source
    assert "TRACKER_NOTIFICATION_TIMELINE_UNAVAILABLE" in adapter_source
    assert "TRACKER_TYPED_PROJECTION_UNAVAILABLE" in adapter_source
    assert "order-tracker.notifications.replay" not in page_source

    transport_methods = re.findall(
        r"\btransport\.(get|post|put|patch|delete)\b", client_source
    )
    assert transport_methods == ["get"]
    assert "order_mutation_client" not in page_source
    assert "ordersMutationClient" not in page_source
