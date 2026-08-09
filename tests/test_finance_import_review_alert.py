from __future__ import annotations

import pytest

from subsystems.anomalies import finance_import_review_alert as subject


class ScriptedCursor:
    def __init__(self, one_rows, all_rows):
        self.one_rows = iter(one_rows)
        self.all_rows = iter(all_rows)
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return next(self.one_rows)

    def fetchall(self):
        return next(self.all_rows)


def test_project_creates_import_alert_for_occurrence_integrity_mismatch(monkeypatch):
    cursor = ScriptedCursor(
        [
            {"id": 4, "row_count": 3, "source_file": r"C:\\bank\\statement.xlsx", "format_id": "sinopac", "sheet_name": "Sheet1", "header_row": 2, "status": "completed"},
            {"occurrence_count": 2, "distinct_count": 2},
            {"id": 8, "dispatch_count": 2, "reconciled_count": 1, "pending_count": 1, "status": "completed", "selected_count": 2, "changed_count": 2, "completed_at": None},
        ],
        [[{"id": 11, "direction": "credit", "classification_type": "non_business_review", "classification_reason": "unknown", "reconciliation_status": "pending"}]],
    )
    captured = {}
    monkeypatch.setattr(subject, "upsert_system_alert", lambda _cursor, **kwargs: captured.update(kwargs) or {"result": "created", "alert": {"id": 1}})
    monkeypatch.setattr(subject, "_project_canonical_import006_alert", lambda *args, **kwargs: None)

    result = subject.project_finance_import_review_alert(cursor, 4)

    assert result["alert_action"] == "created"
    assert result["summary"]["integrity_inconsistent_count"] == 1
    assert captured["case_key"] == "finance-import-batch:4"
    assert captured["details"]["source_file_label"] == "statement.xlsx"
    assert captured["details"]["sample_row_ids"] == [11]


def test_project_resolves_when_completed_batch_is_consistent(monkeypatch):
    cursor = ScriptedCursor(
        [
            {"id": 4, "row_count": 1, "source_file": None, "format_id": "sinopac", "sheet_name": "Sheet1", "header_row": 2, "status": "completed"},
            {"occurrence_count": 1, "distinct_count": 1},
            None,
        ],
        [[{"id": 11, "direction": "credit", "classification_type": "non_business_review", "classification_reason": "unknown", "reconciliation_status": "pending"}]],
    )
    monkeypatch.setattr(subject, "resolve_current_state_alert", lambda _cursor, **kwargs: {"result": "resolved", "alert": {"id": 1}})
    monkeypatch.setattr(subject, "_project_canonical_import006_alert", lambda *args, **kwargs: None)

    result = subject.project_finance_import_review_alert(cursor, 4)

    assert result["alert_action"] == "resolved"
    assert result["alert"] == {"id": 1}
    assert result["summary"]["integrity_inconsistent_count"] == 0


def test_scan_maps_existing_action_to_unchanged(monkeypatch):
    cursor = ScriptedCursor([], [[{"id": 3}, {"id": 4}]])
    actions = iter(["existing", "created"])
    monkeypatch.setattr(subject, "project_finance_import_review_alert", lambda *_: {"alert_action": next(actions)})

    assert subject.scan_completed_finance_import_review_alerts(cursor) == {
        "created": 1,
        "updated": 0,
        "reopened": 0,
        "resolved": 0,
        "unchanged": 1,
    }


def test_rejects_non_positive_batch_id():
    with pytest.raises(ValueError, match="batch_id must be a positive integer"):
        subject.project_finance_import_review_alert(ScriptedCursor([], []), True)


def test_project_also_mirrors_into_canonical_anomaly_registry(monkeypatch):
    cursor = ScriptedCursor(
        [
            {"id": 4, "row_count": 3, "source_file": r"C:\\bank\\statement.xlsx", "format_id": "sinopac", "sheet_name": "Sheet1", "header_row": 2, "status": "completed"},
            {"occurrence_count": 2, "distinct_count": 2},
            {"id": 8, "dispatch_count": 2, "reconciled_count": 1, "pending_count": 1, "status": "completed", "selected_count": 2, "changed_count": 2, "completed_at": None},
        ],
        [[{"id": 11, "direction": "credit", "classification_type": "non_business_review", "classification_reason": "unknown", "reconciliation_status": "pending"}]],
    )
    monkeypatch.setattr(subject, "upsert_system_alert", lambda _cursor, **kwargs: {"result": "created", "alert": {"id": 1}})
    captured = {}

    def _fake_canonical_projection(_cursor, batch_id, summary, details):
        captured["batch_id"] = batch_id
        captured["active"] = summary["integrity_inconsistent_count"] > 0

    monkeypatch.setattr(subject, "_project_canonical_import006_alert", _fake_canonical_projection)

    subject.project_finance_import_review_alert(cursor, 4)

    assert captured["batch_id"] == 4
    assert captured["active"] is True
