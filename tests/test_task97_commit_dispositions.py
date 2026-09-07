"""Focused contract checks for the Task 97 commit disposition artifact."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile

from shared_kernel.writer_inventory import scan_production_writers

from scripts.generate_task97_commit_dispositions import (
    APPLICATION_OWNED_COMMIT_SYMBOLS,
    CommitLocation,
    EVIDENCE_PATH,
    MEDIA_STAGING_VIOLATIONS,
    READ_ONLY_APPLICATIONS,
    REPOSITORY_ROOT,
    REVIEWED_COMMIT_BOUNDARIES,
    SOURCE_REVISION_INPUTS,
    UNRESOLVED_REVIEWED_COMMIT_BOUNDARIES,
    _classify,
    _git_revision,
    _semantic_owner,
    build_artifact,
)


REQUIRED_ENTRY_FIELDS = {
    "identity",
    "source_path",
    "symbol",
    "line",
    "method",
    "fingerprint",
    "owner",
    "layer",
    "classification",
    "analysis_basis",
    "replacement_or_remediation",
    "blocker",
    "zero_reference_oracle",
    "terminal_receipt",
}


def test_task97_commit_dispositions_cover_fresh_scan_and_preserve_exact_semantics() -> None:
    artifact = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    rebuilt = build_artifact()

    assert artifact == rebuilt
    entries = artifact["entries"]
    assert artifact["candidate_count"] == len(entries) == artifact["unique_identity_count"]
    assert all(set(entry) == REQUIRED_ENTRY_FIELDS for entry in entries)
    assert all(entry["method"] == "commit" for entry in entries)
    assert all(entry["source_path"] in entry["identity"] for entry in entries)
    assert set(artifact["classification_counts"]) <= {
        "real_violation",
        "application_owned_legitimate_outer_uow",
        "false_positive_non_transaction",
    }
    assert artifact["classification_counts"]["application_owned_legitimate_outer_uow"] > 0
    violation_count = artifact["classification_counts"].get("real_violation", 0)
    assert artifact["terminal_status"] == ("blocked" if violation_count else "passed")
    assert artifact["terminal_blocker"] == (
        f"{violation_count} exact commit identities remain classified as real violations."
        if violation_count
        else None
    )
    assert all(
        entry["terminal_receipt"].startswith(
            "TASK97-COMMIT-DISPOSITION "
            + ("blocked;" if entry["classification"] == "real_violation" else "accepted;")
        )
        for entry in entries
    )

    by_location = {(entry["source_path"], entry["line"]): entry for entry in entries}
    for location in MEDIA_STAGING_VIOLATIONS:
        if location in by_location:
            assert by_location[location]["classification"] == "real_violation"
            assert "schema" in by_location[location]["blocker"]

    for path, symbol in READ_ONLY_APPLICATIONS:
        matches = [entry for entry in entries if entry["source_path"] == path and entry["symbol"] == symbol]
        assert not matches

    frozen = [entry for entry in entries if entry["source_path"] == "scripts/generate_fake_data.py"]
    assert not frozen


def test_task97_commit_dispositions_do_not_blanket_classify_by_path() -> None:
    artifact = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    entries = artifact["entries"]

    infra_uow = next(
        entry for entry in entries
        if entry["source_path"] == "infrastructure/mysql/unit_of_work.py"
    )
    assert infra_uow["classification"] == "application_owned_legitimate_outer_uow"
    workflow = next(
        entry for entry in entries
        if entry["source_path"] == "subsystems/orders/actual_start_workflow.py"
    )
    assert workflow["classification"] == "application_owned_legitimate_outer_uow"

    remediated_paths = {
        "infrastructure/mysql/knowledge_retrieval_repository.py",
        "infrastructure/mysql/government_subsidy_anomaly_source.py",
        "infrastructure/mysql/line_notification_reconciliation_worker.py",
        "api/dependencies/runtime_heartbeat.py",
    }
    assert not [entry for entry in entries if entry["source_path"] in remediated_paths]

    by_symbol = {(entry["source_path"], entry["symbol"]): entry for entry in entries}
    for identity in APPLICATION_OWNED_COMMIT_SYMBOLS:
        assert by_symbol[identity]["classification"] == "application_owned_legitimate_outer_uow"


def test_task97_audited_commit_boundaries_follow_exact_current_decisions() -> None:
    artifact = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    by_identity = {str(entry["identity"]): entry for entry in artifact["entries"]}

    for identity, review in REVIEWED_COMMIT_BOUNDARIES.items():
        owner, layer, _basis, _remediation, _blocker = review
        entry = by_identity.get(identity)
        assert entry is not None, identity
        assert entry["owner"] == owner
        assert entry["layer"] == layer
        unresolved = UNRESOLVED_REVIEWED_COMMIT_BOUNDARIES.get(identity)
        if unresolved is None:
            assert entry["classification"] == "application_owned_legitimate_outer_uow"
        else:
            basis, remediation, blocker = unresolved
            assert entry["classification"] == "real_violation"
            assert entry["analysis_basis"] == basis
            assert entry["replacement_or_remediation"] == remediation
            assert entry["blocker"] == blocker


def test_task97_reviewed_commit_boundaries_do_not_inherit_to_sibling_commits() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "api" / "dependencies" / "admin_auth.py"
        source.parent.mkdir(parents=True)
        source.write_text(
            "def ensure_development_root_admin(conn):\n"
            "    conn.commit()\n"
            "    conn.commit()\n"
            "\n"
            "def sibling_symbol(conn):\n"
            "    conn.commit()\n",
            encoding="utf-8",
        )
        findings = scan_production_writers(root, ("api",))

    reviewed = next(
        finding for finding in findings
        if finding.symbol == "ensure_development_root_admin" and finding.occurrence == 1
    )
    sibling_occurrence = next(
        finding for finding in findings
        if finding.symbol == "ensure_development_root_admin" and finding.occurrence == 2
    )
    sibling_symbol = next(
        finding for finding in findings
        if finding.symbol == "sibling_symbol"
    )
    location = CommitLocation(
        line=1,
        receiver="conn",
        has_uow_context=False,
        has_connection_lifecycle=False,
        has_worker_signal=False,
    )

    assert reviewed.identity in REVIEWED_COMMIT_BOUNDARIES
    assert reviewed.identity not in UNRESOLVED_REVIEWED_COMMIT_BOUNDARIES
    assert sibling_occurrence.identity not in REVIEWED_COMMIT_BOUNDARIES
    assert sibling_symbol.identity not in REVIEWED_COMMIT_BOUNDARIES
    exact_result = _classify(reviewed, location)
    sibling_occurrence_result = _classify(sibling_occurrence, location)
    sibling_symbol_result = _classify(sibling_symbol, location)
    assert exact_result[0] == "application_owned_legitimate_outer_uow"
    assert sibling_occurrence_result[0] == "real_violation"
    assert sibling_symbol_result[0] == "real_violation"
    assert sibling_occurrence_result[3] != exact_result[3]
    assert sibling_symbol_result[3] != exact_result[3]
    assert _semantic_owner(reviewed) == ("access_control", "adapter")
    assert _semantic_owner(sibling_occurrence) == ("global_operations", "adapter")
    assert _semantic_owner(sibling_symbol) == ("global_operations", "adapter")

def test_task97_commit_disposition_source_revision_is_input_bound_and_idempotent() -> None:
    expected = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", *SOURCE_REVISION_INPUTS],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    first = build_artifact()
    second = build_artifact()

    assert first == second
    assert first["source_revision"] == expected == _git_revision()
    assert all(
        entry["terminal_receipt"].endswith(f"source_revision={expected}")
        for entry in first["entries"]
    )
