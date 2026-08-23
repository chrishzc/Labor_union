"""
File: test_react_finance_entry_cutover.py
Description: 驗證Finance／Reports entry映射、rollback、control-plane缺口與GET-only邊界。
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARENT_WP = (
    ROOT
    / "document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-cutover-finance-workspaces-work-package.md"
)
SYSTEM_STATUS_TARGET_GAP = (
    ROOT
    / "document/架構重整/02_決策與退役執行記錄/PROV-20260821-react-admin-system-status-control-plane-target-gap.md"
)
ENTRYPOINTS = ROOT / "validation/scenarios/react_admin_entrypoints.json"
RETIREMENT_REQUIREMENTS = ROOT / "validation/scenarios/react_admin_retirement_requirements.json"
INITIAL_TARGETS = ROOT / "config/admin_entry_targets.initial.json"
REVIEW_QUEUE = (
    ROOT
    / "document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl"
)
FINANCE_ENTRY = "ui-react:#finance"
REPORTS_ENTRY = "ui-react:#reports"
SYSTEM_STATUS_ENTRY = "ui-react:#system-status"


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
        rf'<button\b(?P<attrs>[^>]*data-control-id="{re.escape(control_id)}"[^>]*)>',
        source,
        re.DOTALL,
    )
    assert match is not None, control_id
    attributes = match.group("attrs")
    assert re.search(r"\bdisabled(?:\s*=\s*\{\s*true\s*\})?", attributes)
    return attributes


def test_finance_and_reports_registry_queue_and_rollback_are_separate() -> None:
    registry = _read_json(ENTRYPOINTS)
    retirement = _read_json(RETIREMENT_REQUIREMENTS)
    registry_entries = registry["react_entries"]
    retirement_entries = retirement["react_entries"]

    assert isinstance(registry_entries, list)
    assert isinstance(retirement_entries, list)
    assert len(registry_entries) == len(set(registry_entries)) == 15
    assert len(retirement_entries) == len(set(retirement_entries)) == 15
    assert set(registry_entries) == set(retirement_entries)
    for entry_id in (FINANCE_ENTRY, REPORTS_ENTRY):
        assert registry_entries.count(entry_id) == 1
        assert retirement_entries.count(entry_id) == 1

    assert registry["rollback_links"][FINANCE_ENTRY] == "/?entry=finance"
    assert registry["rollback_links"][REPORTS_ENTRY] == "/?entry=system-status&view=reports"

    queue = _read_queue()
    expected = {
        FINANCE_ENTRY: {
            "replacement_group": "finance",
            "streamlit_entry": "ui:04_finance.py",
            "rollback_deep_link": "/?entry=finance",
        },
        REPORTS_ENTRY: {
            "replacement_group": "reports-system",
            "streamlit_entry": "ui:08_system_status.py",
            "rollback_deep_link": "/?entry=system-status&view=reports",
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
    assert expected[FINANCE_ENTRY]["replacement_group"] != expected[REPORTS_ENTRY]["replacement_group"]


def test_finance_frozen_target_remains_streamlit_without_switch_receipts() -> None:
    state = _read_json(INITIAL_TARGETS)
    entries = state["entries"]

    assert isinstance(entries, list)
    assert len(entries) == 11
    assert [entry for entry in entries if entry["entry_id"] == FINANCE_ENTRY] == [
        {
            "entry_id": FINANCE_ENTRY,
            "replacement_group": "finance",
            "current_target": "streamlit",
            "streamlit_target": "/?entry=finance",
            "react_target": "/admin/#finance",
            "required_react_artifact": None,
            "entry_revision": 1,
        }
    ]
    assert all(entry["current_target"] == "streamlit" for entry in entries)
    assert all(entry["required_react_artifact"] is None for entry in entries)
    assert state["receipts"] == []


def test_reports_and_system_status_share_owner_group_but_record_control_plane_gap() -> None:
    registry = _read_json(ENTRYPOINTS)
    retirement = _read_json(RETIREMENT_REQUIREMENTS)
    registry_entries = registry["react_entries"]
    retirement_entries = retirement["react_entries"]

    for entry_id in (REPORTS_ENTRY, SYSTEM_STATUS_ENTRY):
        assert registry_entries.count(entry_id) == 1
        assert retirement_entries.count(entry_id) == 1
    assert registry["rollback_links"][REPORTS_ENTRY] == "/?entry=system-status&view=reports"
    assert registry["rollback_links"][SYSTEM_STATUS_ENTRY] == "/?entry=system-status"

    queue = _read_queue()
    expected = {
        REPORTS_ENTRY: {
            "streamlit_entry": "ui:08_system_status.py",
            "rollback_deep_link": "/?entry=system-status&view=reports",
        },
        SYSTEM_STATUS_ENTRY: {
            "streamlit_entry": "ui:08_system_status.py",
            "rollback_deep_link": "/?entry=system-status",
        },
    }
    for entry_id, expected_values in expected.items():
        matches = [entry for entry in queue if entry.get("entry_id") == entry_id]
        assert len(matches) == 1
        entry = matches[0]
        assert entry["kind"] == "ui-react"
        assert entry["replacement_group"] == "reports-system"
        assert entry["status"] == "review_required"
        assert entry["streamlit_entry"] == expected_values["streamlit_entry"]
        assert entry["rollback_deep_link"] == expected_values["rollback_deep_link"]
        assert entry["witnesses"] == {
            "nav": "ui_react/src/components/MasterLayout.tsx",
            "render": "ui_react/src/App.tsx",
        }
    assert REPORTS_ENTRY != SYSTEM_STATUS_ENTRY

    state = _read_json(INITIAL_TARGETS)
    frozen = {entry["entry_id"]: entry for entry in state["entries"]}
    assert frozen[REPORTS_ENTRY] == {
        "entry_id": REPORTS_ENTRY,
        "replacement_group": "reports-system",
        "current_target": "streamlit",
        "streamlit_target": "/?entry=system-status&view=reports",
        "react_target": "/admin/#reports",
        "required_react_artifact": None,
        "entry_revision": 1,
    }
    assert SYSTEM_STATUS_ENTRY not in frozen
    assert all(entry["current_target"] == "streamlit" for entry in state["entries"])
    assert all(entry["required_react_artifact"] is None for entry in state["entries"])
    assert state["receipts"] == []

    gap = SYSTEM_STATUS_TARGET_GAP.read_text(encoding="utf-8")
    assert "declared_status: proposed" in gap
    assert "BLOCKED_SCOPE" in gap
    assert SYSTEM_STATUS_ENTRY in gap

    app_source = (ROOT / "ui_react/src/App.tsx").read_text(encoding="utf-8")
    nav_source = (ROOT / "ui_react/src/components/MasterLayout.tsx").read_text(
        encoding="utf-8"
    )
    assert re.search(
        r"\{currentPage\s*===\s*'reports'\s*&&\s*<ReportsPage\s*/>\}",
        app_source,
    )
    assert re.search(
        r"\{currentPage\s*===\s*'system-status'\s*&&\s*<SystemStatusPage\s*/>\}",
        app_source,
    )
    assert re.search(
        r"\{\s*id:\s*'reports'\s*,[^}]*section:\s*'operations'\s*\}",
        nav_source,
    )
    assert re.search(
        r"\{\s*id:\s*'system-status'\s*,[^}]*section:\s*'audit'\s*\}",
        nav_source,
    )


def test_reports_parent_wp_keeps_weekly_authority_and_runtime_switch_blocked() -> None:
    work_package = PARENT_WP.read_text(encoding="utf-8")

    assert "declared_status: blocked" in work_package
    assert "execution_state: inventory-pass-prerequisites-blocked-runtime-not-run" in work_package
    assert "Weekly authority缺口" in work_package
    assert "generic weekly workbook" in work_package
    assert "Phase5B fresh runtime" in work_package
    assert "真TOTP Chrome" in work_package
    assert "exact switch" in work_package
    assert "不得宣稱candidate／cutover／replacement" in work_package
    assert "#reports" in work_package
    assert "不是Finance entry的一對多workspace" in work_package


def test_finance_is_a_get_only_query_slice_with_disabled_mutations() -> None:
    app_path = ROOT / "ui_react/src/App.tsx"
    nav_path = ROOT / "ui_react/src/components/MasterLayout.tsx"
    page_path = ROOT / "ui_react/src/pages/FinancePage.tsx"
    client_paths = (
        ROOT / "ui_react/src/api/orders/order_query_client.ts",
        ROOT / "ui_react/src/api/staff_directory/staff_directory_client.ts",
        ROOT / "ui_react/src/api/client_finance/client_receipt_query_client.ts",
        ROOT / "ui_react/src/api/staff_payables/staff_payables_query_client.ts",
        ROOT / "ui_react/src/api/accounts_payable/accounts_payable_query_client.ts",
        ROOT / "ui_react/src/api/finance_import/finance_import_query_client.ts",
    )

    app_source = app_path.read_text(encoding="utf-8")
    nav_source = nav_path.read_text(encoding="utf-8")
    page_source = page_path.read_text(encoding="utf-8")

    assert re.search(
        r"\{currentPage\s*===\s*'finance'\s*&&\s*<FinancePage\s*/>\}",
        app_source,
    )
    assert re.search(
        r"\{\s*id:\s*'finance'\s*,[^}]*section:\s*'finance'\s*\}",
        nav_source,
    )
    assert re.search(
        r"\{\s*id:\s*'reports'\s*,[^}]*section:\s*'operations'\s*\}",
        nav_source,
    )
    assert "'finance': 'finance'" in nav_source
    assert "'reports': 'operations'" in nav_source

    for tab in ("client-receipts", "staff-payables", "accounts-payable", "finance-import"):
        assert tab in page_source
    assert "StateMessage" in page_source
    assert "目前沒有可查詢的公開批次 identity。" in page_source
    assert "請先選擇具 identity" in page_source
    assert "mockData" not in page_source
    assert not re.search(r"\bMOCK_[A-Z0-9_]+\b", page_source)
    assert not re.search(r"\bfetch\s*\(", page_source)
    assert not re.search(r"\btransport\.(post|put|patch|delete)\b", page_source)
    assert not re.search(r"\b(?:alert|confirm|prompt)\s*\(", page_source)

    for client_path in client_paths:
        client_source = client_path.read_text(encoding="utf-8")
        transport_methods = re.findall(
            r"\btransport\.(get|post|put|patch|delete)\b", client_source
        )
        assert transport_methods and set(transport_methods) == {"get"}, client_path

    for control_id in ("finance.refund.approve", "finance.subsidy.advance"):
        assert f"['{control_id}'," in page_source
    assert re.search(
        r"disabledActions\.map\(\(\[id,\s*label\]\)\s*=>\s*<button[^>]*data-control-id=\{id\}[^>]*disabled",
        page_source,
    )

    for control_id in (
        "finance.accounts-payable.export-xlsx",
        "finance.client-receipt.settle",
        "finance.staff-payable.adjustment",
        "finance.staff-payable.mark-paid",
        "finance.finance-import.upload",
        "finance.finance-import.preview",
        "finance.finance-import.apply",
        "finance.finance-import.reprocess",
    ):
        _disabled_button(page_source, control_id)
