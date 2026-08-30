import pytest

from subsystems.finance_import import application as importer


class Cursor:
    rowcount = 1

    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))


class Connection:
    def __init__(self, cursor=None):
        self._cursor = cursor or Cursor()
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


def test_pipeline_dispatches_only_inserted_rows_and_completes_batch(monkeypatch):
    connection = Connection()
    dispatched = []
    normalized = {"format_id": "sinopac", "normalized_rows": [{}]}
    staged = {
        "batch_id": 41,
        "staged_rows": [
            {
                "row_id": 10,
                "classification_type": "client_receipt",
                "result": "inserted",
            },
            {
                "row_id": 11,
                "classification_type": "client_receipt",
                "result": "skipped_existing",
            },
            {
                "row_id": 12,
                "classification_type": "non_business_review",
                "result": "inserted",
            },
        ],
    }
    monkeypatch.setattr(importer, "load_finance_identity_maps", lambda cursor: {"staff_accounts": {}})
    monkeypatch.setattr(importer, "stage_finance_rows", lambda cursor, result, maps: staged)

    def dispatch(cursor, row_id, batch_id):
        assert batch_id == 41
        dispatched.append(row_id)
        return {
            "classification_type": (
                "client_receipt" if row_id == 10 else "non_business_review"
            ),
            "result": "reconciled" if row_id == 10 else "pending",
            "reason": None,
            "formal_references": {},
            "finance_alert_action": None,
        }

    monkeypatch.setattr(importer, "dispatch_finance_import_row", dispatch)
    monkeypatch.setattr(
        importer,
        "project_finance_import_review_alert",
        lambda cursor, batch_id: None,
    )

    result = importer.import_finance_workbook(
        "renamed.xlsx", dry_run=True, connection_factory=lambda: connection,
        normalizer=lambda _path: normalized,
    )

    assert dispatched == [10, 12]
    assert result == {
        "mode": "dry_run",
        "source_path": str(importer.os.path.abspath("renamed.xlsx")),
        "format_manifest": {
            "format_id": "sinopac",
            "sheet_name": None,
            "header_row": None,
            "normalized_row_count": 1,
        },
        "batch_id": None,
        "inserted_rows": 2,
        "skipped_existing": 1,
        "reconciled_counts": {"client_receipt": 1},
        "pending_rows": [],
        "row_results": [
            {
                "dedup_fingerprint": None,
                "classification_type": "client_receipt",
                "staging_result": "inserted",
                "dispatch_result": "reconciled",
                "reason": None,
                "finance_alert_action": None,
            },
            {
                "dedup_fingerprint": None,
                "classification_type": "client_receipt",
                "staging_result": "skipped_existing",
                "dispatch_result": None,
                "reason": None,
                "finance_alert_action": None,
            },
            {
                "dedup_fingerprint": None,
                "classification_type": "non_business_review",
                "staging_result": "inserted",
                "dispatch_result": "pending",
                "reason": None,
                "finance_alert_action": None,
            },
        ],
        "alert_action": None,
        "transaction_outcome": "rolled_back",
    }
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closes == 1
    assert any("SET status='completed'" in sql for sql, _ in connection._cursor.executed)


def test_downstream_error_rolls_back_entire_batch(monkeypatch):
    connection = Connection()
    monkeypatch.setattr(importer, "load_finance_identity_maps", lambda cursor: {})
    monkeypatch.setattr(
        importer,
        "stage_finance_rows",
        lambda cursor, result, maps: {
            "batch_id": 42,
            "staged_rows": [
                {"row_id": 20, "classification_type": "government_subsidy", "result": "inserted"}
            ],
        },
    )
    monkeypatch.setattr(
        importer,
        "dispatch_finance_import_row",
        lambda cursor, row_id, batch_id: (_ for _ in ()).throw(
            RuntimeError("downstream failed")
        ),
    )

    with pytest.raises(RuntimeError, match="downstream failed"):
        importer.import_finance_workbook(
            "input.xlsx", dry_run=True, connection_factory=lambda: connection,
            normalizer=lambda _path: {"normalized_rows": []},
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closes == 1
    assert not any("status='completed'" in sql for sql, _ in connection._cursor.executed)
