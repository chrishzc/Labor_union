"""
File: test_update_local_database_entrypoint.py
Description: 驗證本機 ordered release 升級、current gate 與 launcher 的明確確認契約。
"""

from pathlib import Path

import pytest

from scripts import update_local_database as update


SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "launchers"
    / "update_local_database.bat"
).read_text(encoding="utf-8")


def test_double_click_previews_before_preserve_data_update() -> None:
    assert SCRIPT.index("-m scripts.update_local_database\n") < SCRIPT.index(
        "--apply --confirm-configured-database"
    )
    assert "Type UPDATE to continue" in SCRIPT


def test_launcher_dry_run_only_checks_wiring() -> None:
    dry_run_start = SCRIPT.index('if /I "%~1"=="--dry-run"')
    argument_forward_start = SCRIPT.index('if not "%~1"==""', dry_run_start)
    dry_run_block = SCRIPT[dry_run_start:argument_forward_start]
    assert "scripts.launcher_preflight --profile database-update" in dry_run_block
    assert "scripts.update_local_database" not in dry_run_block


def test_update_reports_restart_requirement() -> None:
    assert "Restart local services" in SCRIPT


def test_update_reads_the_configured_database_for_confirmation() -> None:
    assert "--confirm-configured-database" in SCRIPT
    assert "--confirm-database union_db" not in SCRIPT
    assert "replace DB_DATABASE" not in SCRIPT


def test_missing_environment_file_uses_explicit_process_database_values(
    tmp_path,
) -> None:
    config, source = update._database_config_from_environment(
        tmp_path / ".env",
        {
            "DB_HOST": "127.0.0.1",
            "DB_PORT": "3306",
            "DB_USER": "root",
            "DB_PASSWORD": "secret",
            "DB_DATABASE": "lu_test_task96_current",
        },
    )

    assert config.host == "127.0.0.1"
    assert config.port == 3306
    assert config.user == "root"
    assert config.password == "secret"
    assert source == "lu_test_task96_current"


def test_require_current_rejects_malformed_or_incomplete_chain_preview() -> None:
    for preview in (
        {"status": "current", "release_id": "terminal"},
        {
            "status": "current",
            "release_id": "terminal",
            "baseline_release_id": "baseline",
            "latest_release_id": "terminal",
            "artifacts": [
                {"name": "1003.sql", "state": "exact"},
                {"name": "1004.sql", "state": "absent"},
                {"name": "1005.sql", "state": "exact"},
            ],
        },
    ):
        with pytest.raises(update.LocalDatabaseUpdateError):
            update.require_current_database(preview)


def test_apply_additive_update_runs_each_pending_release_in_order(
    monkeypatch, tmp_path
) -> None:
    entries = update.migration._local_ordered_upgrade_entries()
    previews = iter((
        {
            "status": "ready",
            "release_id": "release-1004",
            "pending_releases": [
                {"release_id": "release-1004", "qualification_receipt": "q1004.json"},
                {"release_id": "release-1005", "qualification_receipt": "q1005.json"},
            ],
        },
        {
            "status": "ready",
            "release_id": "release-1005",
            "pending_releases": [
                {"release_id": "release-1005", "qualification_receipt": "q1005.json"},
            ],
        },
        {
            "status": "current",
            "release_id": entries[-1]["release_id"],
            "release_fingerprint": entries[-1]["release_fingerprint"],
            "baseline_release_id": entries[0]["release_id"],
            "latest_release_id": entries[-1]["release_id"],
            "artifacts": [
                {
                    "name": entry["artifact"]["name"],
                    "release_id": entry["release_id"],
                    "release_fingerprint": entry["release_fingerprint"],
                    "state": "exact",
                }
                for entry in entries
            ],
            "pending_releases": [],
        },
    ))
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        update, "build_additive_preview", lambda *_args, **_kwargs: next(previews)
    )
    monkeypatch.setattr(
        update.additive,
        "prepare_backup",
        lambda *_args, **kwargs: calls.append(
            ("prepare", Path(kwargs["qualification_path"]).name)
        ),
    )
    monkeypatch.setattr(
        update.additive,
        "apply",
        lambda *_args, **kwargs: calls.append(
            ("apply", Path(kwargs["qualification_path"]).name)
        ) or {"status": "completed"},
    )

    result = update.apply_additive_update(
        object(), "lu_test_dataset", tmp_path
    )

    assert result["status"] == "current"
    assert calls == [
        ("prepare", "q1004.json"), ("apply", "q1004.json"),
        ("prepare", "q1005.json"), ("apply", "q1005.json"),
    ]


def test_apply_additive_update_reports_release_phase_and_resume_guidance(
    tmp_path, monkeypatch
):
    preview = {
        "status": "ready",
        "pending_releases": [
            {
                "release_id": "release-1012",
                "qualification_receipt": "q1012.json",
            }
        ],
    }
    monkeypatch.setattr(update, "build_additive_preview", lambda *_args, **_kwargs: preview)
    monkeypatch.setattr(update.additive, "prepare_backup", lambda *_args, **_kwargs: None)

    class ProgrammingError(RuntimeError):
        pass

    def fail_apply(*_args, **_kwargs):
        raise ProgrammingError("sensitive SQL details")

    monkeypatch.setattr(update.additive, "apply", fail_apply)

    with pytest.raises(update.LocalDatabaseUpdateError) as raised:
        update.apply_additive_update(object(), "lu_test_example", tmp_path)

    assert raised.value.code == "database_update_execution_failed"
    assert str(raised.value) == (
        "release release-1012 failed during apply: ProgrammingError; "
        "rerun the updater to resume from its journal"
    )
    assert "sensitive SQL details" not in str(raised.value)
