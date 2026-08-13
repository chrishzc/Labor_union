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
    monkeypatch.setattr(
        update,
        "apply_update",
        lambda _config, _environment, received, _receipt_root: captured.update(received) or {"status": "completed"},
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


def test_apply_update_rebuilds_source_only_after_verified_candidate(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    config = object()
    preview = {
        "source_database": "union_db",
        "candidate_database": "union_db_local_20260813010203",
        "plan": {"status": "ready"},
    }
    monkeypatch.setattr(update.migration, "write_receipt", lambda *_: calls.append("plan"))
    monkeypatch.setattr(update.migration, "create_source_dump", lambda *_: calls.append("backup"))
    monkeypatch.setattr(update.migration, "restore_candidate", lambda *_: calls.append("restore"))
    monkeypatch.setattr(
        update.migration,
        "apply_schema",
        lambda *_, **__: calls.append("schema"),
    )
    monkeypatch.setattr(update.migration, "verify_candidate", lambda *_: calls.append("verify"))
    monkeypatch.setattr(
        update,
        "replace_source_database",
        lambda *_: calls.append("replace") or {"status": "completed"},
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
        lambda *_: (_ for _ in ()).throw(update.LocalDatabaseUpdateError("restore failed")),
    )
    monkeypatch.setattr(update, "rollback_source", lambda *_: events.append("rollback"))

    with pytest.raises(update.LocalDatabaseUpdateError, match="restore failed"):
        update.replace_source_database(object(), "union_db", "candidate", paths)

    assert events == ["recreate", "rollback"]
