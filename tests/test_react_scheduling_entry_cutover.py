"""
File: test_react_scheduling_entry_cutover.py
Description: 驗證 Scheduling entry 映射、Streamlit rollback、GET-only client 與 unavailable 控件。
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
SCHEDULING_ENTRY = "ui-react:#scheduling"
STAFF_ENTRY = "ui-react:#staff"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_queue() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in REVIEW_QUEUE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _disabled_button(source: str, control_id: str) -> str:
    match = re.search(
        rf'<(?:button|select)\b(?P<attrs>[^>]*data-control-id="{re.escape(control_id)}"[^>]*)>',
        source,
        re.DOTALL,
    )
    assert match is not None, control_id
    attributes = match.group("attrs")
    assert re.search(r"\bdisabled(?:\s*=\s*\{\s*true\s*\})?", attributes)
    return attributes


def test_scheduling_and_staff_registry_queue_and_rollback_mappings_are_consistent() -> None:
    registry = _read_json(ENTRYPOINTS)
    retirement = _read_json(RETIREMENT_REQUIREMENTS)
    registry_entries = registry["react_entries"]
    retirement_entries = retirement["react_entries"]

    assert isinstance(registry_entries, list)
    assert isinstance(retirement_entries, list)
    assert len(registry_entries) == len(set(registry_entries)) == 15
    assert len(retirement_entries) == len(set(retirement_entries)) == 15
    assert set(registry_entries) == set(retirement_entries)
    for entry_id in (SCHEDULING_ENTRY, STAFF_ENTRY):
        assert registry_entries.count(entry_id) == 1
        assert retirement_entries.count(entry_id) == 1

    assert registry["rollback_links"] == {
        **registry["rollback_links"],
        SCHEDULING_ENTRY: "/?entry=scheduling&view=calendar",
        STAFF_ENTRY: "/?entry=scheduling&view=staff-directory",
    }

    queue = _read_queue()
    expected = {
        SCHEDULING_ENTRY: {
            "streamlit_entry": "ui:03_calendar.py",
            "rollback_deep_link": "/?entry=scheduling&view=calendar",
        },
        STAFF_ENTRY: {
            "streamlit_entry": "ui:03_calendar.py",
            "rollback_deep_link": "/?entry=scheduling&view=staff-directory",
        },
    }
    for entry_id, expected_values in expected.items():
        entries = [entry for entry in queue if entry.get("entry_id") == entry_id]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["status"] == "review_required"
        assert entry["streamlit_entry"] == expected_values["streamlit_entry"]
        assert entry["rollback_deep_link"] == expected_values["rollback_deep_link"]
        assert entry["witnesses"] == {
            "nav": "ui_react/src/components/MasterLayout.tsx",
            "render": "ui_react/src/App.tsx",
        }
        assert all(
            entry.get(field) in (None, False)
            for field in ("active", "replacement", "cutover_ready", "cutover-ready")
            if field in entry
        )


def test_scheduling_and_staff_frozen_targets_remain_streamlit_without_receipts() -> None:
    state = _read_json(INITIAL_TARGETS)
    entries = state["entries"]

    assert isinstance(entries, list)
    assert len(entries) == 11
    expected = {
        SCHEDULING_ENTRY: {
            "entry_id": SCHEDULING_ENTRY,
            "replacement_group": "staff-scheduling",
            "current_target": "streamlit",
            "streamlit_target": "/?entry=scheduling&view=calendar",
            "react_target": "/admin/#scheduling",
            "required_react_artifact": None,
            "entry_revision": 1,
        },
        STAFF_ENTRY: {
            "entry_id": STAFF_ENTRY,
            "replacement_group": "staff-scheduling",
            "current_target": "streamlit",
            "streamlit_target": "/?entry=scheduling&view=staff-directory",
            "react_target": "/admin/#staff",
            "required_react_artifact": None,
            "entry_revision": 1,
        },
    }
    for entry_id, expected_entry in expected.items():
        assert [entry for entry in entries if entry["entry_id"] == entry_id] == [expected_entry]
    assert all(entry["current_target"] == "streamlit" for entry in entries)
    assert all(entry["required_react_artifact"] is None for entry in entries)
    assert state["receipts"] == []


def test_scheduling_sources_are_get_only_and_unavailable_controls_are_native_disabled() -> None:
    app_path = ROOT / "ui_react/src/App.tsx"
    nav_path = ROOT / "ui_react/src/components/MasterLayout.tsx"
    page_path = ROOT / "ui_react/src/pages/SchedulingPage.tsx"
    client_paths = (
        ROOT / "ui_react/src/api/staff_directory/staff_directory_client.ts",
        ROOT / "ui_react/src/api/scheduling/scheduling_current_client.ts",
    )

    app_source = app_path.read_text(encoding="utf-8")
    nav_source = nav_path.read_text(encoding="utf-8")
    page_source = page_path.read_text(encoding="utf-8")

    assert re.search(
        r"\{currentPage\s*===\s*'scheduling'\s*&&\s*<SchedulingPage\s*/>\}",
        app_source,
    )
    assert re.search(
        r"\{currentPage\s*===\s*'staff'\s*&&\s*<StaffPage\s*/>\}",
        app_source,
    )
    assert re.search(
        r"\{\s*id:\s*'scheduling'\s*,[^}]*section:\s*'operations'\s*\}",
        nav_source,
    )
    assert re.search(
        r"\{\s*id:\s*'staff'\s*,[^}]*section:\s*'operations'\s*\}",
        nav_source,
    )
    assert "'scheduling': 'operations'" in nav_source
    assert "'staff': 'operations'" in nav_source

    assert "mockData" not in page_source
    assert not re.search(r"\bMOCK_[A-Z_]+\b", page_source)
    assert not re.search(r"\bfetch\s*\(", page_source)
    assert not re.search(r"\btransport\.(post|put|patch|delete)\b", page_source)

    for client_path in client_paths:
        client_source = client_path.read_text(encoding="utf-8")
        transport_methods = re.findall(
            r"\btransport\.(get|post|put|patch|delete)\b", client_source
        )
        assert transport_methods == ["get"], client_path

    for control_id in (
        "scheduling.precision.open",
        "scheduling.projection.order-select",
        "scheduling.projection.lock",
    ):
        _disabled_button(page_source, control_id)

    assert re.search(
        r"<button\b[^>]*key=\{control\}[^>]*data-control-id=\{control\}[^>]*disabled[^>]*>",
        page_source,
        re.DOTALL,
    )
    unavailable_control_ids = (
        "scheduling.leave.substitution",
        "scheduling.leave.extension",
        "scheduling.leave.apply",
        "scheduling.holiday.create",
        "scheduling.holiday.toggle-rest",
        "scheduling.holiday.toggle-pay",
        "scheduling.holiday.delete",
        "scheduling.holiday.save",
        "scheduling.leave-inbox.accept",
        "scheduling.leave-inbox.reject",
    )
    for control_id in unavailable_control_ids:
        assert f"'{control_id}'" in page_source
