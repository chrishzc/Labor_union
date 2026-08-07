"""Safety contract tests for the preserve-data rehearsal plan."""

from __future__ import annotations

from pathlib import Path

from infrastructure.migration.rehearsal_runtime import (
    CandidateReadSmokePort,
    CandidateRuntimeConfig,
    EphemeralCandidateRestartPort,
    REHEARSAL_INTERNAL_API_KEY,
    _read_smoke_headers,
)
from scripts import migrate_preserved_database_additive_schema as runner


def test_plan_remains_ready_after_restore_candidate_exists(monkeypatch) -> None:
    monkeypatch.setattr(runner, "server_identity", lambda *_: {"server": "test"})
    monkeypatch.setattr(runner, "_schema_snapshot", lambda *_: {"sha256": "schema"})
    monkeypatch.setattr(runner, "_owned_classification", lambda *_: {})
    monkeypatch.setattr(runner, "database_exists", lambda *_: True)
    monkeypatch.setattr(runner, "schema_artifacts", lambda: [])
    monkeypatch.setattr(runner, "_table_evidence", lambda *_: {"orders": {"count": 1}})
    monkeypatch.setattr(runner, "RELEASE_MANIFEST", type("Manifest", (), {
        "release_id": "test-release", "fingerprint": "manifest"
    })())
    monkeypatch.setattr(runner, "SCHEMA_PARTS", ())

    plan = runner.build_plan(runner.DatabaseConfig("host", 1, "user", "password"), "source", "candidate")

    assert plan["status"] == "ready"
    assert plan["candidate_precondition"] == "source_data_must_match_before_apply"


def test_complete_restart_records_shutdown_after_all_read_smokes(tmp_path, monkeypatch) -> None:
    class Contract:
        phase = "post-restart"
        verification_id = "application-read-smoke"

    class Manifest:
        required_restart_targets = ("api", "streamlit")
        post_cutover_smoke_ids = ("orders-read",)
        verification_contracts = (Contract(),)

    class RestartPort:
        def __init__(self):
            self.targets = []
            self.stopped = False

        def restart(self, target):
            self.targets.append(target)
            return {"status": "passed", "target": target}

        def shutdown(self):
            self.stopped = True
            return ({"status": "passed", "target": "streamlit"},)

    class SmokePort:
        def run(self, smoke_id):
            return {"status": "passed", "smoke_id": smoke_id}

    monkeypatch.setattr(runner, "RELEASE_MANIFEST", Manifest())
    receipt_path = tmp_path / "switch.json"
    runner.write_receipt(receipt_path, {"status": "switched"})
    restart = RestartPort()

    completed = runner.complete_cutover_after_restart(
        receipt_path,
        restart,
        SmokePort(),
    )

    assert completed["status"] == "completed"
    assert restart.targets == ["api", "streamlit"]
    assert restart.stopped is True
    assert completed["post_restart"]["shutdown_receipts"] == (
        {"status": "passed", "target": "streamlit"},
    )


def test_schema_applied_receipt_resumes_post_schema_phase(tmp_path, monkeypatch) -> None:
    plan = {
        "status": "ready",
        "plan_fingerprint": "fingerprint",
        "source": {"database": "source", "server": "server", "host": "host", "port": 1},
        "candidate_database": "candidate",
        "source_schema_sha256": "source-schema",
        "source_data": {"orders": {"count": 1}},
    }
    receipt_path = tmp_path / "operation.json"
    runner.write_receipt(receipt_path, {
        "status": "schema_applied",
        "candidate_database": "candidate",
        "source": {"database": "source", "server": "server"},
        "restored_data": plan["source_data"],
        "candidate_schema_sha256": "candidate-schema",
    })
    monkeypatch.setattr(runner, "read_receipt", lambda path: plan if path.name == "plan.json" else {
        "status": "schema_applied",
        "candidate_database": "candidate",
        "source": {"database": "source", "server": "server"},
        "restored_data": plan["source_data"],
        "candidate_schema_sha256": "candidate-schema",
    })
    monkeypatch.setattr(runner, "build_plan", lambda *_: plan)
    monkeypatch.setattr(runner, "_validate_plan_integrity", lambda *_: None)
    monkeypatch.setattr(runner, "database_exists", lambda *_: True)
    monkeypatch.setattr(runner, "server_identity", lambda *_: {"server": "server"})
    monkeypatch.setattr(runner, "_schema_snapshot", lambda *_: {"sha256": "candidate-schema"})
    monkeypatch.setattr(runner, "_owned_classification", lambda *_: {"owned": "exact"})
    monkeypatch.setattr(runner, "_table_evidence", lambda *_: plan["source_data"])
    monkeypatch.setattr(runner, "run_candidate_post_schema", lambda *_args, **_kwargs: {"status": "backfilled"})

    result = runner.apply_schema(
        runner.DatabaseConfig("host", 1, "user", "password"),
        "source", "candidate", tmp_path / "plan.json", receipt_path,
    )

    assert result == {"status": "backfilled"}


def test_rehearsal_worker_starts_as_project_module(tmp_path) -> None:
    config = CandidateRuntimeConfig(
        Path.cwd(), 18022, 18522, 30, {}, object(), "candidate", tmp_path,
    )

    command = EphemeralCandidateRestartPort(config)._worker_command()

    assert command[1:3] == ["-m", "scripts.run_durable_job_worker"]


def test_rehearsal_read_smoke_uses_its_internal_service_key() -> None:
    assert _read_smoke_headers() == {
        "X-Internal-API-Key": REHEARSAL_INTERNAL_API_KEY,
    }


def test_empty_dataset_is_an_explicit_scheduling_and_payroll_smoke_case(tmp_path) -> None:
    config = CandidateRuntimeConfig(
        Path.cwd(), 18022, 18522, 30, {}, object(), "candidate", tmp_path,
    )
    smoke = CandidateReadSmokePort(config)

    assert smoke._accepted_statuses("scheduling-read") == frozenset({200, 404})
    assert smoke._accepted_statuses("payroll-payables-read") == frozenset({200, 404})


def test_verified_candidate_is_eligible_for_repeat_verification() -> None:
    assert "verified" in runner.VERIFYABLE_CANDIDATE_STATUSES
