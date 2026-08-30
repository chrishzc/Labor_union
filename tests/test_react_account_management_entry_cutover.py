"""
File: test_react_account_management_entry_cutover.py
Description: 驗證 Account 管理 React entry、typed query 與受控 mutation boundaries。
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
ACCOUNT_ENTRY = "ui-react:#account-management"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_queue() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in REVIEW_QUEUE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_account_entry_is_unique_and_has_current_rollback_mapping() -> None:
    registry = _read_json(ENTRYPOINTS)
    retirement = _read_json(RETIREMENT_REQUIREMENTS)
    registry_entries = registry["react_entries"]
    retirement_entries = retirement["react_entries"]

    assert isinstance(registry_entries, list)
    assert isinstance(retirement_entries, list)
    assert len(registry_entries) == len(set(registry_entries)) == 15
    assert len(retirement_entries) == len(set(retirement_entries)) == 15
    assert set(registry_entries) == set(retirement_entries)
    assert registry_entries.count(ACCOUNT_ENTRY) == 1
    assert retirement_entries.count(ACCOUNT_ENTRY) == 1
    assert registry["rollback_links"][ACCOUNT_ENTRY] == "/?entry=access-management"

    queue_entries = [entry for entry in _read_queue() if entry.get("entry_id") == ACCOUNT_ENTRY]
    assert len(queue_entries) == 1
    entry = queue_entries[0]
    assert entry["status"] == "active"
    assert entry["terminal_disposition"] == "active_canonical"
    assert entry["replacement"] == ACCOUNT_ENTRY
    assert entry["replacement_readback"] == f"current canonical entry readback: {ACCOUNT_ENTRY}"
    assert entry["streamlit_entry"] == "ui:09_access_management.py"
    assert entry["rollback_deep_link"] == "/?entry=access-management"
    assert entry["witnesses"] == {
        "nav": "ui_react/src/components/MasterLayout.tsx",
        "render": "ui_react/src/App.tsx",
    }


def test_account_control_plane_keeps_react_identity_metadata() -> None:
    state = _read_json(INITIAL_TARGETS)
    entries = state["entries"]

    assert isinstance(entries, list)
    assert len(entries) == 12
    account_entries = [entry for entry in entries if entry["entry_id"] == ACCOUNT_ENTRY]
    assert len(account_entries) == 1
    assert account_entries[0]["entry_id"] == ACCOUNT_ENTRY
    assert account_entries[0]["react_target"] == "/admin/#account-management"
    assert account_entries[0]["replacement_group"] == "access"


def test_account_sources_use_typed_queries_and_account_commands() -> None:
    app_source = (ROOT / "ui_react/src/App.tsx").read_text(encoding="utf-8")
    nav_source = (ROOT / "ui_react/src/components/MasterLayout.tsx").read_text(encoding="utf-8")
    page_source = (ROOT / "ui_react/src/pages/AccountManagementPage.tsx").read_text(encoding="utf-8")

    assert re.search(
        r"\{currentPage\s*===\s*'account-management'\s*&&\s*<AccountManagementPage\s*/>\}",
        app_source,
    )
    assert re.search(
        r"\{\s*id:\s*'account-management'\s*,[^}]*section:\s*'audit'\s*\}",
        nav_source,
    )

    for control_id in (
        "account.user.create",
        "account.user.password-reset",
        "account.mfa.reset",
        "account.user.session-revoke",
        "account.audit.detail",
    ):
        assert f'data-control-id="{control_id}"' in page_source

    for method in (
        "accountCenterClient.create",
        "accountCenterClient.setEnabled",
        "accountCenterClient.resetPassword",
        "accountCenterClient.resetMfa",
        "accountCenterClient.revokeSessions",
    ):
        assert method in page_source

    client_paths = (
        "ui_react/src/api/access/account_directory_client.ts",
        "ui_react/src/api/access/audit_query_client.ts",
        "ui_react/src/api/jobs/job_observation_client.ts",
    )
    for relative_path in client_paths:
        client_source = (ROOT / relative_path).read_text(encoding="utf-8")
        methods = re.findall(r"\btransport\.(get|post|put|patch|delete)\b", client_source)
        assert methods and set(methods) == {"get"}, relative_path
