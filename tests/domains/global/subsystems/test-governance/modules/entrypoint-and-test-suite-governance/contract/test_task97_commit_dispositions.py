"""Focused contract checks for the Task 97 commit disposition artifact."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import subprocess

from scripts.generate_task97_commit_dispositions import (
    APPLICATION_OWNED_COMMIT_SYMBOLS,
    EVIDENCE_PATH,
    MEDIA_STAGING_VIOLATIONS,
    READ_ONLY_APPLICATIONS,
    REPOSITORY_ROOT,
    SOURCE_REVISION_INPUTS,
    _git_revision,
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


def test_task97_commit_disposition_source_revision_is_input_bound_and_idempotent() -> None:
    tracked_inputs = subprocess.run(
        ["git", "ls-files", "--stage", "--", *SOURCE_REVISION_INPUTS],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    expected = sha256(tracked_inputs.encode("utf-8")).hexdigest()

    first = build_artifact()
    second = build_artifact()

    assert first == second
    assert first["source_revision"] == expected == _git_revision()
    assert all(
        entry["terminal_receipt"].endswith(f"source_revision={expected}")
        for entry in first["entries"]
    )
