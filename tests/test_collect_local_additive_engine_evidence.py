"""
File: test_collect_local_additive_engine_evidence.py
Description: 驗證final engine evidence producer的DB邊界、release prefix、全表資料保留與atomic scratch輸出。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import collect_local_additive_engine_evidence as collector
from scripts import migrate_preserved_database_additive_schema as migration


def test_database_boundary_accepts_only_distinct_development_lu_test_targets() -> None:
    collector._require_database_boundary(
        "lu_test_source", "lu_test_candidate", "lu_test_fresh", "development"
    )
    for values in (
        ("union_db", "lu_test_candidate", "lu_test_fresh", "development"),
        ("lu_test_source", "lu_test_source", "lu_test_fresh", "development"),
        ("lu_test_source", "lu_test_candidate", "lu_test_fresh", "production"),
    ):
        with pytest.raises(collector.EngineEvidenceError):
            collector._require_database_boundary(*values)


def test_release_boundary_defers_only_missing_parent_table_dependency(
    monkeypatch
) -> None:
    entries = (
        {"release_id": "baseline", "artifact": {"name": "1003.sql"}, "descriptor": {}},
        {"release_id": "target", "artifact": {"name": "1004.sql"}, "descriptor": {}},
        {
            "release_id": "future",
            "artifact": {"name": "1005.sql"},
            "descriptor": {"parent_columns": {"parent_table": {"column": {}}}},
        },
    )
    states = iter(("exact", "absent", "drift"))
    monkeypatch.setattr(migration, "_local_ordered_upgrade_entries", lambda: entries)
    monkeypatch.setattr(
        migration,
        "local_additive_target_state",
        lambda *_args, **_kwargs: {"state": next(states)},
    )

    assert collector._verify_release_boundary(
        SimpleNamespace(),
        "lu_test_source",
        "target",
        applied=False,
        snapshot={"columns": [{"table_name": "base_table"}]},
    ) == ["exact", "absent", "dependency_pending"]


def test_release_boundary_rejects_real_future_drift(monkeypatch) -> None:
    entries = (
        {"release_id": "baseline", "artifact": {"name": "1003.sql"}, "descriptor": {}},
        {"release_id": "target", "artifact": {"name": "1004.sql"}, "descriptor": {}},
        {
            "release_id": "future",
            "artifact": {"name": "1005.sql"},
            "descriptor": {"parent_columns": {"parent_table": {"column": {}}}},
        },
    )
    states = iter(("exact", "absent", "drift"))
    monkeypatch.setattr(migration, "_local_ordered_upgrade_entries", lambda: entries)
    monkeypatch.setattr(
        migration,
        "local_additive_target_state",
        lambda *_args, **_kwargs: {"state": next(states)},
    )

    with pytest.raises(collector.EngineEvidenceError, match="future release state"):
        collector._verify_release_boundary(
            SimpleNamespace(),
            "lu_test_source",
            "target",
            applied=False,
            snapshot={"columns": [{"table_name": "parent_table"}]},
        )


def test_fresh_release_boundary_requires_target_but_not_preserve_prefix(
    monkeypatch,
) -> None:
    entries = (
        {"release_id": "preserve-only", "artifact": {"name": "1003.sql"}, "descriptor": {}},
        {"release_id": "target", "artifact": {"name": "1004.sql"}, "descriptor": {}},
        {"release_id": "future", "artifact": {"name": "1005.sql"}, "descriptor": {}},
    )
    states = iter(("absent", "exact", "absent"))
    monkeypatch.setattr(migration, "_local_ordered_upgrade_entries", lambda: entries)
    monkeypatch.setattr(
        migration,
        "local_additive_target_state",
        lambda *_args, **_kwargs: {"state": next(states)},
    )

    assert collector._verify_release_boundary(
        SimpleNamespace(),
        "lu_test_fresh",
        "target",
        applied=True,
        snapshot={"columns": []},
        require_predecessor_prefix=False,
    ) == ["absent", "exact", "absent"]


def test_fresh_release_boundary_still_rejects_nonexact_target(monkeypatch) -> None:
    entries = (
        {"release_id": "preserve-only", "artifact": {"name": "1003.sql"}, "descriptor": {}},
        {"release_id": "target", "artifact": {"name": "1004.sql"}, "descriptor": {}},
    )
    states = iter(("absent", "drift"))
    monkeypatch.setattr(migration, "_local_ordered_upgrade_entries", lambda: entries)
    monkeypatch.setattr(
        migration,
        "local_additive_target_state",
        lambda *_args, **_kwargs: {"state": next(states)},
    )

    with pytest.raises(collector.EngineEvidenceError, match="target release"):
        collector._verify_release_boundary(
            SimpleNamespace(),
            "lu_test_fresh",
            "target",
            applied=True,
            snapshot={"columns": []},
            require_predecessor_prefix=False,
        )


def test_all_canonical_table_projection_preserves_source_rows_and_zero_new_tables(
    monkeypatch
) -> None:
    snapshots = {
        "lu_test_source": {
            "columns": [
                {"table_name": "orders", "column_name": "id"},
                {"table_name": "orders", "column_name": "status"},
            ]
        },
        "lu_test_candidate": {
            "columns": [
                {"table_name": "orders", "column_name": "id"},
                {"table_name": "orders", "column_name": "status"},
                {"table_name": "orders", "column_name": "new_column"},
                {"table_name": "new_table", "column_name": "id"},
            ]
        },
    }

    def projection(_config, database, table, columns):
        if table == "orders":
            return {"columns": columns, "row_count": 2, "rows_sha256": "a" * 64}
        assert database == "lu_test_candidate" and table == "new_table"
        return {"columns": columns, "row_count": 0, "rows_sha256": "b" * 64}

    monkeypatch.setattr(migration, "_table_projection_evidence", projection)

    source, candidate = collector._canonical_row_preservation(
        SimpleNamespace(),
        "lu_test_source",
        "lu_test_candidate",
        frozenset({"orders", "new_table", "future_table"}),
        snapshots["lu_test_source"],
        snapshots["lu_test_candidate"],
    )

    assert source == candidate
    assert source["data_row_counts"] == {
        "future_table": 0,
        "new_table": 0,
        "orders": 2,
    }
    assert set(source["data_fingerprints"]) == set(source["data_row_counts"])


def test_atomic_bundle_writes_only_new_files_below_scratch(monkeypatch, tmp_path) -> None:
    scratch = tmp_path / "scratch"
    monkeypatch.setattr(collector, "SCRATCH_ROOT", scratch)
    output = scratch / "task96"
    bundle = {
        "metadata_backup": {"contract": "metadata"},
        "fresh_bootstrap": {"contract": "fresh"},
        "preserve_data_candidate": {"contract": "preserve"},
    }

    paths = collector._write_evidence_bundle(bundle, output, "1006_example.sql")

    assert set(paths) == set(bundle)
    assert all(path.parent == output for path in paths.values())
    assert json.loads(paths["metadata_backup"].read_text(encoding="utf-8")) == {
        "contract": "metadata"
    }
    with pytest.raises(collector.EngineEvidenceError, match="already exists"):
        collector._write_evidence_bundle(bundle, output, "1006_example.sql")


def test_atomic_bundle_rolls_back_all_targets_when_link_fails(
    monkeypatch, tmp_path
) -> None:
    scratch = tmp_path / "scratch"
    monkeypatch.setattr(collector, "SCRATCH_ROOT", scratch)
    output = scratch / "task96"
    bundle = {
        "metadata_backup": {"contract": "metadata"},
        "fresh_bootstrap": {"contract": "fresh"},
        "preserve_data_candidate": {"contract": "preserve"},
    }
    original_link = collector.os.link
    calls = 0

    def fail_second_link(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated link failure")
        original_link(source, target)

    monkeypatch.setattr(collector.os, "link", fail_second_link)

    with pytest.raises(OSError, match="simulated link failure"):
        collector._write_evidence_bundle(bundle, output, "1006_example.sql")

    assert list(output.glob("1006_example.*.json")) == []


def test_final_operation_requires_exact_release_artifact_and_server_identity(
    monkeypatch, tmp_path
) -> None:
    operation = {
        "status": "verified",
        "release_id": "wrong-release",
        "artifact_name": "1006_example.sql",
        "artifact_names": ["1006_example.sql"],
        "release_fingerprint": "a" * 64,
        "source": {
            "database": "lu_test_source",
            "host": "127.0.0.1",
            "port": 3306,
            "server": "server-1",
            "version": "8.0",
        },
        "candidate": {
            "database": "lu_test_candidate",
            "host": "127.0.0.1",
            "port": 3306,
            "server": "server-1",
            "version": "8.0",
        },
        "candidate_database": "lu_test_candidate",
        "source_data": {},
        "candidate_data": {},
    }
    monkeypatch.setattr(migration, "read_receipt", lambda _path: operation)
    monkeypatch.setattr(migration, "_table_evidence", lambda *_args: {})

    with pytest.raises(collector.EngineEvidenceError, match="release identity"):
        collector._require_final_operation(
            SimpleNamespace(),
            "lu_test_source",
            "lu_test_candidate",
            tmp_path / "operation.json",
            operation["source"],
            operation["candidate"],
            "expected-release",
            "1006_example.sql",
            "a" * 64,
        )


def test_candidate_dump_must_be_created_after_final_verification() -> None:
    operation = {
        "status": "verified",
        "verified_at": "2026-08-28T01:00:00+00:00",
        "candidate": {"database": "lu_test_candidate", "server": "server-1"},
    }
    receipt = {
        "kind": "source_backup",
        "created_at": "2026-08-28T00:59:59+00:00",
        "database": "lu_test_candidate",
        "server": "server-1",
        "sha256": "b" * 64,
        "exit_code": 0,
    }

    with pytest.raises(collector.EngineEvidenceError, match="final verification"):
        collector._require_dump_binding(
            {"database": "lu_test_candidate", "server": "server-1", "sha256": "b" * 64},
            receipt,
            operation,
            role="candidate",
        )


def test_fresh_zero_rows_checks_only_tables_created_by_target(monkeypatch) -> None:
    snapshot = {
        "columns": [
            {"table_name": "government_payers", "column_name": "id"},
            {"table_name": "target_events", "column_name": "id"},
        ]
    }

    def projection(_config, _database, table, _columns):
        return {"row_count": 1 if table == "government_payers" else 0}

    monkeypatch.setattr(migration, "_table_projection_evidence", projection)

    collector._require_fresh_zero_rows(
        SimpleNamespace(),
        "lu_test_fresh",
        frozenset({"target_events"}),
        snapshot,
    )
