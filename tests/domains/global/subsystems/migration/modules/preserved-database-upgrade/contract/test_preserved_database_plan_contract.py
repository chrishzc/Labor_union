"""
File: test_preserved_database_plan_contract.py
Description: 驗證 preserve-data plan、release catalog 與候選升級的安全契約。
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from infrastructure.migration.maintenance import issue_maintenance_window_token
from infrastructure.migration.rehearsal_runtime import (
    CandidateReadSmokePort,
    CandidateRuntimeConfig,
    EphemeralCandidateRestartPort,
)
from scripts import migrate_preserved_database_additive_schema as runner
from scripts.schema_assembly import load_schema_assembly


def test_runtime_release_manifests_are_in_preserve_data_catalog() -> None:
    required_manifests = {
        "labor_union_2026_08_12_line_stage13_strict_v1.json",
        "labor_union_2026_08_11_provisional_registration_case_issue_strict_v1.json",
        "labor_union_2026_08_11_line_stage11_v1.json",
        "labor_union_2026_08_11_line_stage12_v1.json",
    }

    assert required_manifests <= set(runner.DEFAULT_RELEASE_MANIFESTS)


def test_current_notification_schema_parts_are_always_in_preserve_data_chain() -> None:
    """A fresh-only notification part would make local upgrades silently incomplete."""
    notification_parts = {
        path.name
        for path in load_schema_assembly().active_artifact_paths
        if path.name.split("_", 1)[0].isdigit()
        and 203 <= int(path.name.split("_", 1)[0]) <= 208
    }
    preserve_parts = {path.name for path in runner.SCHEMA_PARTS}

    assert notification_parts <= preserve_parts


def test_source_backup_includes_manifest_required_event_objects(
    tmp_path, monkeypatch
) -> None:
    observed = {}

    def run(command, *, stdout, stderr, env, check):
        del stderr, env, check
        observed["command"] = command
        stdout.write(b"-- deterministic test dump\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        runner,
        "server_identity",
        lambda *_: {"server": "test", "version": "8.0"},
    )
    monkeypatch.setattr(runner.subprocess, "run", run)

    runner.create_source_dump(
        runner.DatabaseConfig("127.0.0.1", 3306, "tester", "secret"),
        "lu_test_source",
        tmp_path / "source.sql",
        tmp_path / "source-backup.json",
    )

    assert "--events" in observed["command"]


def test_every_catalog_descriptor_and_schema_artifact_has_exact_hash() -> None:
    release_root = Path(__file__).resolve().parents[8]

    for manifest_name in runner.DEFAULT_RELEASE_MANIFESTS:
        manifest_path = release_root / "db" / "migration_releases" / manifest_name
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = [manifest["descriptor_artifact"], *manifest["artifacts"]]
        for artifact in artifacts:
            artifact_path = release_root / artifact["relative_path"]
            actual_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            assert actual_hash == artifact["sha256"], artifact["name"]


def test_mysql_time_value_has_a_stable_canonical_representation() -> None:
    payload = runner._canonical_json({"service_end_time": timedelta(hours=17)})

    assert json.loads(payload) == {
        "service_end_time": {"timedelta_microseconds": 61_200_000_000}
    }


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
    for evidence_name in ("source.json", "candidate.json", "principal.json", "token.json"):
        (tmp_path / evidence_name).write_text("{}\n", encoding="utf-8")
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


def test_default_catalog_does_not_replay_historical_post_schema_backfills(
    tmp_path, monkeypatch
) -> None:
    receipt_path = tmp_path / "operation.json"
    runner.write_receipt(receipt_path, {
        "status": "schema_applied", "candidate_database": "candidate",
    })
    monkeypatch.setattr(
        runner, "server_identity", lambda *_: {"database": "candidate"}
    )
    monkeypatch.setattr(
        runner,
        "_candidate_preddl_dump",
        lambda *_args, **_kwargs: pytest.fail("legacy backfill must not run"),
    )

    result = runner.run_candidate_post_schema(
        runner.DatabaseConfig("host", 1, "user", "password"),
        "source", "candidate", receipt_path,
    )

    assert result["status"] == "backfilled"
    assert result["backfills"] == ()


def test_rehearsal_worker_starts_as_project_module(tmp_path) -> None:
    config = CandidateRuntimeConfig(
        Path.cwd(), 18022, 18522, 30, {}, object(), "candidate", tmp_path,
    )

    command = EphemeralCandidateRestartPort(config)._worker_command()

    assert command[1:3] == ["-m", "scripts.run_durable_job_worker"]


def test_empty_dataset_is_an_explicit_scheduling_and_payroll_smoke_case(tmp_path) -> None:
    config = CandidateRuntimeConfig(
        Path.cwd(), 18022, 18522, 30, {}, object(), "candidate", tmp_path,
    )
    smoke = CandidateReadSmokePort(config)

    assert smoke._accepted_statuses("scheduling-read") == frozenset({200, 404})
    assert smoke._accepted_statuses("payroll-payables-read") == frozenset({200, 404})


def test_verified_candidate_is_eligible_for_repeat_verification() -> None:
    assert "verified" in runner.VERIFYABLE_CANDIDATE_STATUSES


def test_default_release_catalog_preserves_successors_in_unique_order() -> None:
    artifact_names = tuple(path.name for path in runner.SCHEMA_PARTS)
    assembly = load_schema_assembly()
    assembly_terminal = assembly.active_artifact_paths[-1]

    assert artifact_names.index("209_access_control_totp_root.sql") == (
        artifact_names.index("208_scheduling_rebuild_notification_invalidation.sql") + 1
    )
    assert len(artifact_names) == len(set(artifact_names))
    assert "153_retire_empty_legacy_field_inventory.sql" in artifact_names
    preserve_terminal = runner.SCHEMA_PARTS[-1]
    if preserve_terminal.name != assembly_terminal.name:
        metadata = json.loads(
            (runner.ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json").read_text(
                encoding="utf-8"
            )
        )
        retirement = metadata["retirement_contracts"][
            preserve_terminal.relative_to(runner.ROOT).as_posix()
        ]
        assert retirement["successor"] == assembly_terminal.relative_to(runner.ROOT).as_posix()
    assert runner.RELEASE_MANIFEST.release_id == (
        runner.RELEASE_MANIFEST.manifests[-1].release_id
    )


def test_schema_assembly_release_declares_the_order_details_view_contract() -> None:
    descriptor = runner.RELEASE_MANIFEST.descriptors[
        "999_v_order_details_view.sql"
    ]

    assert descriptor["views"] == {
        "v_order_details": {
            "definition_sha256": "4d8fc34c1d50b85d0cd426a0ce3f5fc9d1eee8eede8d6c46943e4cae94577aba"
        }
    }


def test_owned_view_contract_distinguishes_absent_exact_and_drift(
    monkeypatch,
) -> None:
    descriptor = runner.RELEASE_MANIFEST.descriptors[
        "999_v_order_details_view.sql"
    ]
    expected = descriptor["views"]["v_order_details"]["definition_sha256"]
    views = [{"table_name": "v_order_details", "view_definition": "SELECT 1"}]

    assert runner._descriptor_presence_state(descriptor, {}, set(), []) == "absent"
    monkeypatch.setattr(runner, "_view_definition_digest", lambda _definition: expected)
    assert runner._descriptor_presence_state(descriptor, {}, set(), views) == "exact"
    monkeypatch.setattr(runner, "_view_definition_digest", lambda _definition: "0" * 64)
    assert runner._descriptor_presence_state(descriptor, {}, set(), views) == "drift"


@pytest.mark.parametrize(
    ("manifest_name", "release_id"),
    (
        (
            "labor_union_2026_08_14_wp77_v2.json",
            "labor-union-wp77-2026-08-14-v2",
        ),
        (
            "labor_union_2026_08_14_wp80_v2.json",
            "labor-union-wp80-2026-08-14-v2",
        ),
    ),
)
def test_wp77_and_wp80_manifests_satisfy_strict_v1_loader_contract(
    manifest_name: str, release_id: str,
) -> None:
    manifest_path = runner.ROOT / "db" / "migration_releases" / manifest_name

    manifest = runner.load_migration_release_manifest(manifest_path, runner.ROOT)

    assert manifest.release_id == release_id


def test_default_release_selection_aggregates_successor_requirements() -> None:
    verification_ids = {
        contract.verification_id
        for contract in runner.RELEASE_MANIFEST.verification_contracts
    }

    assert {
        "client-refund-snapshot-owned-objects",
        "government-overpayment-owned-objects",
        "line-staff-self-service-identity-flow-owned-column",
        "government-outbox-intent-type-repair",
        "wp77-owned-objects",
        "wp80-owned-objects",
        "wp90-owned-objects",
        "wp91-partial-case-columns",
        "wp92-client-beclass-binding-columns",
        "wp93-pending-completion-order-status",
    } <= verification_ids
    assert {"api", "architecture-outbox-worker", "line-worker", "streamlit-ui"} <= set(
        runner.RELEASE_MANIFEST.required_restart_targets
    )
    assert {
        "staff-historical-adoption",
        "hcm-invalid-review-outbox",
        "historical-order-adoption-preview",
        "accounts-payable-query",
        "line-staff-self-service-verified-binding",
        "import-warning-tracking-preview",
        "hcm-partial-formal-case",
        "client-beclass-unique-case-binding",
    } <= set(runner.RELEASE_MANIFEST.post_cutover_smoke_ids)


def test_government_outbox_intent_type_repair_is_typed_and_fail_closed() -> None:
    def snapshot(column_type: str) -> dict[str, object]:
        return {"columns": [{
            "table_name": "government_subsidy_outbox",
            "column_name": "intent_type",
            "column_type": column_type,
        }]}

    old_type = runner._enum_column_type(
        runner.GOVERNMENT_OUTBOX_INTENTS_BEFORE_REPAIR
    )
    target_type = runner._enum_column_type(
        runner.GOVERNMENT_OUTBOX_INTENTS_AFTER_REPAIR
    )
    assert runner._government_outbox_intent_type_repair_state(
        snapshot(old_type)
    ) == "absent"
    assert runner._government_outbox_intent_type_repair_state(
        snapshot(target_type)
    ) == "exact"
    assert runner._government_outbox_intent_type_repair_state(
        snapshot("enum('unexpected')")
    ) == "drift"


def test_release_chain_rejects_distinct_artifacts_with_duplicate_ordinals() -> None:
    manifests = (
        SimpleNamespace(
            release_id="release-a",
            schema_paths=lambda _root: (Path("189_a.sql"),),
        ),
        SimpleNamespace(
            release_id="release-b",
            schema_paths=lambda _root: (Path("189_b.sql"),),
        ),
    )

    with pytest.raises(runner.UpgradeBlocked, match="unique and ordered"):
        runner._validate_release_chain(manifests)


def test_client_refund_snapshot_successor_descriptor_is_complete() -> None:
    part = "189_client_refund_recipient_snapshot_local_upgrade.sql"
    descriptor = runner.RELEASE_MANIFEST.descriptors[part]

    assert descriptor["tables"] == {
        "client_refund_recipient_snapshots": {
            "refund_obligation_identity",
            "case_no",
            "bank_code",
            "bank_account",
            "source_kind",
            "created_at",
        }
    }
    assert set(descriptor["triggers"]) == {
        "trg_client_refund_recipient_snapshots_before_update",
        "trg_client_refund_recipient_snapshots_before_delete",
    }
    assert runner._descriptor_presence_state(
        {"tables": {"knowledge_items": ["id", "version"]}, "triggers": []},
        {"knowledge_items": {"id", "version"}},
        set(),
    ) == "exact"


def test_wp72_parent_column_is_required_by_descriptor() -> None:
    descriptor = runner.RELEASE_MANIFEST.descriptors[
        "188_matching_preferences_and_staff_availability.sql"
    ]
    new_tables = {
        table: set(columns)
        for table, columns in descriptor["tables"].items()
        if table != "orders"
    }

    assert runner._descriptor_presence_state(
        descriptor, {**new_tables, "orders": {"case_no"}}, set()
    ) == "partial"
    assert runner._descriptor_presence_state(
        descriptor,
        {**new_tables, "orders": {"case_no", "requires_cooking"}},
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
