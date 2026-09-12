import json
from pathlib import Path

import pytest

from scripts import backfill_twins_payroll_rate_snapshots as backfill
from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_09_11_twins_payroll_policy_v1.json"


def test_twins_payroll_release_is_registered_and_exact():
    manifest = load_migration_release_manifest(MANIFEST, ROOT)
    descriptors = manifest.owned_object_descriptors(ROOT)
    descriptor = descriptors["1037_twins_payroll_policy.sql"]
    assembly = json.loads((ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json").read_text(encoding="utf-8"))

    assert manifest.schema_artifacts[0].data_effect == "system_seed"
    assert manifest.schema_artifacts[1].artifact.name == (
        "1038_twins_payroll_order_details_view.sql"
    )
    assert manifest.backfills[0].backfill_id == "twins-payroll-rate-snapshots-v1"
    assert migration.DEFAULT_RELEASE_MANIFESTS[-1] == MANIFEST.name
    assert set(descriptor["parent_columns"]) == {
        "payroll_rate_policies", "assignment_payroll_rate_snapshots",
        "case_architecture_bootstrap_events", "case_payroll_rate_policy_snapshots",
    }
    assert "db/schema_parts/220_twins_payroll_policy.sql" in assembly["active_bootstrap"]
    assert "db/schema_parts/221_twins_payroll_order_details_view.sql" in assembly["active_bootstrap"]
    assert descriptors["1038_twins_payroll_order_details_view.sql"]["views"] == {
        "v_order_details": {
            "definition_sha256": "ab3ef0e5c827433b3b9b3f7d66e5ad5c84ad0f57d4b0f61d898fbdb290d3a0dd"
        }
    }


def test_twins_seed_verification_preserves_every_existing_policy(monkeypatch):
    source_rows = [{
        "policy_version": "approved-rates-v1",
        "policy_kind": "citizen",
        "hourly_rate_ntd": 300,
        "effective_from": "1900-01-01",
        "effective_until": None,
        "created_at": "2026-01-01T00:00:00",
    }]
    candidate_rows = list(source_rows)

    def policy_rows(_config, database, *, exclude_twins_policy):
        assert exclude_twins_policy is (database == "candidate")
        return candidate_rows if database == "candidate" else source_rows

    monkeypatch.setattr(migration, "_payroll_rate_policy_rows", policy_rows)
    monkeypatch.setattr(
        migration,
        "_verify_twins_payroll_policy_seed",
        lambda *_args: {"policy_kind": "twins", "hourly_rate_ntd": 450},
    )

    result = migration._verify_twins_payroll_policy_seed_preserves_source(
        object(), "source", "candidate"
    )
    assert result["preserved_source_row_count"] == 1
    assert result["seeded_policy"]["hourly_rate_ntd"] == 450

    candidate_rows = [{**source_rows[0], "hourly_rate_ntd": 301}]
    with pytest.raises(migration.UpgradeBlocked, match="rows changed"):
        migration._verify_twins_payroll_policy_seed_preserves_source(
            object(), "source", "candidate"
        )


class _Cursor:
    def __init__(self, row):
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _sql, _parameters):
        return None

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, row):
        self._cursor = _Cursor(row)

    def cursor(self):
        return self._cursor

    def close(self):
        return None


class _Config:
    def __init__(self, row):
        self._connection = _Connection(row)

    def connect(self, database):
        assert database == "lu_test_twins"
        return self._connection


def test_twins_payroll_post_schema_verification_requires_canonical_seed():
    verification_id = "twins-payroll-policy-enums-and-approved-rate-exact"
    validators = migration._post_schema_verification_validators(
        {
            "1037_twins_payroll_policy.sql": "exact",
            "1038_twins_payroll_order_details_view.sql": "exact",
        },
        config=_Config({
            "hourly_rate_ntd": 450,
            "effective_from": "1900-01-01",
            "effective_until": None,
        }),
        candidate="lu_test_twins",
    )

    assert validators[verification_id]()["approved_twins_policy"]["hourly_rate_ntd"] == 450

    invalid = migration._post_schema_verification_validators(
        {
            "1037_twins_payroll_policy.sql": "exact",
            "1038_twins_payroll_order_details_view.sql": "exact",
        },
        config=_Config({
            "hourly_rate_ntd": 451,
            "effective_from": "1900-01-01",
            "effective_until": None,
        }),
        candidate="lu_test_twins",
    )
    with pytest.raises(migration.UpgradeBlocked, match="not canonical"):
        invalid[verification_id]()


def test_twins_view_replacement_accepts_only_the_known_predecessor_or_target(
    monkeypatch,
):
    descriptor = migration.RELEASE_MANIFEST.descriptors[
        "1038_twins_payroll_order_details_view.sql"
    ]
    view = [{"table_name": "v_order_details", "view_definition": "definition"}]

    monkeypatch.setattr(
        migration,
        "_view_definition_digest",
        lambda _definition: "4d8fc34c1d50b85d0cd426a0ce3f5fc9d1eee8eede8d6c46943e4cae94577aba",
    )
    assert migration._twins_payroll_order_details_view_state(view, descriptor) == "absent"
    monkeypatch.setattr(
        migration,
        "_view_definition_digest",
        lambda _definition: descriptor["views"]["v_order_details"]["definition_sha256"],
    )
    assert migration._twins_payroll_order_details_view_state(view, descriptor) == "exact"
    monkeypatch.setattr(migration, "_view_definition_digest", lambda _definition: "0" * 64)
    assert migration._twins_payroll_order_details_view_state(view, descriptor) == "drift"


def test_backfill_inserts_only_missing_twin_assignment_snapshots(monkeypatch):
    twin_payload = {"特殊計費:胎數": "雙胞胎"}
    monkeypatch.setattr(
        backfill,
        "_load_bound_beclass_rows",
        lambda *_args, **_kwargs: (
            {"case_no": "TW-1", "survey_details": twin_payload},
        ),
    )
    monkeypatch.setattr(
        backfill,
        "_load_case_rates",
        lambda *_args, **_kwargs: {
            "TW-1": {
                "policy_version": "approved-rates-v1",
                "policy_kind": "twins",
                "hourly_rate_ntd": 450,
            }
        },
    )
    monkeypatch.setattr(
        backfill,
        "_load_assignment_rates",
        lambda *_args, **_kwargs: (
            {"case_no": "TW-1", "assignment_id": 7, "hourly_rate_ntd": None},
            {
                "case_no": "TW-1",
                "assignment_id": 8,
                "hourly_rate_ntd": 450,
                "policy_kind": "citizen",
            },
        ),
    )

    result = backfill._build_plan(
        object(), database="lu_test_twins", server="mysql", lock=False
    )

    assert result["unresolved"] == []
    assert result["insertions"] == [
        {
            "assignment_id": 7,
            "case_no": "TW-1",
            "policy_version": "approved-rates-v1",
            "policy_kind": "twins",
            "hourly_rate_ntd": 450,
            "source_identity_status": "twins-preserve-backfill:case-policy",
        }
    ]


def test_backfill_fails_closed_for_existing_non_450_snapshot(monkeypatch):
    monkeypatch.setattr(
        backfill,
        "_load_bound_beclass_rows",
        lambda *_args, **_kwargs: (
            {"case_no": "TW-1", "survey_details": {"特殊計費:胎數": "雙胞胎"}},
        ),
    )
    monkeypatch.setattr(
        backfill,
        "_load_case_rates",
        lambda *_args, **_kwargs: {
            "TW-1": {
                "policy_version": "legacy",
                "policy_kind": "citizen",
                "hourly_rate_ntd": 300,
            }
        },
    )
    monkeypatch.setattr(
        backfill,
        "_load_assignment_rates",
        lambda *_args, **_kwargs: (
            {"case_no": "TW-1", "assignment_id": 7, "hourly_rate_ntd": 300},
        ),
    )

    result = backfill._build_plan(
        object(), database="lu_test_twins", server="mysql", lock=True
    )

    assert result["insertions"] == []
    assert result["unresolved"] == [
        "TW-1:assignment_7_rate_not_450",
        "TW-1:case_rate_snapshot_not_twins_450",
    ]


def test_candidate_runner_executes_declared_backfill_dry_apply_verify(
    tmp_path, monkeypatch
):
    calls = []

    class Completed:
        returncode = 0

    def run(command, **_kwargs):
        mode = next(
            value for value in ("dry-run", "apply", "verify")
            if f"--{value}" in command
        )
        receipt_path = Path(command[command.index("--receipt-path") + 1])
        status = {
            "dry-run": "planned", "apply": "committed", "verify": "verified",
        }[mode]
        migration.write_receipt(
            receipt_path,
            {
                "contract": backfill.RECEIPT_CONTRACT,
                "mode": mode,
                "database": "lu_test_candidate",
                "receipt_status": status,
                "dataset_fingerprint": mode,
            },
        )
        calls.append(mode)
        return Completed()

    monkeypatch.setattr(
        migration,
        "_candidate_preddl_dump",
        lambda *_args, **_kwargs: {
            "path": str(tmp_path / "backup.sql"), "sha256": "a" * 64, "size": 1,
        },
    )
    monkeypatch.setattr(migration.subprocess, "run", run)

    receipts = migration._run_manifest_backfills(
        migration.DatabaseConfig("127.0.0.1", 3306, "user", "password"),
        "lu_test_candidate",
        tmp_path / "operation.json",
        mysql_container=None,
    )

    assert calls == ["dry-run", "apply", "verify"]
    assert receipts[0]["backfill_id"] == "twins-payroll-rate-snapshots-v1"
    assert receipts[0]["phases"]["verify"]["receipt_status"] == "verified"


def test_candidate_verification_preserves_old_snapshots_and_allows_only_marked_addition(
    monkeypatch,
):
    original = {
        "assignment_id": 7,
        "policy_version": "custom-case-v1",
        "policy_kind": "citizen",
        "hourly_rate_ntd": 450,
        "source_identity_status": "legacy",
        "created_at": "same",
    }
    added = {
        "assignment_id": 8,
        "policy_version": "approved-rates-v1",
        "policy_kind": "twins",
        "hourly_rate_ntd": 450,
        "source_identity_status": "twins-preserve-backfill:case-policy",
        "created_at": "new",
    }

    monkeypatch.setattr(
        migration,
        "_assignment_payroll_snapshot_rows",
        lambda _config, database: [original]
        if database == "source"
        else [original, added],
    )

    class AssignmentCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _sql, _parameters):
            return None

        def fetchall(self):
            return ({"id": 8, "case_no": "TW-1"},)

    class AssignmentConnection:
        def cursor(self):
            return AssignmentCursor()

        def close(self):
            return None

    class AssignmentConfig:
        def connect(self, database):
            assert database == "candidate"
            return AssignmentConnection()

    result = migration._verify_twins_assignment_snapshot_backfill(
        AssignmentConfig(),
        "source",
        "candidate",
        {"twin_cases": ["TW-1"]},
    )

    assert result["added_ids"] == [8]
    changed = {**original, "hourly_rate_ntd": 451}
    monkeypatch.setattr(
        migration,
        "_assignment_payroll_snapshot_rows",
        lambda _config, database: [original]
        if database == "source"
        else [changed, added],
    )
    with pytest.raises(migration.UpgradeBlocked, match="preserved.*changed"):
        migration._verify_twins_assignment_snapshot_backfill(
            AssignmentConfig(), "source", "candidate", {"twin_cases": ["TW-1"]}
        )
