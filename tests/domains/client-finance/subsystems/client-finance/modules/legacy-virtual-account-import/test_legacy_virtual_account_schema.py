from pathlib import Path

from scripts.schema_assembly import load_schema_assembly
from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[7]


def test_legacy_virtual_account_mapping_is_in_fresh_schema_assembly():
    names = {path.name for path in load_schema_assembly().active_artifact_paths}
    assert "225_client_legacy_virtual_accounts.sql" in names


def test_mapping_allows_account_reuse_but_deduplicates_the_same_case_pair():
    sql = (ROOT / "db/schema_parts/225_client_legacy_virtual_accounts.sql").read_text(encoding="utf-8")
    assert "UNIQUE KEY uq_client_legacy_virtual_account_pair (case_no, virtual_account)" in sql
    assert "UNIQUE KEY uq_client_legacy_virtual_account_lookup" not in sql
    assert "KEY idx_client_legacy_virtual_account_lookup (virtual_account, case_no)" in sql


def test_mapping_has_a_published_preserve_data_release():
    manifest = load_migration_release_manifest(
        ROOT / "db/migration_releases/labor_union_2026_09_15_client_legacy_virtual_accounts_v1.json",
        ROOT,
    )
    assert manifest.release_id == (
        "labor-union-client-legacy-virtual-accounts-2026-09-15-v1"
    )
    assert [path.name for path in manifest.schema_paths(ROOT)] == [
        "1042_client_legacy_virtual_accounts.sql"
    ]
    qualification = migration.local_additive_release_qualification(
        manifest.release_id
    )
    assert qualification["schema_artifacts"][0]["descriptor"]["tables"] == {
        "client_legacy_virtual_accounts": {
            "id": {
                "column_type": "bigint",
                "is_nullable": "NO",
                "column_default": None,
                "extra": "auto_increment",
            },
            "case_no": {
                "column_type": "varchar(50)",
                "is_nullable": "NO",
                "column_default": None,
                "extra": "",
            },
            "virtual_account": {
                "column_type": "varchar(14)",
                "is_nullable": "NO",
                "column_default": None,
                "extra": "",
            },
            "source_content_digest": {
                "column_type": "char(64)",
                "is_nullable": "NO",
                "column_default": None,
                "extra": "",
            },
            "source_row": {
                "column_type": "int unsigned",
                "is_nullable": "NO",
                "column_default": None,
                "extra": "",
            },
            "created_by": {
                "column_type": "varchar(100)",
                "is_nullable": "NO",
                "column_default": None,
                "extra": "",
            },
            "created_at": {
                "column_type": "timestamp(6)",
                "is_nullable": "NO",
                "column_default": "current_timestamp(6)",
                "extra": "default_generated",
            },
        }
    }


def test_admin_preview_and_apply_routes_are_registered():
    from api.routes.legacy_virtual_account_import import router

    paths = {route.path for route in router.routes}
    prefix = "/api/v1/admin/client-finance/legacy-virtual-account-workbooks"
    assert f"{prefix}/preview" in paths
    assert f"{prefix}/apply" in paths
