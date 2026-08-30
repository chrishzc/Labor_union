import copy
import json
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from scripts.verify_verification_baseline import (
    coverage_report,
    load_baseline,
    verify_baseline,
)
from scripts.verify_verification_scenarios import (
    load_scenarios,
    scenario_coverage_report,
    verify_scenarios,
)
from scripts.verify_verification_receipts import (
    _persistent_database_source_errors,
    load_receipts,
    receipt_coverage_report,
    _source_aware_scenario_digest,
    verify_receipts,
)
from scripts.verification_gate_report import build_gate_report
from scripts.verification_gate_report import write_gate_report
from scripts.verify_verification_fixtures import (
    fixture_coverage_report,
    load_fixtures,
    verify_fixtures,
)


@lru_cache(maxsize=1)
def _current_gate_report() -> dict[str, object]:
    """避免同一唯讀測試模組重複掃描整個驗收基線。"""
    return build_gate_report()


def test_checked_in_dual_track_verification_baseline_is_valid():
    assert verify_baseline(load_baseline()) == []


def test_coverage_keeps_gaps_visible_and_never_claims_overall_completion():
    report = coverage_report(load_baseline())

    assert report["overall_complete"] is False
    assert "CI" in report["tracks"][0]["gaps"]
    assert "MIG" in report["tracks"][1]["gaps"]


def test_validator_rejects_derived_data_as_a_business_root_policy():
    baseline = copy.deepcopy(load_baseline())
    baseline["tracks"][0]["root_input_policy"] = "seed_all_tables"

    assert verify_baseline(baseline) == ["track A has an invalid root input policy"]


def test_validator_rejects_unknown_test_kind_and_false_completion():
    baseline = copy.deepcopy(load_baseline())
    suite = baseline["tracks"][1]["suites"][0]
    suite["test_kinds"] = ["database_seed"]
    suite["status"] = "complete"

    assert verify_baseline(baseline) == [
        "suite MIG has unsupported test_kinds",
        "suite MIG has a test_kind outside track B",
        "suite MIG cannot be complete before executable scenario receipts exist",
    ]


def test_validator_rejects_a_test_kind_from_the_other_track():
    baseline = copy.deepcopy(load_baseline())
    baseline["tracks"][0]["suites"][0]["test_kinds"] = ["metadata_fixture"]

    assert verify_baseline(baseline) == [
        "suite ORD has a test_kind outside track A"
    ]


def test_validator_rejects_suite_acceptance_that_does_not_cover_its_test_kinds():
    baseline = copy.deepcopy(load_baseline())
    baseline["tracks"][0]["suites"][0]["acceptance"] = ["one generic statement"]

    assert verify_baseline(baseline) == [
        "suite ORD has incomplete acceptance criteria"
    ]


def test_checked_in_scenarios_follow_the_dual_track_contract():
    assert verify_scenarios(load_scenarios()) == []


def test_scenario_coverage_reports_contract_coverage_without_claiming_execution():
    report = scenario_coverage_report(load_scenarios())

    assert report["scenario_count"] >= 27
    assert report["suites_without_scenario"] == []
    assert report["business_requirements_missing"] == []
    assert "CF-03" not in report["business_requirements_missing"]


def test_scenario_validator_rejects_a_business_requirement_missing_from_the_matrix():
    scenarios = copy.deepcopy(load_scenarios())
    scenario = next(
        item for item in scenarios if item["scenario_id"] == "CF-REFUND-RECOVERY-001"
    )
    scenario["coverage_ids"] = ["NOT-A-REQUIREMENT"]

    errors = verify_scenarios(scenarios)

    assert errors[0] == "scenario CF-REFUND-RECOVERY-001 has unknown business coverage ids"
    assert errors[1].startswith("missing business requirement mappings: CF-01")


def test_scenario_validator_rejects_a_missing_source_reference():
    scenarios = copy.deepcopy(load_scenarios())
    scenario = next(item for item in scenarios if item["scenario_id"] == "ENTRY-001")
    scenario["source_refs"] = ["document/does-not-exist.md"]

    assert verify_scenarios(scenarios) == [
        "scenario ENTRY-001 has a missing source reference"
    ]


def test_scenario_validator_rejects_a_missing_source_anchor():
    scenarios = copy.deepcopy(load_scenarios())
    scenario = next(item for item in scenarios if item["scenario_id"] == "ENTRY-001")
    scenario["source_refs"] = [
        "document/資料庫、資料處理/新版驗證雙軌總計畫_草案.md#NOT-A-REAL-SECTION"
    ]

    assert verify_scenarios(scenarios) == [
        "scenario ENTRY-001 has a missing source reference"
    ]


def test_scenario_validator_rejects_a_test_kind_not_approved_by_its_suite():
    scenarios = copy.deepcopy(load_scenarios())
    scenario = next(item for item in scenarios if item["scenario_id"] == "ENTRY-001")
    scenario["test_kinds"] = ["domain_root_data"]

    assert verify_scenarios(scenarios) == [
        "scenario ENTRY-001 has a test_kind outside its suite contract"
    ]


def test_scenario_validator_rejects_duplicate_test_kinds():
    scenarios = copy.deepcopy(load_scenarios())
    scenario = next(item for item in scenarios if item["scenario_id"] == "ENTRY-001")
    scenario["test_kinds"].append("metadata_fixture")

    assert verify_scenarios(scenarios) == [
        "scenario ENTRY-001 has duplicate test_kinds"
    ]


def test_scenario_validator_rejects_incomplete_acceptance_criteria():
    scenarios = copy.deepcopy(load_scenarios())
    scenario = next(item for item in scenarios if item["scenario_id"] == "ORD-LIFECYCLE-001")
    scenario["expected"] = ["one generic assertion"]

    assert verify_scenarios(scenarios) == [
        "scenario ORD-LIFECYCLE-001 has incomplete acceptance criteria"
    ]


def test_scenario_validator_rejects_a_bound_database_scenario_without_safety_mode():
    scenarios = copy.deepcopy(load_scenarios())
    scenario = next(
        item for item in scenarios
        if item["scenario_id"] == "ORD-AUTO-COMPLETION-002"
    )
    scenario.pop("database_execution_mode")

    assert verify_scenarios(scenarios) == [
        "scenario ORD-AUTO-COMPLETION-002 must define a safe database execution mode"
    ]


def test_scenario_validator_rejects_a_blocked_scenario_without_a_blocker():
    scenarios = copy.deepcopy(load_scenarios())
    scenario = next(item for item in scenarios if item["scenario_id"] == "PERF-UX-001")
    scenario.pop("blocker")

    assert verify_scenarios(scenarios) == [
        "scenario PERF-UX-001 must define a blocker"
    ]


def test_scenario_validator_rejects_an_uncovered_suite():
    scenarios = [
        scenario for scenario in load_scenarios()
        if scenario["suite_id"] != "ENTRY"
    ]

    assert verify_scenarios(scenarios) == [
        "missing scenario contracts for suites: ENTRY"
    ]


def test_receipt_coverage_never_treats_absent_evidence_as_a_passing_scenario():
    scenarios = load_scenarios()

    assert verify_receipts([], scenarios) == []
    report = receipt_coverage_report([], scenarios)

    assert report["receipt_count"] == 0
    assert report["passed_scenario_ids"] == []
    assert report["scenarios_without_passing_receipt"] == sorted(
        scenario["scenario_id"] for scenario in scenarios
    )
    assert report["all_scenarios_verified"] is False


def test_receipt_validator_rejects_unknown_scenario_and_invalid_digest():
    receipt = {
        "contract": "labor-union-verification-receipt/v1",
        "scenario_id": "UNKNOWN-001",
        "result": "passed",
        "assertion_count": 1,
        "runner": ["pytest"],
        "environment": {"python": "3.14"},
        "scenario_digest": "0" * 64,
        "input_digests": {"fixture": "not-a-sha256"},
    }

    assert verify_receipts([receipt], load_scenarios()) == [
        "receipt UNKNOWN-001 references an unknown scenario",
        "receipt UNKNOWN-001 has a stale or missing scenario digest",
        "receipt UNKNOWN-001 has an invalid input digest",
        "receipt UNKNOWN-001 must record input paths",
    ]


def test_receipt_validator_rejects_unbound_passing_evidence():
    scenarios = copy.deepcopy(load_scenarios())
    scenario = next(item for item in scenarios if item["scenario_id"] == "ORD-LIFECYCLE-001")
    receipt = {
        "contract": "labor-union-verification-receipt/v1",
        "scenario_id": scenario["scenario_id"],
        "result": "passed",
        "assertion_count": 1,
        "runner": ["pytest"],
        "environment": {"python": "3.14"},
        "scenario_digest": _source_aware_scenario_digest(
            Path("validation/scenarios/ORD-LIFECYCLE-001.json")
        ),
        "input_digests": {
            "fixture": sha256(
                Path("validation/fixtures/ORD-LIFECYCLE-001.json").read_bytes()
            ).hexdigest()
        },
        "input_paths": {"fixture": "validation/fixtures/ORD-LIFECYCLE-001.json"},
    }

    assert verify_receipts([receipt], scenarios) == [
        "receipt ORD-LIFECYCLE-001 cannot pass an unbound scenario",
        "receipt ORD-LIFECYCLE-001 runner does not match scenario binding",
    ]


def test_receipt_validator_rejects_database_evidence_outside_lu_test_namespace():
    receipts = copy.deepcopy(load_receipts())
    receipt = next(
        item for item in receipts
        if item["scenario_id"] == "FI-CANONICAL-STAGING-003"
    )
    receipt["environment"]["database"] = "union_db_candidate_20260803_v5"

    errors = verify_receipts(receipts, load_scenarios())

    # 現行基線刻意保留過期 receipt 作為 fail-closed 訊號；此案例只驗證
    # 目標資料庫名稱違反隔離規則時，仍會被額外精準指出。
    assert "receipt FI-CANONICAL-STAGING-003 must use a lu_test_* database" in errors


def test_persistent_database_source_guard_rejects_unsafe_runner(tmp_path):
    unsafe_runner = tmp_path / "unsafe_runner.py"
    unsafe_runner.write_text(
        "DATABASE = 'lu_test_validation_v1'\n"
        "LABOR_UNION_TEST_MYSQL_DATABASE = DATABASE\n"
        "DB_DATABASE = DATABASE\n"
        "DELETE FROM orders\n",
        encoding="utf-8",
    )

    errors = _persistent_database_source_errors(
        "SAFE-001",
        {
            "database_execution_mode": "persistent_append_only",
            "execution": {"test_paths": ["unsafe_runner.py"]},
        },
        tmp_path,
    )

    assert errors == [
        "receipt SAFE-001 persistent test lacks an explicit database guard",
        "receipt SAFE-001 persistent test contains a destructive database operation",
    ]


def test_scenario_digest_changes_when_its_authoritative_source_changes(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("# RULE-01\nfirst", encoding="utf-8")
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps({"source_refs": [str(source) + "#RULE-01"]}), encoding="utf-8"
    )
    first = _source_aware_scenario_digest(scenario)
    source.write_text("# RULE-01\nrevised", encoding="utf-8")

    assert _source_aware_scenario_digest(scenario) != first


def test_gate_report_separates_complete_contracts_from_unverified_execution():
    report = _current_gate_report()

    # 來源或 schema 已變動但尚未取得全套重跑 receipt 時，gate 必須保留
    # fail-closed 狀態，不能以舊 digest 宣稱驗收已完成。
    assert report["contract_valid"] is False
    assert report["baseline_established"] is False
    assert any(not item["satisfied"] for item in report["baseline_deliverables"])
    assert report["errors"]["field_authority"] == []
    assert report["field_authority"]["mappings"][0]["unexpected_legacy_references"] == []
    assert report["business_matrix"] == {"required": 127, "missing": []}
    assert report["fixtures"]["fixture_count"] == 38
    assert report["fixtures"]["valid"] is True
    assert report["fixtures"]["all_a_scenarios_have_fixture"] is True
    assert all(not track["suites_missing_contract"] for track in report["tracks"])
    assert report["receipts"]["all_scenarios_verified"] is False
    assert report["database_execution"]["execution_evidence_recorded"] is True
    assert report["database_execution"]["passed_disposable_database_scenarios"] == [
        "AC-CAPABILITY-SESSION-002",
        "ANOM-SCHEDULING-CLOSED-LOOP-002",
        "CF-EXPLICIT-REFUND-RECOVERY-002",
        "CI-CANONICAL-ROOTS-002",
        "FI-CANONICAL-STAGING-003",
        "FI-UI-PREVIEW-PARITY-003",
        "JOB-QUEUE-LIFECYCLE-002",
        "KN-KNOWLEDGE-LIFECYCLE-001",
        "MIG-VALIDATION-SCHEMA-002",
        "ORD-AUTO-COMPLETION-002",
    ]
    assert report["database_execution"]["passed_by_execution_mode"] == {
        "persistent_append_only": [
            "AC-CAPABILITY-SESSION-002",
            "ANOM-SCHEDULING-CLOSED-LOOP-002",
            "CF-EXPLICIT-REFUND-RECOVERY-002",
            "CI-CANONICAL-ROOTS-002",
            "FI-CANONICAL-STAGING-003",
            "FI-UI-PREVIEW-PARITY-003",
            "JOB-QUEUE-LIFECYCLE-002",
            "KN-KNOWLEDGE-LIFECYCLE-001",
            "ORD-AUTO-COMPLETION-002",
        ],
        "read_only_existing_database": ["MIG-VALIDATION-SCHEMA-002"],
    }
    assert report["overall_complete"] is False


def test_gate_report_keeps_supplemental_receipts_separate_from_master_scenarios():
    report = _current_gate_report()
    suites = {row["suite_id"]: row for row in report["suite_execution"]}

    assert suites["PAY"]["unverified_matrix_scenario_ids"] == [
        "PAY-AND-SP-OBLIGATION-001"
    ]
    assert suites["PAY"]["passed_supplemental_scenario_ids"] == [
        "PAY-ASSIGNMENT-RECONCILIATION-002"
    ]
    assert suites["BKR"]["unverified_matrix_scenario_ids"] == ["BKR-RESTORE-001"]
    assert suites["BKR"]["passed_supplemental_scenario_ids"] == [
        "BKR-ARTIFACT-RESTORE-GUARDS-002"
    ]
    assert suites["REL"]["passed_supplemental_scenario_ids"] == [
        "REL-PREFLIGHT-FAIL-CLOSED-002"
    ]
    assert suites["SCH"]["passed_supplemental_scenario_ids"] == [
        "SCH-WAITING-LOCK-RELEASE-002"
    ]
    assert suites["PAY"]["full_suite_verified"] is False
    assert suites["ORD"]["passed_supplemental_scenario_ids"] == [
        "ORD-AUTO-COMPLETION-002", "ORD-CANCELLATION-WORKFLOW-003",
        "ORD-DETAIL-TYPED-QUERY-004",
    ]


def test_gate_report_separates_data_fixtures_from_runtime_evidence():
    report = _current_gate_report()
    boundaries = {row["track"]: row["test_kinds"] for row in report["evidence_boundaries"]}

    assert boundaries["A"]["domain_root_data"]["declared_scenarios"] >= 1
    assert boundaries["A"]["external_input_fixture"]["declared_scenarios"] >= 1
    assert boundaries["A"]["subsystem_state_machine"] == {
        "declared_scenarios": 3,
        "bound_scenarios": 2,
        "passing_receipts": 2,
    }
    assert boundaries["B"]["metadata_fixture"]["declared_scenarios"] >= 1
    assert boundaries["B"]["filesystem_artifact"]["declared_scenarios"] >= 1
    assert boundaries["B"]["process_network_harness"]["passing_receipts"] >= 1
    assert boundaries["B"]["benchmark_evidence"]["passing_receipts"] == 0


def test_gate_report_records_architecture_deferred_performance_blocker():
    report = _current_gate_report()

    assert report["blocked_scenarios"] == [{
        "scenario_id": "PERF-UX-001",
        "track": "B",
        "suite_id": "PERF",
        "blocker": (
            "UI click-to-render telemetry is deferred until the React-versus-"
            "Streamlit architecture decision is finalized; current Streamlit state "
            "has no browser paint metric."
        ),
    }]


def test_gate_report_can_be_saved_as_utf8_evidence(tmp_path):
    report_path = tmp_path / "verification-gate.json"

    write_gate_report(report_path, {"contract_valid": True})

    assert json.loads(report_path.read_text(encoding="utf-8")) == {
        "contract_valid": True
    }


def test_root_fixture_and_expected_manifest_are_valid():
    assert verify_fixtures(load_fixtures()) == []


def test_fixture_validator_rejects_direct_seed_of_a_derived_field():
    fixtures = copy.deepcopy(load_fixtures())
    fixture = next(
        item for item in fixtures if item["scenario_id"] == "CF-REFUND-RECOVERY-001"
    )
    fixture["seed_fields"].append("refund_progress.status")

    assert verify_fixtures(fixtures) == [
        "fixture CF-REFUND-RECOVERY-001 directly seeds derived fields"
    ]


def test_fixture_validator_rejects_a_semantically_derived_seed_without_exception():
    fixtures = copy.deepcopy(load_fixtures())
    fixture = next(
        item for item in fixtures
        if item["scenario_id"] == "CF-EXPLICIT-REFUND-RECOVERY-002"
    )
    fixture.pop("permitted_same_named_input_fields")

    assert verify_fixtures(fixtures) == [
        "fixture CF-EXPLICIT-REFUND-RECOVERY-002 directly seeds semantically derived fields"
    ]


def test_fixture_validator_rejects_a_state_machine_seed_outside_its_harness():
    fixtures = copy.deepcopy(load_fixtures())
    fixture = next(
        item for item in fixtures
        if item["scenario_id"] == "ORD-CANCELLATION-WORKFLOW-003"
    )
    fixture["seed_fields"][0] = "orders.status"

    assert verify_fixtures(fixtures) == [
        "fixture ORD-CANCELLATION-WORKFLOW-003 seeds outside its harness boundary"
    ]


def test_fixture_validator_rejects_an_unknown_or_duplicate_a_fixture():
    fixtures = copy.deepcopy(load_fixtures())
    duplicate = copy.deepcopy(fixtures[0])
    fixtures.append(duplicate)

    assert verify_fixtures(fixtures) == [
        f"duplicate fixture scenario id: {duplicate['scenario_id']}"
    ]


def test_fixture_coverage_proves_every_a_scenario_has_root_data_contract():
    report = fixture_coverage_report(load_fixtures())

    assert report["required_a_scenario_count"] == 38
    assert report["scenarios_without_fixture"] == []
    assert report["all_a_scenarios_have_fixture"] is True
    assert "CF-REFUND-RECOVERY-001" not in report["scenarios_without_fixture"]
