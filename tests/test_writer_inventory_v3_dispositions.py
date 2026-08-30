import json
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


def test_task97_exact_commit_receipts_leave_no_matching_writer_undecided():
    records = {
        record["identity"]: record
        for record in _records("writer_inventory_v3_disposition.records.jsonl")
    }
    commit_receipt = json.loads(
        (
            EVIDENCE_DIRECTORY.parent
            / "task97_repository_commit_dispositions_v1.json"
        ).read_text(encoding="utf-8")
    )

    assert commit_receipt["terminal_status"] == "passed"
    matching = [
        records[entry["identity"]]
        for entry in commit_receipt["entries"]
        if entry["identity"] in records
    ]
    assert matching
    assert all(record["final_disposition"] != "needs_decision" for record in matching)


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

    for identity in EXACT_IDENTITY_REVIEWS:
        assert by_identity[identity]["final_disposition"] != "needs_decision"
    for review_registry in (EXACT_SOURCE_REVIEWS, EXACT_SOURCE_RESTRICTED_REVIEWS):
        for path, (_digest, symbols, _review) in review_registry.items():
            selected = [
                record
                for record in records
                if record["identity"].startswith(f"{path}:")
                and str(record["identity"]).split(":", 2)[1] in symbols
            ]
            assert selected, path
            assert all(record["final_disposition"] != "needs_decision" for record in selected)


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
