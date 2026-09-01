"""Preserve-data contract for Historical Orders count-based accounting roots."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.migration.rehearsal_runtime import (
    CandidateReadSmokePort,
    CandidateRuntimeConfig,
)
from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = "1028_historical_service_accounting.sql"
MANIFEST_NAME = "labor_union_2026_09_01_historical_service_accounting_v1.json"
NORMAL_STATUS_ENUM = "enum('待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消')"


def _predecessor_snapshot(status_enum: str = NORMAL_STATUS_ENUM):
    statuses = "'待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消'"
    return {
        "columns": [{
            "table_name": "orders",
            "column_name": "status",
            "column_type": status_enum,
            "is_nullable": "NO",
            "column_default": "洽談中",
            "extra": "",
        }],
        "indexes": [],
        "constraints": [
            {
                "table_name": "order_lifecycle_state_events",
                "constraint_name": f"chk_order_lifecycle_state_event_{name}",
                "constraint_type": "CHECK",
                "check_clause": f"{name} IN ({statuses})",
            }
            for name in ("before_status", "after_status")
        ],
        "key_columns": [],
        "foreign_keys": [],
        "triggers": [],
        "show_create_tables": {},
        "views": [],
    }


def test_release_is_selected_hash_bound_and_matches_canonical_descriptor():
    assert migration.DEFAULT_RELEASE_MANIFESTS.count(MANIFEST_NAME) == 1
    manifest = load_migration_release_manifest(
        ROOT / "db/migration_releases" / MANIFEST_NAME,
        ROOT,
    )
    assert manifest.schema_paths(ROOT) == (
        (ROOT / "db/schema_parts" / ARTIFACT).resolve(),
    )
    released = manifest.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert released["parent_columns"] == canonical["parent_columns"]
    assert released["tables"] == {
        table: set(columns) for table, columns in canonical["tables"].items()
    }


def test_post_schema_verification_is_bound_to_the_released_artifact():
    contract = next(
        item
        for item in migration.RELEASE_MANIFEST.verification_contracts
        if item.verification_id
        == "historical-service-accounting-owned-objects"
    )
    validators = migration._post_schema_verification_validators(
        {ARTIFACT: "exact"}
    )

    receipts = migration.run_manifest_verifications(
        (contract,), phase="post-schema", validators=validators
    )

    assert receipts[0].status == "passed"
    assert receipts[0].evidence["owned_objects"] == {ARTIFACT: "exact"}
    with pytest.raises(migration.UpgradeBlocked):
        migration._post_schema_verification_validators(
            {ARTIFACT: "drift"}
        )[contract.verification_id]()


class _Cursor:
    def __init__(self, row):
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql):
        assert "歷史訂單－服務完成" in sql

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, row):
        self._row = row

    def cursor(self):
        return _Cursor(self._row)

    def close(self):
        return None


class _DatabaseConfig:
    def __init__(self, row):
        self._row = row

    def connect(self, database):
        assert database == "candidate"
        return _Connection(self._row)


def _smoke(row):
    return CandidateReadSmokePort(CandidateRuntimeConfig(
        ROOT,
        18022,
        18522,
        30,
        {},
        _DatabaseConfig(row),
        "candidate",
        ROOT / "scratch",
    ))


def test_historical_accounting_smoke_resolves_a_supported_read_path():
    smoke = _smoke({"case_no": "115000019"})

    assert smoke._path_for("historical-service-accounting-query") == (
        "/api/v1/orders/115000019/historical-service-accounting"
    )
    assert smoke._accepted_statuses(
        "historical-service-accounting-query"
    ) == frozenset({200, 404})


def test_historical_accounting_smoke_has_an_explicit_empty_dataset_path():
    assert _smoke(None)._path_for("historical-service-accounting-query") == (
        "/api/v1/orders/__migration_empty_historical_case__/"
        "historical-service-accounting"
    )


def test_only_exact_normal_lifecycle_predecessor_is_upgradeable():
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    assert migration.local_additive_descriptor_state(
        _predecessor_snapshot(), descriptor, ARTIFACT
    ) == "absent"
    assert migration.local_additive_descriptor_state(
        _predecessor_snapshot(NORMAL_STATUS_ENUM.replace("訂單取消", "其他")),
        descriptor,
        ARTIFACT,
    ) == "drift"
