"""Safety contract tests for the preserve-data rehearsal plan."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from infrastructure.migration.maintenance import issue_maintenance_window_token
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
    monkeypatch.setattr(runner, "_owned_classification", lambda *_, **__: {})
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


def test_complete_restart_cli_wires_candidate_only_runtime_ports(tmp_path, monkeypatch) -> None:
    environment = tmp_path / "rehearsal.env"
    environment.write_text("DB_DATABASE=rehearsal_source\n", encoding="utf-8")
    source = runner.DatabaseDescriptor(
        "source-read", "rehearsal_source",
        runner.DatabaseConfig("source-host", 3306, "reader", "reader-secret"),
    )
    candidate = runner.DatabaseDescriptor(
        "candidate-write", "rehearsal_candidate",
        runner.DatabaseConfig("candidate-host", 3307, "writer", "writer-secret"),
    )
    config = runner.SeparateDatabaseConfig(source, candidate)
    received = {}

    class RestartPort:
        def __init__(self, runtime):
            received["runtime"] = runtime

    class SmokePort:
        def __init__(self, runtime):
            received["smoke_runtime"] = runtime

    monkeypatch.setattr(runner, "build_descriptor_runtime", lambda *_: config)
    monkeypatch.setattr(runner, "run_source_safety_preflight", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(runner, "EphemeralCandidateRestartPort", RestartPort)
    monkeypatch.setattr(runner, "CandidateReadSmokePort", SmokePort)
    monkeypatch.setattr(
        runner,
        "complete_cutover_after_restart",
        lambda _receipt, restart, smoke: {
            "status": "completed",
            "restart_port": type(restart).__name__,
            "smoke_port": type(smoke).__name__,
        },
    )

    exit_code = runner.main([
        "--complete-restart",
        "--environment-file", str(environment),
        "--source-database", "rehearsal_source",
        "--candidate-database", "rehearsal_candidate",
        "--source-read-descriptor", str(tmp_path / "source.json"),
        "--candidate-write-descriptor", str(tmp_path / "candidate.json"),
        "--source-principal-evidence", str(tmp_path / "principal.json"),
        "--maintenance-token", str(tmp_path / "token.json"),
        "--receipt-directory", str(tmp_path / "receipts"),
        "--switch-receipt", str(tmp_path / "switch.json"),
        "--rehearsal-api-port", "18022",
        "--rehearsal-streamlit-port", "18522",
    ])

    assert exit_code == 0
    assert received["runtime"].database_environment["DB_DATABASE"] == "rehearsal_candidate"
    assert received["runtime"].database_environment["DB_HOST"] == "candidate-host"
    assert received["runtime"] == received["smoke_runtime"]


def test_candidate_runtime_rejects_unsafe_or_colliding_ports(tmp_path) -> None:
    config = runner.SeparateDatabaseConfig(
        runner.DatabaseDescriptor(
            "source-read", "rehearsal_source",
            runner.DatabaseConfig("source-host", 3306, "reader", "reader-secret"),
        ),
        runner.DatabaseDescriptor(
            "candidate-write", "rehearsal_candidate",
            runner.DatabaseConfig("candidate-host", 3307, "writer", "writer-secret"),
        ),
    )

    with pytest.raises(runner.UpgradeBlocked, match="must differ"):
        runner.build_candidate_runtime_config(
            config, "rehearsal_candidate", tmp_path, 18022, 18022, 30,
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


def test_release_chain_drives_schema_artifacts_and_v8_descriptor_presence() -> None:
    artifact_names = tuple(path.name for path in runner.SCHEMA_PARTS)

    assert artifact_names[-11:] == (
        "154_line_integration_inbox_delivery.sql",
        "155_line_identity_review_configuration.sql",
        "156_line_publication_media_order_group.sql",
        "157_line_runtime_control.sql",
        "158_line_identity_runtime.sql",
        "159_line_messaging_publication_runtime.sql",
        "160_line_order_group_runtime.sql",
        "161_runtime_monitoring_line_alerts.sql",
        "162_matching_line_communication.sql",
        "163_knowledge_runtime.sql",
        "164_line_rich_menu_preview_bridge.sql",
    )
    assert "153_retire_empty_legacy_field_inventory.sql" in artifact_names
    assert runner.RELEASE_MANIFEST.release_id == "labor-union-2026-08-09-v8"
    assert runner._descriptor_presence_state(
        {"tables": {"knowledge_items": ["id", "version"]}, "triggers": []},
        {"knowledge_items": {"id", "version"}},
        set(),
    ) == "exact"


def test_preflight_requires_live_read_only_principal_and_bound_token(
    tmp_path, monkeypatch
) -> None:
    plan = {
        "source": {"database": "rehearsal_source"},
        "source_schema_sha256": "schema-digest",
        "source_data": {"orders": {"count": 1}},
        "plan_fingerprint": "plan-digest",
    }
    evidence = runner.SourcePrincipalEvidence(
        principal="rehearsal_reader@localhost",
        source_database="rehearsal_source",
        privileges=frozenset({"SELECT"}),
    )
    source_data_digest = runner.fingerprint_source_data_evidence(
        plan["source_data"]
    )
    now = datetime.now(timezone.utc)
    token = issue_maintenance_window_token(
        token_id="window-1",
        source_database="rehearsal_source",
        source_schema_sha256="schema-digest",
        source_data_sha256=source_data_digest,
        write_freeze_started_at=(now - timedelta(minutes=1)).isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
        issuer="release-manager",
    )
    evidence_path = tmp_path / "principal.json"
    evidence_path.write_text(json.dumps({
        "principal": evidence.principal,
        "source_database": evidence.source_database,
        "privileges": sorted(evidence.privileges),
    }), encoding="utf-8")
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps(asdict(token)), encoding="utf-8")
    runtime = runner.SeparateDatabaseConfig(
        runner.DatabaseDescriptor(
            "source-read", "rehearsal_source",
            runner.DatabaseConfig("host", 3306, "reader", "secret"),
        ),
        runner.DatabaseDescriptor(
            "candidate-write", "rehearsal_candidate",
            runner.DatabaseConfig("host", 3306, "writer", "secret"),
        ),
    )
    monkeypatch.setattr(runner, "build_plan", lambda *_: plan)
    monkeypatch.setattr(
        runner, "inspect_source_read_only_principal", lambda *_: evidence
    )

    receipt = runner.run_source_safety_preflight(
        runtime,
        "rehearsal_source",
        "rehearsal_candidate",
        evidence_path,
        token_path,
        tmp_path / "receipts",
        mode="dry-run",
    )

    assert receipt["status"] == "passed"
    assert (tmp_path / "receipts" / "cutover.journal.jsonl").is_file()
    assert "secret" not in json.dumps(receipt)


def test_preflight_rejects_declared_principal_that_differs_from_live(
    tmp_path, monkeypatch
) -> None:
    plan = {
        "source": {"database": "rehearsal_source"},
        "source_schema_sha256": "schema-digest",
        "source_data": {},
        "plan_fingerprint": "plan-digest",
    }
    declared = {
        "principal": "declared_reader@localhost",
        "source_database": "rehearsal_source",
        "privileges": ["SELECT"],
    }
    evidence_path = tmp_path / "principal.json"
    evidence_path.write_text(json.dumps(declared), encoding="utf-8")
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    runtime = runner.SeparateDatabaseConfig(
        runner.DatabaseDescriptor(
            "source-read", "rehearsal_source",
            runner.DatabaseConfig("host", 3306, "reader", "secret"),
        ),
        runner.DatabaseDescriptor(
            "candidate-write", "rehearsal_candidate",
            runner.DatabaseConfig("host", 3306, "writer", "secret"),
        ),
    )
    live = runner.SourcePrincipalEvidence(
        principal="live_reader@localhost",
        source_database="rehearsal_source",
        privileges=frozenset({"SELECT"}),
    )
    monkeypatch.setattr(runner, "build_plan", lambda *_: plan)
    monkeypatch.setattr(
        runner, "inspect_source_read_only_principal", lambda *_: live
    )

    with pytest.raises(runner.UpgradeBlocked, match="does not match"):
        runner.run_source_safety_preflight(
            runtime,
            "rehearsal_source",
            "rehearsal_candidate",
            evidence_path,
            token_path,
            tmp_path / "receipts",
            mode="backup",
        )


def test_recover_interrupted_switch_reports_restart_without_mutating_config(
    tmp_path
) -> None:
    environment = tmp_path / ".env"
    environment.write_text("DB_DATABASE=rehearsal_candidate\n", encoding="utf-8")
    switch_receipt = tmp_path / "switch.json"
    before = runner._sha256_bytes(b"DB_DATABASE=rehearsal_source\n")
    after = runner._sha256_file(environment)
    runner.write_receipt(switch_receipt, {
        "status": "switched",
        "before_sha256": before,
        "after_sha256": after,
    })

    result = runner.recover_interrupted_switch(
        environment, switch_receipt, tmp_path / "receipts"
    )

    assert result["state"] == "switched_requires_restart"
    assert environment.read_text(encoding="utf-8") == (
        "DB_DATABASE=rehearsal_candidate\n"
    )


def test_descriptor_runtime_rejects_shared_source_candidate_principal(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("PRESERVE_TEST_PASSWORD", "not-recorded")
    source_path = tmp_path / "source.json"
    candidate_path = tmp_path / "candidate.json"
    source_path.write_text(json.dumps({
        "contract": "preserve-data/database-descriptor/v1",
        "role": "source-read",
        "database": "union_db",
        "host": "127.0.0.1",
        "port": 3306,
        "user": "shared_principal",
        "password_env": "PRESERVE_TEST_PASSWORD",
    }), encoding="utf-8")
    candidate_path.write_text(json.dumps({
        "contract": "preserve-data/database-descriptor/v1",
        "role": "candidate-write",
        "database": "rehearsal_candidate",
        "host": "127.0.0.1",
        "port": 3306,
        "user": "shared_principal",
        "password_env": "PRESERVE_TEST_PASSWORD",
    }), encoding="utf-8")

    with pytest.raises(runner.UpgradeBlocked, match="principals must differ"):
        runner.build_descriptor_runtime(
            source_path, candidate_path, "union_db", "rehearsal_candidate"
        )
