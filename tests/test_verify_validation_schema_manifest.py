"""
File: test_verify_validation_schema_manifest.py
Description: 驗證 schema manifest、最終物件與可重建 full release。
"""

from pathlib import Path

from scripts.build_validation_schema_release import (
    DATABASE_TOKEN,
    build_release_text,
    verify_release,
    write_release,
)
from scripts.verify_validation_schema_manifest import (
    expected_database_objects,
    load_manifest,
    schema_part_sort_key,
    verify_database_objects,
    verify_manifest,
)
from scripts.verify_validation_database import _require_disposable_database


def test_checked_in_validation_schema_manifest_matches_current_artifacts():
    assert verify_manifest(load_manifest()) == []


def test_lettered_schema_parts_sort_before_the_next_numeric_part(tmp_path):
    paths = [
        tmp_path / "100_runtime.sql",
        tmp_path / "99b_locks.sql",
        tmp_path / "99a_events.sql",
        tmp_path / "99_matching.sql",
    ]

    assert [path.name for path in sorted(paths, key=schema_part_sort_key)] == [
        "99_matching.sql",
        "99a_events.sql",
        "99b_locks.sql",
        "100_runtime.sql",
    ]


def test_release_declares_the_order_detail_view_and_its_tables():
    expected = expected_database_objects(load_manifest())

    assert "orders" in expected["tables"]
    assert "v_order_details" in expected["views"]
    assert "trg_order_lifecycle_control_events_before_update" in expected["triggers"]


def test_release_final_objects_exclude_part_153_retirement_targets():
    expected = expected_database_objects(load_manifest())

    assert "finance_import_reclassification_events" not in expected["tables"]
    assert "trg_finance_import_reclassification_events_before_update" not in expected["triggers"]
    assert "trg_finance_import_reclassification_events_before_delete" not in expected["triggers"]


def test_database_postcheck_reports_only_missing_declared_objects():
    expected = {
        "tables": {"orders", "clients"},
        "views": {"v_order_details"},
        "triggers": {"trg_orders_before_update"},
    }
    cursor = _FakeCursor(
        responses=[
            [("orders",)],
            [("v_order_details",)],
            [],
        ]
    )

    assert verify_database_objects(cursor, "lu_test_schema", expected) == [
        "missing tables: clients",
        "missing triggers: trg_orders_before_update",
    ]


class _FakeCursor:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.executed = []
        self._current_response = []

    def execute(self, statement, parameters):
        self.executed.append((statement, parameters))
        self._current_response = next(self._responses)

    def fetchall(self):
        return self._current_response


def test_full_release_is_reproducible_and_uses_a_database_token(tmp_path):
    manifest = load_manifest()
    output_path = tmp_path / "validation_schema.sql"

    assert write_release(manifest, output_path) == output_path
    assert verify_release(manifest, output_path) == []
    release_text = output_path.read_text(encoding="utf-8")
    assert DATABASE_TOKEN in release_text
    assert "CREATE OR REPLACE VIEW v_order_details" in release_text
    assert release_text == build_release_text(manifest)


def test_database_postcheck_accepts_only_disposable_database_names():
    assert _require_disposable_database("lu_test_validation_v1") == "lu_test_validation_v1"

    try:
        _require_disposable_database("union_db_candidate_20260803_v5")
    except ValueError as error:
        assert str(error) == "database must start with lu_test_"
    else:
        raise AssertionError("candidate database must not be accepted")
