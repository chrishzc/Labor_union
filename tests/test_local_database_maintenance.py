"""
File: test_local_database_maintenance.py
Description: 驗證本機保留資料升級的來源選擇、候選替換與失敗保護。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from scripts import update_local_database as update


def test_local_update_rejects_remote_or_production_targets() -> None:
    with pytest.raises(update.LocalDatabaseUpdateError, match="local MySQL"):
        update.validate_local_source(SimpleNamespace(host="db.example.com"), "union_db", {})
    with pytest.raises(update.LocalDatabaseUpdateError, match="production"):
        update.validate_local_source(
            SimpleNamespace(host="127.0.0.1"), "union_db", {"APP_ENV": "production"}
        )


def test_candidate_name_is_stable_and_scoped_to_the_configured_source() -> None:
    now = datetime(2026, 8, 13, 1, 2, 3, tzinfo=timezone.utc)

    assert update.candidate_name("lu_test_dataset", now) == (
        "lu_test_dataset_local_20260813010203"
    )
    assert len(update.candidate_name("a" * 64, now)) == 64


def test_explicit_candidate_name_fails_before_mysql_when_it_exceeds_limit() -> None:
    with pytest.raises(
        update.LocalDatabaseUpdateError,
        match="exceeds MySQL identifier limit",
    ):
        update.validate_candidate_database("lu_test", "a" * 65)


def test_local_update_accepts_the_configured_local_database_name() -> None:
    update.validate_local_source(
        SimpleNamespace(host="127.0.0.1"), "lu_test_dataset", {}
    )


def test_apply_confirms_the_database_configured_in_the_environment(
    tmp_path, monkeypatch
) -> None:
    config = SimpleNamespace(host="127.0.0.1")
    preview = {
        "source_database": "lu_test_dataset",
        "candidate_database": "lu_test_dataset_local_20260813010203",
        "plan": {"status": "ready"},
    }
    captured = {}
    monkeypatch.setattr(
        update.migration,
        "config_from_env",
        lambda _path: (config, "lu_test_dataset"),
    )
    monkeypatch.setattr(update, "candidate_name", lambda source: preview["candidate_database"])
    monkeypatch.setattr(update, "build_preview", lambda *_: preview)
    monkeypatch.setattr(update, "require_mysql_clients", lambda *_: None)
    monkeypatch.setattr(
        update,
        "apply_update",
        lambda _config, _environment, received, _receipt_root, **_options: captured.update(received) or {"status": "completed"},
    )

    result = update.update_local_database(
        environment_file=tmp_path / ".env",
        apply=True,
        confirm_configured_database=True,
    )

    assert result == {"status": "completed"}
    assert captured["source_database"] == "lu_test_dataset"


def test_preview_connection_failure_is_reported_as_a_bounded_error(
    tmp_path, monkeypatch
) -> None:
    config = SimpleNamespace(host="127.0.0.1")
    monkeypatch.setattr(
        update.migration,
        "config_from_env",
        lambda _path: (config, "lu_test_dataset"),
    )
    monkeypatch.setattr(
        update,
        "build_preview",
        lambda *_: (_ for _ in ()).throw(RuntimeError("connection failed")),
    )

    with pytest.raises(update.LocalDatabaseUpdateError, match="preview failed"):
        update.update_local_database(environment_file=tmp_path / ".env")


def test_only_known_idempotent_partials_are_resumable() -> None:
    states = {
        "181_matching_service_date_confirmation.sql": "partial",
        "125_government_subsidy_domain.sql": "partial",
        "161_runtime_monitoring_line_alerts.sql": "absent",
    }

    blocking = update.migration._blocking_schema_states(
        states,
        update.LOCAL_RESUMABLE_PARTIAL_ARTIFACTS,
    )

    assert blocking == {"125_government_subsidy_domain.sql": "partial"}


def test_drift_report_is_read_only_and_requires_artifact_decisions(monkeypatch) -> None:
    snapshot = {
        "sha256": "source-schema",
        "columns": [],
        "triggers": [],
    }
    monkeypatch.setattr(update.migration, "_schema_snapshot", lambda *_: snapshot)
    monkeypatch.setattr(
        update.migration,
        "_owned_classification",
        lambda *_args, **_kwargs: {
            "109_scheduling_generations.sql": "partial",
            "107_system_alert_current_projection.sql": "drift",
        },
    )
    monkeypatch.setattr(
        update.migration,
        "_canonical_artifact_descriptor",
        lambda _artifact: {"tables": {}, "parent_columns": {}},
    )

    report = update.build_drift_report(object(), "lu_test_dataset")

    assert report["status"] == "blocked"
    assert report["source_policy"] == "read_only_no_source_ddl"
    by_artifact = {item["artifact"]: item for item in report["remediations"]}
    assert by_artifact["109_scheduling_generations.sql"]["automatic_apply"] is False
    assert by_artifact["107_system_alert_current_projection.sql"]["disposition"] == (
        "candidate_repair_requires_artifact_decision"
    )


def test_drift_report_does_not_build_or_apply_a_candidate(tmp_path, monkeypatch) -> None:
    config = SimpleNamespace(host="127.0.0.1")
    monkeypatch.setattr(
        update.migration,
        "config_from_env",
        lambda _path: (config, "lu_test_dataset"),
    )
    monkeypatch.setattr(
        update,
        "build_drift_report",
        lambda *_: {"status": "blocked", "remediations": []},
    )
    monkeypatch.setattr(
        update,
        "build_preview",
        lambda *_: pytest.fail("preview must not run for a drift report"),
    )

    assert update.update_local_database(
        environment_file=tmp_path / ".env", drift_report=True
    ) == {"status": "blocked", "remediations": []}


def test_apply_update_rebuilds_source_only_after_verified_candidate(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    config = object()
    preview = {
        "source_database": "union_db",
        "candidate_database": "union_db_local_20260813010203",
        "plan": {"status": "ready"},
    }
    monkeypatch.setattr(update.migration, "write_receipt", lambda *_: calls.append("plan"))
    monkeypatch.setattr(update.migration, "create_source_dump", lambda *_, **__: calls.append("backup"))
    monkeypatch.setattr(update.migration, "restore_candidate", lambda *_, **__: calls.append("restore"))
    monkeypatch.setattr(
        update.migration,
        "apply_schema",
        lambda *_, **__: calls.append("schema"),
    )
    monkeypatch.setattr(update.migration, "verify_candidate", lambda *_: calls.append("verify"))
    monkeypatch.setattr(
        update,
        "replace_source_database",
        lambda *_, **__: calls.append("replace") or {"status": "completed"},
    )

    result = update.apply_update(config, tmp_path / ".env", preview, tmp_path / "receipts")

    assert calls == [
        "plan",
        "backup",
        "restore",
        "schema",
        "verify",
        "backup",
        "replace",
    ]
    assert result["status"] == "completed"
    assert result["source_database"] == "union_db"
    assert result["restart_required"] is True


def test_apply_update_resumes_a_partial_schema_candidate(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    config = object()
    candidate = "union_db_local_20260813010203"
    preview = {
        "source_database": "union_db",
        "candidate_database": candidate,
        "plan": {
            "source": {"database": "union_db"},
            "candidate_database": candidate,
        },
    }
    paths = update.artifact_paths(tmp_path / "receipts", candidate)
    paths["directory"].mkdir(parents=True)
    for name in ("plan", "operation", "dump", "backup"):
        paths[name].write_text("{}", encoding="utf-8")

    def read_receipt(path):
        if path == paths["plan"]:
            return preview["plan"]
        return {"candidate_database": candidate, "status": "partial", "phase": "schema_apply"}

    monkeypatch.setattr(update.migration, "read_receipt", read_receipt)
    monkeypatch.setattr(update.migration, "apply_schema", lambda *_, **__: calls.append("schema"))
    monkeypatch.setattr(update.migration, "verify_candidate", lambda *_: calls.append("verify"))
    monkeypatch.setattr(update.migration, "create_source_dump", lambda *_, **__: calls.append("backup"))
    monkeypatch.setattr(update, "replace_source_database", lambda *_, **__: calls.append("replace") or {"status": "completed"})

    result = update.apply_update(config, tmp_path / ".env", preview, tmp_path / "receipts")

    assert calls == ["schema", "verify", "backup", "replace"]
    assert result["status"] == "completed"
    assert result["resumed"] is True


def test_apply_update_restarts_only_a_candidate_stalled_before_restore(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    config = object()
    candidate = "union_db_local_20260813010203"
    preview = {
        "source_database": "union_db",
        "candidate_database": candidate,
        "plan": {
            "source": {"database": "union_db"},
            "candidate_database": candidate,
        },
    }
    paths = update.artifact_paths(tmp_path / "receipts", candidate)
    paths["directory"].mkdir(parents=True)
    for name in ("plan", "operation", "dump", "backup"):
        paths[name].write_text("{}", encoding="utf-8")

    def read_receipt(path):
        if path == paths["plan"]:
            return preview["plan"]
        return {"candidate_database": candidate, "status": "prepared", "phase": "restore"}

    monkeypatch.setattr(update.migration, "read_receipt", read_receipt)
    monkeypatch.setattr(update, "discard_incomplete_candidate", lambda *_: calls.append("discard"))
    monkeypatch.setattr(update.migration, "restore_candidate", lambda *_, **__: calls.append("restore"))
    monkeypatch.setattr(update.migration, "apply_schema", lambda *_, **__: calls.append("schema"))
    monkeypatch.setattr(update.migration, "verify_candidate", lambda *_: calls.append("verify"))
    monkeypatch.setattr(update.migration, "create_source_dump", lambda *_, **__: calls.append("backup"))
    monkeypatch.setattr(update, "replace_source_database", lambda *_, **__: calls.append("replace") or {"status": "completed"})

    result = update.apply_update(config, tmp_path / ".env", preview, tmp_path / "receipts")

    assert calls == ["discard", "restore", "schema", "verify", "backup", "replace"]
    assert result["resumed"] is True


def test_resumable_partial_artifacts_requires_a_notification_receipt_step() -> None:
    assert update.resumable_partial_artifacts({"schema_steps": []}) == update.LOCAL_RESUMABLE_PARTIAL_ARTIFACTS

    allowed = update.resumable_partial_artifacts({
        "schema_steps": [{"part": "203_line_notification_rule_catalog.sql"}],
    })

    assert allowed == update.LOCAL_RESUMABLE_PARTIAL_ARTIFACTS | update.NOTIFICATION_CATALOG_PARTS


def test_resume_or_replace_source_verifies_an_interrupted_prepared_replacement(tmp_path, monkeypatch) -> None:
    candidate = "union_db_local_20260813010203"
    paths = update.artifact_paths(tmp_path / "receipts", candidate)
    paths["directory"].mkdir(parents=True)
    paths["replacement"].write_text("{}", encoding="utf-8")
    receipt = {
        "status": "prepared",
        "source_database": "union_db",
        "candidate_database": candidate,
    }
    written: list[dict[str, object]] = []
    monkeypatch.setattr(update.migration, "read_receipt", lambda _: receipt)
    monkeypatch.setattr(update, "verify_replacement", lambda *_: {"status": "exact"})
    monkeypatch.setattr(update.migration, "write_receipt", lambda _, value: written.append(value.copy()))

    result = update.resume_or_replace_source(object(), "union_db", candidate, paths)

    assert result["status"] == "completed"
    assert result["resumed"] is True
    assert written[-1]["verification"] == {"status": "exact"}


def test_backfilled_candidate_is_eligible_for_verification() -> None:
    assert "backfilled" in update.migration.VERIFYABLE_CANDIDATE_STATUSES


def test_require_current_accepts_only_an_exact_source() -> None:
    exact = {"parts_to_apply": [], "parts_to_resume": []}

    assert update.require_current_database(exact)["status"] == "current"

    with pytest.raises(update.LocalDatabaseUpdateError, match="schema update required"):
        update.require_current_database({
            "parts_to_apply": ["161_runtime_monitoring_line_alerts.sql"],
            "parts_to_resume": [],
        })


def test_preview_treats_an_absent_pure_retirement_as_complete(monkeypatch) -> None:
    monkeypatch.setattr(update.migration, "PURE_RETIREMENT_ARTIFACTS", frozenset({"153.sql"}))
    monkeypatch.setattr(update.migration, "build_plan", lambda *_args, **_kwargs: {
        "release_id": "release",
        "source_objects": {"153.sql": "absent", "161.sql": "absent"},
    })

    preview = update.build_preview(object(), "union_db", "candidate")

    assert preview["parts_to_apply"] == ["161.sql"]
    assert preview["exact_parts"] == ["153.sql"]


def test_cli_reports_a_bounded_blocked_error(monkeypatch, capsys) -> None:
    def blocked_update(**_arguments):
        raise update.LocalDatabaseUpdateError("catalog mismatch")

    monkeypatch.setattr(update, "update_local_database", blocked_update)
    monkeypatch.setattr(sys, "argv", ["update_local_database"])

    assert update.main() == 2
    error = json.loads(capsys.readouterr().err)
    assert error == {"status": "blocked", "error": "catalog mismatch"}


def test_show_create_table_comparison_ignores_dynamic_auto_increment_value() -> None:
    source = {"show_create_tables": {"orders": "CREATE TABLE `orders` AUTO_INCREMENT=81"}}
    candidate = {"show_create_tables": {"orders": "CREATE TABLE `orders` AUTO_INCREMENT=82"}}

    assert update._show_create_tables_match(source, candidate) is True


def test_show_create_table_comparison_ignores_mysql_utf8mb4_rendering_difference() -> None:
    source = {"show_create_tables": {"orders": "`status` enum('待補件') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"}}
    candidate = {"show_create_tables": {"orders": "`status` enum('待補件') COLLATE utf8mb4_unicode_ci"}}

    assert update._show_create_tables_match(source, candidate) is True


def test_show_create_table_comparison_keeps_schema_difference_visible() -> None:
    source = {"show_create_tables": {"orders": "CREATE TABLE `orders` (`status` varchar(8))"}}
    candidate = {"show_create_tables": {"orders": "CREATE TABLE `orders` (`status` varchar(16))"}}

    assert update._show_create_tables_match(source, candidate) is False


def test_replace_refuses_source_changes_before_drop(tmp_path, monkeypatch) -> None:
    paths = update.artifact_paths(tmp_path, "union_db_local_20260813010203")
    monkeypatch.setattr(
        update.migration,
        "read_receipt",
        lambda path: (
            {"source_schema_sha256": "schema"}
            if path.name == "plan.json"
            else {"source_data": {"orders": {"count": 1}}}
        ),
    )
    monkeypatch.setattr(
        update.migration,
        "_table_evidence",
        lambda *_: {"orders": {"count": 2}},
    )

    with pytest.raises(update.LocalDatabaseUpdateError, match="source changed"):
        update.replace_source_database(object(), "union_db", "candidate", paths)


def test_replace_rolls_back_old_dump_when_final_restore_fails(tmp_path, monkeypatch) -> None:
    paths = update.artifact_paths(tmp_path, "union_db_local_20260813010203")
    expected = {"orders": {"count": 1}}
    events: list[str] = []
    monkeypatch.setattr(
        update.migration,
        "read_receipt",
        lambda path: (
            {"source_schema_sha256": "schema"}
            if path.name == "plan.json"
            else {"source_data": expected}
        ),
    )
    monkeypatch.setattr(update.migration, "_table_evidence", lambda *_: expected)
    monkeypatch.setattr(update.migration, "_schema_snapshot", lambda *_: {"sha256": "schema"})
    monkeypatch.setattr(update.migration, "write_receipt", lambda *_: None)
    monkeypatch.setattr(update, "recreate_database", lambda *_: events.append("recreate"))
    monkeypatch.setattr(
        update,
        "restore_dump",
        lambda *_, **__: (_ for _ in ()).throw(update.LocalDatabaseUpdateError("restore failed")),
    )
    monkeypatch.setattr(update, "rollback_source", lambda *_, **__: events.append("rollback"))

    with pytest.raises(update.LocalDatabaseUpdateError, match="restore failed"):
        update.replace_source_database(object(), "union_db", "candidate", paths)

    assert events == ["recreate", "rollback"]
