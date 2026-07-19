from scripts.imports import import_finance_excel as importer


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
    def __init__(self):
        self._cursor = Cursor()
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def _run(monkeypatch, staged_rows):
    connection = Connection()
    dispatched = []
    monkeypatch.setattr(importer, "normalize_workbook", lambda path: {"normalized_rows": []})
    monkeypatch.setattr(importer, "get_connection", lambda: connection)
    monkeypatch.setattr(importer, "load_finance_identity_maps", lambda cursor: {})
    monkeypatch.setattr(
        importer,
        "stage_finance_rows",
        lambda cursor, normalized, maps: {"batch_id": 51, "staged_rows": staged_rows},
    )

    def dispatch(cursor, row):
        dispatched.append(row["row_id"])
        return row["dispatch_result"]

    monkeypatch.setattr(importer, "_dispatch_inserted_row", dispatch)
    return importer.import_finance_workbook("renamed-and-overlapping.xlsx"), dispatched, connection


def test_cross_file_duplicate_is_not_redispatched_or_overwritten(monkeypatch):
    """A historical overlap only records an occurrence; its manual state is untouched."""
    result, dispatched, connection = _run(
        monkeypatch,
        [
            {
                "row_id": 701,
                "classification_type": "client_receipt",
                "result": "skipped_existing",
                "existing_reconciliation_status": "manual_reviewed",
            }
        ],
    )

    assert result["inserted_rows"] == 0
    assert result["skipped_existing"] == 1
    assert result["pending_rows"] == []
    assert dispatched == []
    assert all("finance_import_rows SET" not in sql for sql, _ in connection._cursor.executed)


def test_same_second_same_memo_different_balance_stays_two_canonical_rows(monkeypatch):
    """Different fingerprints are dispatched independently; a suspected duplicate stays pending."""
    result, dispatched, _ = _run(
        monkeypatch,
        [
            {
                "row_id": 711,
                "classification_type": "client_receipt",
                "result": "inserted",
                "dispatch_result": {"result": "reconciled"},
            },
            {
                "row_id": 712,
                "classification_type": "client_receipt",
                "result": "inserted",
                "dispatch_result": {
                    "result": "pending",
                    "reason": "suspected_duplicate_business_match",
                },
            },
        ],
    )

    assert dispatched == [711, 712]
    assert result["inserted_rows"] == 2
    assert result["reconciled_counts"] == {"client_receipt": 1}
    assert result["pending_rows"] == [712]


def test_same_batch_duplicate_occurrence_only_dispatches_its_canonical_row(monkeypatch):
    result, dispatched, _ = _run(
        monkeypatch,
        [
            {
                "row_id": 721,
                "classification_type": "client_receipt",
                "result": "inserted",
                "dispatch_result": {"result": "reconciled"},
            },
            {
                "row_id": 721,
                "classification_type": "client_receipt",
                "result": "skipped_existing",
            },
        ],
    )

    assert dispatched == [721]
    assert result["inserted_rows"] == 1
    assert result["skipped_existing"] == 1
    assert result["reconciled_counts"] == {"client_receipt": 1}
