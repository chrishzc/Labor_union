"""Static contract for the registered 1017 additive Client release."""

from pathlib import Path
import json
import inspect

from infrastructure.mysql.client_hcm_correction_adapter import MySqlClientHcmCorrectionAdapter
from infrastructure.mysql.orders_hcm_correction_adapter import MySqlOrdersHcmCorrectionAdapter
from scripts import migrate_preserved_database_additive_schema as migration


ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "db/schema_parts/1017_client_hcm_correction_versioning.sql"
DESCRIPTOR = ROOT / "db/migration_releases/labor_union_2026_08_30_client_hcm_correction_versioning_v1.descriptors.json"
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_08_30_client_hcm_correction_versioning_v1.json"


def test_1017_is_client_owned_and_does_not_add_order_service_type() -> None:
    sql = SQL.read_text(encoding="utf-8")
    assert "client_hcm_correction_version" in sql
    assert "client_hcm_correction_events" in sql
    assert "client_hcm_correction_receipts" in sql
    assert "orders.service_type" not in sql
    assert "ALTER TABLE orders" not in sql


def test_1017_descriptor_is_hash_bound_to_registered_release() -> None:
    descriptor = json.loads(DESCRIPTOR.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert descriptor["release_id"] == manifest["release_id"]
    assert manifest["backfills"] == []
    owned = descriptor["descriptors"]["1017_client_hcm_correction_versioning.sql"]
    canonical = migration._canonical_artifact_descriptor(
        "1017_client_hcm_correction_versioning.sql"
    )
    assert set(canonical["parent_columns"]["clients"]) == {
        "client_hcm_correction_version"
    }
    assert owned["foreign_keys"][
        "client_hcm_correction_events.fk_client_hcm_correction_event_case"
    ]["referenced_table"] == "clients"


def test_owner_adapters_borrow_caller_transaction() -> None:
    for adapter in (MySqlClientHcmCorrectionAdapter, MySqlOrdersHcmCorrectionAdapter):
        source = inspect.getsource(adapter)
        assert ".commit(" not in source
        assert ".rollback(" not in source


def test_case_import_repository_delegates_owner_mutations() -> None:
    source = (ROOT / "infrastructure/mysql/hcm_resubmission_repository.py").read_text(encoding="utf-8")
    assert "apply_in_current_uow" in source
    assert "UPDATE clients" not in source
    assert "UPDATE orders" not in source
