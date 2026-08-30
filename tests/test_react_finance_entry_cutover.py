"""
File: test_react_finance_entry_cutover.py
Description: 驗證Finance／Reports entry映射、rollback、control-plane缺口與GET-only邊界。
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
    assert expected[FINANCE_ENTRY]["replacement_group"] != expected[REPORTS_ENTRY]["replacement_group"]


def test_finance_control_plane_keeps_react_identity_metadata() -> None:
    state = _read_json(INITIAL_TARGETS)
    entries = state["entries"]

    assert isinstance(entries, list)
    assert len(entries) == 12
    finance_entries = [entry for entry in entries if entry["entry_id"] == FINANCE_ENTRY]
    assert len(finance_entries) == 1
    assert finance_entries[0]["react_target"] == "/admin/#finance"
    assert finance_entries[0]["replacement_group"] == "finance"


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
        assert entry["status"] == "active"
        assert entry["terminal_disposition"] == "active_canonical"
        assert entry["replacement"] == entry_id
        assert entry["streamlit_entry"] == expected_values["streamlit_entry"]
        assert entry["rollback_deep_link"] == expected_values["rollback_deep_link"]
        assert entry["witnesses"] == {
            "nav": "ui_react/src/components/MasterLayout.tsx",
            "render": "ui_react/src/App.tsx",
        }
    assert REPORTS_ENTRY != SYSTEM_STATUS_ENTRY

    state = _read_json(INITIAL_TARGETS)
    frozen = {entry["entry_id"]: entry for entry in state["entries"]}
    assert frozen[REPORTS_ENTRY]["react_target"] == "/admin/#reports"
    assert frozen[SYSTEM_STATUS_ENTRY]["react_target"] == "/admin/#system-status"

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


def test_reports_and_system_status_have_distinct_canonical_runtime_pages() -> None:
    app_source = (ROOT / "ui_react/src/App.tsx").read_text(encoding="utf-8")
    reports_source = (ROOT / "ui_react/src/pages/ReportsPage.tsx").read_text(encoding="utf-8")
    status_source = (ROOT / "ui_react/src/pages/SystemStatusPage.tsx").read_text(encoding="utf-8")
    assert "currentPage === 'reports' && <ReportsPage />" in app_source
    assert "currentPage === 'system-status' && <SystemStatusPage />" in app_source
    assert "weeklyOperationsReportQueryClient" in reports_source
    assert "fetchPerformanceSnapshot" in status_source


def test_finance_composes_typed_queries_and_bounded_import_mutation() -> None:
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
    assert "目前沒有可顯示的收款資料。" in page_source
    assert "上傳檔案 → 預覽 → 匯入完成" in page_source
    assert "mockData" not in page_source
    assert not re.search(r"\bMOCK_[A-Z0-9_]+\b", page_source)
    assert not re.search(r"\bfetch\s*\(", page_source)
    assert not re.search(r"\b(?:alert|confirm|prompt)\s*\(", page_source)

    for client_path in client_paths:
        client_source = client_path.read_text(encoding="utf-8")
        transport_methods = re.findall(
            r"\btransport\.(get|post|put|patch|delete)\b", client_source
        )
        assert transport_methods and set(transport_methods) == {"get"}, client_path
    mutation_source = (ROOT / "ui_react/src/api/finance_import/finance_import_mutation_client.ts").read_text(encoding="utf-8")
    assert "financeImportMutationClient.ingest" in page_source
    assert "financeImportMutationClient.preview" in page_source
    assert "financeImportMutationClient.apply" in page_source
    assert "financeImportMutationClient.queryBatchOutcome" in page_source
    assert "transport.post" in mutation_source
    assert "Idempotency-Key" in mutation_source
    for control_id in (
        "finance.finance-import.upload",
        "finance.finance-import.preview",
        "finance.finance-import.apply",
        "finance.finance-import.receipt",
    ):
        assert f'data-control-id="{control_id}"' in page_source
