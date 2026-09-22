"""The retained disposable bootstrap library produces a plan without database writes."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from scripts import bootstrap_disposable_mysql_schema as disposable


def test_disposable_bootstrap_dry_run_is_plan_only(tmp_path: Path) -> None:
    arguments = Namespace(
        database="lu_test_a",
        confirm_database="lu_test_a",
        max_schema_part=None,
        base_only=False,
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(disposable, "selected_schema_parts", lambda _manifest: [])
    try:
        payload = disposable._dry_run_payload(arguments, {"release_id": "r1"})
    finally:
        monkeypatch.undo()
    assert payload["mode"] == "dry-run"
    assert payload["database"] == "lu_test_a"
    assert payload["plan_fingerprint"]
