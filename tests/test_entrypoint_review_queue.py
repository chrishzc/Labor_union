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

    assert not [entry_id for entry_id in unreviewed if entry_id.startswith("ui-react:#")]


def test_governed_entries_have_exact_task97_terminal_receipts() -> None:
    required = {
        "runtime_registration",
        "current_inbound_callers",
        "external_operator_evidence",
        "canonical_owner",
        "replacement_path_or_symbol",
        "replacement_readback",
        "deletion_410_gate",
        "focused_regression",
        "final_zero_reference_oracle",
        "terminal_disposition",
        "terminal_receipt",
    }
    terminal = {
        "active_canonical",
        "rewrite_to_canonical",
        "retired_410",
        "delete",
        "operator_only_guarded",
        "blocked_external_evidence",
    }
    for entry in _load_queue():
        if entry["status"] == "review_required":
            continue
        assert required <= entry.keys(), entry["entry_id"]
        assert entry["terminal_disposition"] in terminal
        assert all(str(entry[field]).strip() for field in required)


def test_queue_has_no_generic_owner_placeholder() -> None:
    assert not [
        entry["entry_id"]
        for entry in _load_queue()
        if entry.get("canonical_owner") == "owning bounded domain"
    ]


def test_task97_local_canonical_http_promotions_are_exact_identity_locked() -> None:
    entries = {entry["entry_id"]: entry for entry in _load_queue()}
    canonical_entries = (
        queue.SOURCE_LOCAL_CANONICAL_HTTP_ENTRIES
        - set(queue.SOURCE_RETIRED_HTTP_ENTRIES)
    )

    assert len(queue.SOURCE_LOCAL_CANONICAL_HTTP_ENTRIES) == 104
    assert len(canonical_entries) == 103
    for identity in canonical_entries:
        entry = entries[identity]
        assert entry["status"] == "active"
        assert entry["terminal_disposition"] == "active_canonical"
        assert entry["replacement_path_or_symbol"] == identity
        assert entry["deletion_410_gate"] == "not_applicable_active_canonical"
        assert entry["final_zero_reference_oracle"] == "not_applicable_active_canonical"
        assert "repository-local typed caller" in entry["current_inbound_callers"]
        assert "production deployment or external usage is not claimed" in entry["external_operator_evidence"]


def test_task97_controlled_file_entries_are_exact_active_canonical() -> None:
    entries = {entry["entry_id"]: entry for entry in queue.build_review_queue()}

    assert len(queue.SOURCE_CONTROLLED_FILE_HTTP_ENTRIES) == 7
    for identity in queue.SOURCE_CONTROLLED_FILE_HTTP_ENTRIES:
        entry = entries[identity]
        assert entry["status"] == "active"
        assert entry["terminal_disposition"] == "active_canonical"
        assert entry["deletion_410_gate"] == "not_applicable_active_canonical"
        assert entry["replacement_path_or_symbol"] == identity
        assert entry["final_zero_reference_oracle"] == "not_applicable_active_canonical"
        assert "repository-local typed caller" in entry["current_inbound_callers"]
        assert "production deployment or external usage is not claimed" in entry["external_operator_evidence"]


def test_historical_client_payment_entries_are_repository_local_canonical() -> None:
    entries = {entry["entry_id"]: entry for entry in queue.build_review_queue()}
    identities = {
        "api:GET /api/v1/client-payments/historical-payments/{case_no}",
        "api:GET /api/v1/client-payments/historical-payments/{case_no}/readback",
        "api:POST /api/v1/client-payments/historical-payments/apply",
        "api:POST /api/v1/client-payments/historical-payments/preview",
    }

    for identity in identities:
        entry = entries[identity]
        assert entry["status"] == "active"
        assert entry["terminal_disposition"] == "active_canonical"
        assert entry["canonical_owner"] == "Client Finance"
        assert "historical_client_payment_client.ts" in entry["current_inbound_callers"]
        assert "test_historical_client_payment_api.py" in entry["focused_regression"]


def test_task97_anomaly_dead_letter_entries_are_exact_retired_410() -> None:
    entries = {entry["entry_id"]: entry for entry in queue.build_review_queue()}

    assert len(queue.SOURCE_ANOMALY_REWRITE_HTTP_ENTRIES) == 5
    for identity in queue.SOURCE_ANOMALY_REWRITE_HTTP_ENTRIES:
        entry = entries[identity]
        assert entry["status"] == "retired_410"
        assert entry["terminal_disposition"] == "retired_410"
        assert "durable-job" in entry["replacement_path_or_symbol"]


def test_repository_local_typed_410_entries_are_not_marked_active() -> None:
    entries = {entry["entry_id"]: entry for entry in queue.build_review_queue()}

    assert len(queue.SOURCE_REPOSITORY_LOCAL_TYPED_410_ENTRIES) == 26
    for identity in queue.SOURCE_REPOSITORY_LOCAL_TYPED_410_ENTRIES:
        entry = entries[identity]
        assert entry["status"] == "retired_410"
        assert entry["terminal_disposition"] == "retired_410"
        assert entry["replacement_path_or_symbol"] != identity
        assert entry["deletion_410_gate"].startswith("blocked_external_evidence")


def test_task97_remaining_api_blockers_are_exact_identity_locked() -> None:
    entries = _load_queue()
    review_api = {
        entry["entry_id"]: entry
        for entry in entries
        if entry["status"] == "review_required" and entry["kind"] == "api"
    }

    assert len(queue.SOURCE_EXTERNAL_EVIDENCE_HTTP_ENTRIES) == 59
    assert set(review_api) == (
        queue.SOURCE_EXTERNAL_EVIDENCE_HTTP_ENTRIES
        | queue.SOURCE_OWNER_COMMAND_REWRITE_HTTP_ENTRIES
    )
    for identity in queue.SOURCE_OWNER_COMMAND_REWRITE_HTTP_ENTRIES:
        assert review_api[identity]["terminal_disposition"] == "rewrite_to_canonical"
        assert "owning typed BeClass command" in review_api[identity]["replacement_path_or_symbol"]
        assert review_api[identity]["deletion_410_gate"] == "blocked_owner_command_contract"
    for identity in queue.SOURCE_EXTERNAL_EVIDENCE_HTTP_ENTRIES:
        assert review_api[identity]["terminal_disposition"] == "blocked_external_evidence"


def test_task97_review_queue_current_terminal_counts() -> None:
    entries = _load_queue()

    assert sum(entry["status"] == "active" for entry in entries) == 500
    assert sum(entry["status"] == "retired_410" for entry in entries) == 79
    assert sum(entry["status"] == "review_required" for entry in entries) == 69
    assert sum(entry["status"] == "operator_only" for entry in entries) == 75


def test_local_mysql_forward_is_owned_by_the_exact_local_bridge_launcher() -> None:
    entries = {entry["entry_id"]: entry for entry in _load_queue()}
    forward = entries["cli:scripts/launchers/local_mysql_tcp_forward.py"]

    assert forward["status"] == "operator_only"
    assert forward["terminal_disposition"] == "operator_only_guarded"
    assert "manage_gcp_cloud_run_db_bridge.ps1" in forward["caller_evidence"]
    assert "127.0.0.1" in forward["caller_evidence"]


def test_read_only_governance_validators_have_formal_operator_callers() -> None:
    entries = {entry["entry_id"]: entry for entry in _load_queue()}
    expected = {
        "cli:scripts/validate_agent_governance.py": "00_Agent任務分級與交付規範.md",
        "cli:scripts/validate_streamlit_retirement_readiness.py": "Phase 6A",
    }

    for identity, caller_marker in expected.items():
        entry = entries[identity]
        assert entry["status"] == "operator_only"
        assert entry["terminal_disposition"] == "operator_only_guarded"
        assert caller_marker in entry["caller_evidence"]


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
