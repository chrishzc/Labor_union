"""Focused Task 97 package B check for the retained assignment migration CLI."""

from __future__ import annotations

import json
import sys

import pytest

from scripts import migrate_assignment_schedule_integrity as assignment


def test_assignment_apply_fails_closed_before_connect(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["assignment", "--apply"])

    def unexpected_connect(**kwargs):
        raise AssertionError("blocked apply must not connect to MySQL")

    monkeypatch.setattr("pymysql.connect", unexpected_connect)

    with pytest.raises(SystemExit) as exc_info:
        assignment.main()

    assert exc_info.value.code == 2
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["success"] is False
    assert manifest["apply_result"]["applied"] is False
    assert manifest["errors"] == [assignment.APPLY_BLOCKED_REASON]
