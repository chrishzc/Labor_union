from __future__ import annotations

import importlib.util

import pytest

from scripts.imports import reprocess_finance_import_batch as reprocess_cli
from subsystems.finance_import import reprocessing


def test_legacy_service_is_removed_and_typed_diagnostic_rejects_apply(monkeypatch):
    assert importlib.util.find_spec("services.finance_import_reprocessing") is None
    monkeypatch.setattr(
        reprocessing,
        "get_connection",
        lambda: pytest.fail("retired apply must not open a connection"),
    )

    with pytest.raises(ValueError, match="legacy_finance_import_reprocess_apply_retired"):
        reprocessing.reprocess_finance_import_batch(1, dry_run=False)


def test_legacy_cli_apply_is_rejected_before_calling_the_service(monkeypatch):
    monkeypatch.setattr(
        reprocess_cli,
        "reprocess_finance_import_batch",
        lambda *_args, **_kwargs: pytest.fail("legacy apply must not call a service"),
    )

    with pytest.raises(ValueError, match="legacy_finance_import_reprocess_apply_retired"):
        reprocess_cli.main(["--batch-id", "1", "--apply"])
