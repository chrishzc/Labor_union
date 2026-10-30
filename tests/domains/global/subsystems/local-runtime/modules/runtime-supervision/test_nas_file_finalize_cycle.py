"""Only new production NAS files participate in the existing durable cycle."""
from types import SimpleNamespace
from pathlib import Path
import os
import pytest
from api.dependencies import private_operations
from infrastructure.mysql import controlled_file_finalize_worker


def test_production_cycle_uses_existing_runner_with_new_layout_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", str(tmp_path))
    calls = []
    def runner(factory, storage, worker, now, **options):
        calls.append((storage._configured_root, worker, options))
        return SimpleNamespace(run_once=lambda: 2)
    monkeypatch.setattr(controlled_file_finalize_worker, "MySqlControlledFileFinalizeRunner", runner)
    assert private_operations._finalize_new_nas_files("fixture-worker") == 2
    assert calls == [(tmp_path, "fixture-worker", {"layout_only": True})]
    assert not list(tmp_path.iterdir())


def test_development_cycle_never_reads_or_moves_existing_data(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", str(tmp_path))
    sentinel = tmp_path / "existing-development.bin"
    sentinel.write_bytes(b"original development fixture")
    def forbidden(*_, **__):
        raise AssertionError("development data must not enter the new NAS finalize runner")
    monkeypatch.setattr(controlled_file_finalize_worker, "MySqlControlledFileFinalizeRunner", forbidden)
    assert private_operations._finalize_new_nas_files("fixture-worker") == 0
    assert sentinel.read_bytes() == b"original development fixture"


@pytest.mark.skipif(os.name != "nt", reason="Windows UNC source-mode deployment")
def test_windows_source_mode_finalizes_only_new_nas_locators(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", r"\\nas.invalid\shared")
    calls = []
    def runner(factory, storage, worker, now, **options):
        calls.append((storage._configured_root, options))
        return SimpleNamespace(run_once=lambda: 1)
    monkeypatch.setattr(controlled_file_finalize_worker, "MySqlControlledFileFinalizeRunner", runner)
    assert private_operations._finalize_new_nas_files("fixture-worker") == 1
    assert calls == [(Path(r"\\nas.invalid\shared"), {"layout_only": True})]
