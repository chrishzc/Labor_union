"""Protect the additive HCM release and original-workbook reconciliation."""

from pathlib import Path

from openpyxl import Workbook

from domains.case_import.client_import_validation import HCM_REQUIRED_HEADERS
from scripts.backfill_hcm_review_status import load_source_decisions
from scripts.compact_fresh_schema import load_compact_plan
from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


def test_hcm_review_status_release_is_current_and_additive():
    manifest_name = "labor_union_2026_11_06_hcm_review_status_v1.json"
    assert manifest_name in migration.DEFAULT_RELEASE_MANIFESTS
    release_path = migration.ROOT / "db/migration_releases" / manifest_name
    release = load_migration_release_manifest(release_path, migration.ROOT)
    artifact = "1069_hcm_review_status.sql"
    descriptor = release.owned_object_descriptors(migration.ROOT)[artifact]
    assert descriptor["parent_columns"] == migration._canonical_artifact_descriptor(artifact)["parent_columns"]
    assert descriptor["parent_columns"]["clients"]["hcm_review_status"]["is_nullable"] == "YES"
    assert any("`hcm_review_status` enum('符合','不符合')" in step["sql"] for step in load_compact_plan()["steps"])
    statement, = migration.split_sql((migration.ROOT / "db/schema_parts" / artifact).read_text(encoding="utf-8"))
    assert migration._local_classify_statement(statement) == "alter_add_only"


def test_excel_decisions_require_exact_status_and_consistent_source(tmp_path: Path):
    headers = sorted(HCM_REQUIRED_HEADERS)
    paths = []
    for index, cases in enumerate((
        [("115000001", " 符合 "), ("115000002", "不符合"), ("115000003", "待確認")],
        [("115000001", "符合"), ("115000002", "符合"), ("A115004", "不符合")],
    )):
        workbook = Workbook()
        workbook.active.append(headers)
        workbook.create_sheet("Empty").append(headers)
        for case_no, status in cases:
            values = {"查詢序號(案件編號)": case_no, "案件狀態": status}
            workbook.active.append([values.get(header) for header in headers])
        path = tmp_path / f"source-{index}.xlsx"
        workbook.save(path)
        paths.append(path)
    decisions, receipt = load_source_decisions(paths)
    assert decisions == {"115000001": "符合"}
    assert receipt["conflicting_source_cases"] == 1
    assert len(receipt["source_sha256"]) == 2
