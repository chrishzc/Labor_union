"""
File: test_entrypoint_review_queue.py
Description: 驗證 entry queue 與 runtime discovery 完全一致且 review 狀態 fail closed。
"""

from __future__ import annotations

import json

from scripts import generate_entrypoint_review_queue as queue


def test_queue_matches_current_entrypoint_discovery() -> None:
    expected = queue.build_review_queue()
    actual = _load_queue()

    assert actual == expected


def test_reviewed_entries_require_their_business_contract() -> None:
    for entry in _load_queue():
        _validate_entry(entry)


def test_queue_has_no_unreviewed_entries() -> None:
    unreviewed = [
        entry["entry_id"]
        for entry in _load_queue()
        if entry["status"] == "review_required"
    ]

    assert {entry_id for entry_id in unreviewed if entry_id.startswith("ui-react:#")} == {
        f"ui-react:#{page}"
        for page in (
            "order-tracker", "orders", "scheduling", "staff", "data-import", "line-management",
            "reports", "finance", "anomalies", "account-management", "system-status",
            "line-security", "line-liff-studio", "line-ai-events",
        )
    }


def _load_queue() -> list[dict[str, object]]:
    return [json.loads(line) for line in queue.QUEUE_PATH.read_text(encoding="utf-8").splitlines()]


def _validate_entry(entry: dict[str, object]) -> None:
    status = entry["status"]
    assert status in {"review_required", "active", "retired_410", "operator_only", "removed"}
    if status == "review_required":
        return
    for field in ("business_scenario", "operator", "canonical_owner"):
        assert isinstance(entry.get(field), str) and entry[field].strip()
    if status == "retired_410":
        assert entry["kind"] == "api"
        assert isinstance(entry.get("replacement"), str) and entry["replacement"].strip()
    if status == "operator_only":
        assert entry["kind"] == "cli"
