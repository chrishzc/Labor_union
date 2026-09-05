from domains.finance_import.planning import (
    FinanceImportBatchFacts,
    build_finance_import_plan,
)
from infrastructure.mysql.finance_import_repository import _load_batch_facts


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self._result_index = -1
        self._results = (
            {
                "batch_id": 7,
                "batch_identity": "finance-import-batch:7",
                "source_content_digest": "a" * 64,
                "classifier_version": "classifier-v1",
                "fingerprint_version": "fingerprint-v1",
                "batch_version": 0,
                "row_count": 1,
                "status": "completed",
            },
            {
                "canonical_created_count": 0,
                "duplicate_occurrence_count": 0,
                "canonical_member_count": 0,
                "source_review_occurrence_count": 1,
            },
            (),
            (),
        )

    def execute(self, statement: str, params: tuple[object, ...]) -> None:
        self.calls.append((statement, params))
        self._result_index += 1

    def fetchone(self):
        return self._results[self._result_index]

    def fetchall(self):
        return self._results[self._result_index]


def _facts(*, source_review_occurrence_count: int) -> FinanceImportBatchFacts:
    return FinanceImportBatchFacts(
        batch_identity="finance-import-batch:7",
        batch_version=0,
        source_row_count=1,
        canonical_created_count=0,
        duplicate_occurrence_count=0,
        source_content_digest="a" * 64,
        classifier_version="classifier-v1",
        fingerprint_version="fingerprint-v1",
        rows=(),
        source_review_occurrence_count=source_review_occurrence_count,
    )


def test_source_review_occurrence_satisfies_batch_conservation() -> None:
    plan = build_finance_import_plan(_facts(source_review_occurrence_count=1))

    assert "occurrence_count_mismatch" not in plan.blocking_codes
    assert plan.apply_allowed is True


def test_missing_source_review_occurrence_keeps_real_mismatch_blocked() -> None:
    plan = build_finance_import_plan(_facts(source_review_occurrence_count=0))

    assert "occurrence_count_mismatch" in plan.blocking_codes
    assert plan.apply_allowed is False


def test_repository_reads_source_review_occurrence_count_in_batch_snapshot() -> None:
    cursor = _Cursor()

    facts = _load_batch_facts(cursor, "finance-import-batch:7", False)

    counts_statement, counts_params = cursor.calls[1]
    assert "finance_import_source_review_occurrences" in counts_statement
    assert "source_review_occurrence_count" in counts_statement
    assert counts_params == (7, 7, 7, 7)
    assert facts.source_review_occurrence_count == 1
