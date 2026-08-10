"""The preserve-data read-smoke must not start write-capable workers."""

from __future__ import annotations

from api import main


def test_rehearsal_environment_disables_background_workers(monkeypatch) -> None:
    monkeypatch.setenv("PRESERVE_DATA_REHEARSAL_READ_ONLY", "true")

    assert main._background_workers_enabled() is False


def test_normal_runtime_keeps_background_workers_enabled(monkeypatch) -> None:
    monkeypatch.delenv("PRESERVE_DATA_REHEARSAL_READ_ONLY", raising=False)

    assert main._background_workers_enabled() is True
