import json
from hashlib import sha256
import subprocess
import sys
from pathlib import Path

from scripts.reconcile_writer_inventory_v3_dispositions import (
    EXACT_IDENTITY_REVIEWS,
    EXACT_SOURCE_RESTRICTED_REVIEWS,
    EXACT_SOURCE_REVIEWS,
    _task97_exact_review,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIRECTORY = (
    REPOSITORY_ROOT
    / "document"
    / "架構重整"
    / "03_追蹤清單與證據"
    / "evidence"
    / "writer_inventory_v3"
)
DISPOSITION_MANIFEST = EVIDENCE_DIRECTORY / "writer_inventory_v3_disposition.manifest.json"


def test_writer_inventory_v3_disposition_validator_accepts_full_coverage():
    candidate_identities = _identities("writer_inventory_v3_candidate.findings.jsonl")
    reviewed_identities = _identities("writer_inventory_v3_disposition.records.jsonl")
    manifest = json.loads(DISPOSITION_MANIFEST.read_text(encoding="utf-8"))
    result = subprocess.run(
        [sys.executable, "scripts/validate_writer_inventory_v3_dispositions.py"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert candidate_identities == reviewed_identities
    assert f"records={manifest['record_count']}" in result.stdout


def test_task97_production_writer_gate_uses_current_v3_artifacts():
    checker = (
        REPOSITORY_ROOT / "scripts" / "check_production_writers.py"
    ).read_text(encoding="utf-8")

    assert "production_writer_inventory.v1.json" not in checker
    assert "writer_inventory_v3_candidate.manifest.json" in checker
    assert "writer_inventory_v3_disposition.records.jsonl" in checker
    assert "scan_production_writers" in checker
    assert "validate_dispositions" in checker


def test_writer_inventory_v3_candidate_scans_services():
    from scripts.generate_writer_inventory_v3_candidate import ROOTS

    assert "services" in ROOTS


def test_task97_exact_commit_receipts_preserve_per_identity_decisions():
    records = {
        record["identity"]: record
        for record in _records("writer_inventory_v3_disposition.records.jsonl")
    }
    commit_receipt = json.loads(
        (EVIDENCE_DIRECTORY.parent / "task97_repository_commit_dispositions_v1.json").read_text(encoding="utf-8")
    )
    entries = commit_receipt["entries"]
    assert entries
    violations = [entry for entry in entries if entry["classification"] == "real_violation"]
    assert commit_receipt["terminal_status"] == ("blocked" if violations else "passed")
    assert {entry["identity"] for entry in entries} <= records.keys()
    for entry in entries:
        record = records[entry["identity"]]
        assert record["approved_to_remove"] is False
        if entry["classification"] == "real_violation":
            assert record["final_disposition"] == "needs_decision"
            assert entry["blocker"] in record["replacement_evidence"]
        elif entry["classification"] == "application_owned_legitimate_outer_uow":
            assert record["final_disposition"] in {"retain_canonical", "retain_restricted"}


def test_task97_current_anomaly_page_query_is_exactly_read_only_restricted():
    path = "infrastructure/mysql/current_anomaly_issue_repository.py"
    symbol = "MySqlCurrentIssueRepository.query_current_page"
    review = _task97_exact_review(path, symbol)

    assert review == (
        "anomalies",
        "bounded current-only anomaly projection query",
        f"Task97 exact bounded read evidence for {path}::{symbol}",
        "retain_restricted:exact owner-scoped read grants no independent mutation authority",
    )


def test_task97_source_locked_reviews_are_exact_and_fail_closed_for_new_symbols():
    records = _records("writer_inventory_v3_disposition.records.jsonl")
    by_identity = {record["identity"]: record for record in records}
    commit_receipt = json.loads(
        (EVIDENCE_DIRECTORY.parent / "task97_repository_commit_dispositions_v1.json").read_text(encoding="utf-8")
    )
    commit_decisions = {entry["identity"]: entry["classification"] for entry in commit_receipt["entries"]}

    for identity in EXACT_IDENTITY_REVIEWS:
        if commit_decisions.get(identity) == "real_violation":
            assert by_identity[identity]["final_disposition"] == "needs_decision"
        else:
            assert by_identity[identity]["final_disposition"] != "needs_decision"
    for review_registry in (EXACT_SOURCE_REVIEWS, EXACT_SOURCE_RESTRICTED_REVIEWS):
        for path, (digest, symbols, _review) in review_registry.items():
            selected = [
                record
                for record in records
                if record["identity"].startswith(f"{path}:")
                and str(record["identity"]).split(":", 2)[1] in symbols
            ]
            assert selected, path
            source_matches = sha256((REPOSITORY_ROOT / path).read_bytes()).hexdigest() == digest
            for record in selected:
                identity = record["identity"]
                commit_decision = commit_decisions.get(identity)
                if commit_decision == "real_violation":
                    assert record["final_disposition"] == "needs_decision", identity
                elif (source_matches or identity in EXACT_IDENTITY_REVIEWS
                      or _task97_exact_review(path, identity.split(":", 2)[1]) is not None
                      or commit_decision == "application_owned_legitimate_outer_uow"):
                    assert record["final_disposition"] != "needs_decision", identity
                else:
                    # Expired source reviews must reject the writer, not inherit
                    # an old accepted snapshot. Independent exact decisions above
                    # do not grant approval to other occurrences or symbols.
                    assert record["final_disposition"] == "needs_decision", identity
            assert _task97_exact_review(path, "FutureUnreviewedWriter.mutate") is None


def test_writer_inventory_v3_receipts_close_legacy_scheduling_and_payroll_boundaries():
    records = _records("writer_inventory_v3_disposition.records.jsonl")
    scheduling_legacy = [
        record
        for record in records
        if record["owner"] == "scheduling"
        and "retired legacy matching communication transaction" in record["transaction_boundary"]
    ]
    payroll = [record for record in records if record["owner"] == "payroll"]

    assert not scheduling_legacy
    assert payroll
    cross_owner = [
        record
        for record in payroll
        if record["identity"].startswith(
            "infrastructure/mysql/leave_substitution_repository.py:"
            "_insert_special_pay_events:"
        )
    ]
    typed_special_pay = [
        record
        for record in payroll
        if record["identity"].startswith(
            "infrastructure/mysql/payroll_terms_writer.py:"
            "_insert_special_pay_events:"
        )
    ]
    assert not cross_owner
    assert len(typed_special_pay) == 1
    assert typed_special_pay[0]["final_disposition"] == "retain_canonical"
    assert all(record["final_disposition"] in {"retain_canonical", "retain_restricted"} for record in payroll)
    assert all("typed" in record["runtime_caller"].lower() for record in payroll)


def test_task97_service_day_writer_dispositions_are_exactly_scheduling_owned():
    records = _records("writer_inventory_v3_disposition.records.jsonl")
    expected = {
        ("infrastructure/mysql/scheduling_checkpoint_notification_source_repository.py", "MySqlSchedulingCheckpointNotificationSourceRepository.mark_published"),
        ("infrastructure/mysql/scheduling_checkpoint_notification_source_repository.py", "MySqlSchedulingCheckpointNotificationSourceRepository.mark_retry_or_failed"),
        ("infrastructure/mysql/service_day_checkpoint_repository.py", "MySqlServiceDayCheckpointRepository.append_checkpoint"),
        ("infrastructure/mysql/service_day_log_notification_stop_repository.py", "MySqlServiceDayLogNotificationStopRepository.claim_due"),
        ("infrastructure/mysql/service_day_log_notification_stop_repository.py", "MySqlServiceDayLogNotificationStopRepository.mark_published"),
        ("infrastructure/mysql/service_day_log_notification_stop_repository.py", "MySqlServiceDayLogNotificationStopRepository.mark_retry_or_failed"),
        ("infrastructure/mysql/service_day_log_repository.py", "MySqlServiceDayLogRepository.load_assignment"),
    }
    # The identity itself contains the method and the scanner operation after it.
    selected_records = [
        record
        for record in records
        if any(str(record["identity"]).startswith(f"{path}:{symbol}:") for path, symbol in expected)
    ]
    assert {(str(record["identity"]).split(":", 2)[0], str(record["identity"]).split(":", 2)[1]) for record in selected_records} == expected
    assert len(selected_records) == 9
    assert all(record["owner"] == "scheduling" for record in selected_records)
    assert all(record["final_disposition"] == "retain_canonical" for record in selected_records)
    assert all("manual review" not in record["runtime_caller"].lower() for record in selected_records)
    assert all("Staff Operations" in record["replacement_evidence"] for record in selected_records)
    assert all("LINE" in record["replacement_evidence"] for record in selected_records)
    for path, symbol in expected:
        review = _task97_exact_review(path, symbol)
        assert review is not None
        assert review[0] == "scheduling"
        assert review[1].startswith("Scheduling")
        assert review[3].startswith("retain_canonical:")


def test_task97_service_day_line_writers_remain_delivery_only():
    records = _records("writer_inventory_v3_disposition.records.jsonl")
    symbols = {
        "MySqlLineNotificationRepository.cancel_service_day_log_reminders",
        "MySqlLineNotificationRepository.cancel_service_day_log_reminders_for_assignments",
    }
    selected = [
        record
        for record in records
        if record["identity"].startswith("infrastructure/mysql/line_notification_repository.py:")
        and str(record["identity"]).split(":", 2)[1] in symbols
    ]

    assert len(selected) == 4
    assert all(record["owner"] == "line_delivery" for record in selected)
    assert all(record["final_disposition"] == "retain_canonical" for record in selected)
    assert all("Scheduling owns the Service Day completion fact" in record["replacement_evidence"] for record in selected)
    for symbol in symbols:
        review = _task97_exact_review(
            "infrastructure/mysql/line_notification_repository.py", symbol
        )
        assert review is not None
        assert review[0] == "line_delivery"
        assert review[3].startswith("retain_canonical:")


def _identities(filename: str) -> set[str]:
    lines = (EVIDENCE_DIRECTORY / filename).read_text(encoding="utf-8").splitlines()
    return {str(json.loads(line)["identity"]) for line in lines if line}


def _records(filename: str) -> list[dict[str, str]]:
    lines = (EVIDENCE_DIRECTORY / filename).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line]


def test_task97_blocked_receipt_keeps_exact_acceptance_without_overriding_blockers(tmp_path, monkeypatch):
    import scripts.reconcile_writer_inventory_v3_dispositions as reconciler

    artifact = json.loads(reconciler.COMMIT_DISPOSITIONS.read_text(encoding="utf-8"))
    accepted = next(entry for entry in artifact["entries"] if entry["classification"] == "application_owned_legitimate_outer_uow")
    # Simulate a rejected identity in the isolated receipt; the real
    # repository need not retain any particular blocker for this test.
    blocked = dict(accepted, identity=accepted["identity"] + ":blocked-fixture",
        classification="real_violation", analysis_basis="unowned transaction fixture",
        replacement_or_remediation="restore an explicitly owned outer boundary",
        blocker="unowned_commit_fixture", zero_reference_oracle="isolated exact-identity test")
    receipt = tmp_path / "commit-dispositions.json"
    receipt.write_text(json.dumps({"terminal_status": "blocked", "entries": [accepted, blocked]}), encoding="utf-8")
    monkeypatch.setattr(reconciler, "COMMIT_DISPOSITIONS", receipt)

    assert reconciler._commit_review(accepted["identity"])[3].startswith("retain_")
    assert reconciler._commit_review(accepted["identity"] + ":new-occurrence") is None
    monkeypatch.setitem(reconciler.EXACT_IDENTITY_REVIEWS, blocked["identity"],
        ("old-owner", "old-boundary", "old-review", "retain_canonical:obsolete decision"))
    candidate = {"identity": blocked["identity"], "relative_path": blocked["source_path"],
        "symbol": blocked["symbol"], "operation": "COMMIT", "fingerprint": blocked["fingerprint"]}
    result = reconciler._disposition(candidate)
    assert result["final_disposition"] == "needs_decision"
    assert result["approved_to_remove"] is False
    assert blocked["blocker"] in result["replacement_evidence"]


def test_data_browser_exact_review_rejects_new_symbol_and_changed_source(tmp_path, monkeypatch):
    import scripts.reconcile_writer_inventory_v3_dispositions as reconciler

    path = "infrastructure/mysql/data_browser_query_repository.py"
    symbol = "DataBrowserQueryRepository.query_page"
    reviews = reconciler.EXACT_SOURCE_REVIEWS
    assert reconciler._exact_source_review(path, symbol, reviews) is not None
    assert reconciler._exact_source_review(path, symbol + "_unreviewed", reviews) is None
    original = (reconciler.ROOT / path).read_bytes()
    changed = tmp_path / path
    changed.parent.mkdir(parents=True)
    changed.write_bytes(original + b"\n# unreviewed source change\n")
    monkeypatch.setattr(reconciler, "ROOT", tmp_path)
    assert reconciler._exact_source_review(path, symbol, reviews) is None



def test_reconciliation_preserves_valid_typed_receipts_and_refreshes_exact_blockers(tmp_path, monkeypatch):
    import scripts.reconcile_writer_inventory_v3_dispositions as reconciler

    candidates = {entry["identity"]: entry for entry in reconciler._load(reconciler.CANDIDATE)}
    saved = reconciler._load(reconciler.RECORDS)
    typed = [entry for entry in saved if entry["owner"] == "payroll"
             and candidates[entry["identity"]]["operation"] == "COMMIT"]
    retained, stale = typed[:2]
    receipt = json.loads(reconciler.COMMIT_DISPOSITIONS.read_text(encoding="utf-8"))
    exact = {entry["identity"]: entry for entry in receipt["entries"]}
    blocked = dict(exact[stale["identity"]], classification="real_violation",
                   analysis_basis="isolated missing-owner fixture",
                   replacement_or_remediation="restore the owning outer transaction",
                   blocker="isolated_unowned_commit", zero_reference_oracle="isolated test")
    paths = {name: tmp_path / (name.lower() + ".json")
             for name in ("CANDIDATE", "RECORDS", "MANIFEST", "COMMIT_DISPOSITIONS")}
    paths["CANDIDATE"].write_text("".join(json.dumps(candidates[entry["identity"]]) + "\n"
                                          for entry in (retained, stale)), encoding="utf-8")
    paths["RECORDS"].write_text("".join(json.dumps(entry) + "\n"
                                        for entry in (retained, stale)), encoding="utf-8")
    paths["COMMIT_DISPOSITIONS"].write_text(json.dumps({
        "terminal_status": "blocked", "entries": [exact[retained["identity"]], blocked]
    }), encoding="utf-8")
    for name, path in paths.items():
        monkeypatch.setattr(reconciler, name, path)

    assert reconciler.main() == 0
    actual = {entry["identity"]: entry for entry in reconciler._load(paths["RECORDS"])}
    assert actual[retained["identity"]] == retained
    assert actual[stale["identity"]]["final_disposition"] == "needs_decision"
    assert actual[stale["identity"]]["approved_to_remove"] is False
    assert blocked["blocker"] in actual[stale["identity"]]["replacement_evidence"]
