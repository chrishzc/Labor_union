import pytest

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


@pytest.mark.parametrize(
    "receipt_duplicates,occurrence_duplicates,source_rows,expected_duplicates",
    [(None, 1, 2, 1), ("2", 0, 3, 2)],
    ids=["same-batch-occurrences", "receipt-duplicates"],
)
def test_repository_counts_repeats_without_blocking_a_new_dispatchable_row(
    receipt_duplicates, occurrence_duplicates, source_rows, expected_duplicates,
):
    cursor = _Cursor()
    header, counts, *_ = cursor._results
    cursor._results = (
        {**header, "row_count": source_rows, "receipt_duplicate_count": receipt_duplicates},
        {**counts, "canonical_created_count": 1, "canonical_member_count": 1,
         "duplicate_occurrence_count": occurrence_duplicates, "source_review_occurrence_count": 0},
        ({
            "finance_import_row_id": 8,
            "credit": 12000,
            "debit": None,
            "classification_type": "client_receipt",
            "canonical_fact_version": 0,
            "disposition": "create",
            "decision_facts_fingerprint": "b" * 64,
            "target_identities": '["synthetic-obligation"]',
            "evidence": "[]",
            "available_actions": "[]",
        },),
        (),
    )
    plan = build_finance_import_plan(_load_batch_facts(cursor, "finance-import-batch:7", False))
    assert "finance_import_ingestion_receipts" in cursor.calls[0][0]
    assert plan.counts.source_rows == source_rows
    assert plan.counts.duplicate_occurrences == expected_duplicates
    assert plan.counts.ready_dispatch == 1
    assert len(plan.dispatchable_rows) == 1
    assert plan.apply_allowed


@pytest.mark.parametrize("for_update", [False, True], ids=["preview", "apply"])
@pytest.mark.parametrize(
    "source_count,canonical_count,occurrence_duplicates,receipt_duplicates,review_count,allowed",
    [
        pytest.param(2, 2, 0, None, 0, True, id="complete-source"),
        pytest.param(3, 2, 0, None, 0, False, id="missing-row-without-receipt"),
        pytest.param(3, 2, 0, 0, 0, False, id="missing-row-with-zero-receipt-duplicates"),
        pytest.param(3, 0, 0, 0, 0, False, id="all-rows-missing"),
        pytest.param(3, 2, 0, 1, 0, True, id="receipt-duplicate"),
        pytest.param(3, 2, 1, None, 0, True, id="legacy-occurrence-duplicate"),
        pytest.param(3, 2, 1, 0, 0, False, id="zero-receipt-does-not-borrow-legacy-count"),
        pytest.param(3, 2, 0, None, 1, True, id="source-review"),
        pytest.param(4, 2, 0, 1, 1, True, id="duplicate-and-source-review"),
        pytest.param(2, 2, 0, 0, 1, False, id="excess-occurrence"),
    ],
)
def test_repository_preserves_source_count_for_planning_conservation(
    for_update,
    source_count,
    canonical_count,
    occurrence_duplicates,
    receipt_duplicates,
    review_count,
    allowed,
):
    cursor = _Cursor()
    header, counts, *_ = cursor._results
    cursor._results = (
        {**header, "row_count": source_count, "receipt_duplicate_count": receipt_duplicates},
        {
            **counts,
            "canonical_created_count": canonical_count,
            "canonical_member_count": canonical_count,
            "duplicate_occurrence_count": occurrence_duplicates,
            "source_review_occurrence_count": review_count,
        },
        tuple(
            {
                "finance_import_row_id": row_id,
                "credit": 12000,
                "debit": None,
                "classification_type": "client_receipt",
                "canonical_fact_version": 0,
                "disposition": "create",
                "decision_facts_fingerprint": "b" * 64,
                "target_identities": f'["synthetic-obligation:{row_id}"]',
                "evidence": "[]",
                "available_actions": "[]",
            }
            for row_id in range(8, 8 + canonical_count)
        ),
        (),
    )

    facts = _load_batch_facts(cursor, "finance-import-batch:7", for_update)
    plan = build_finance_import_plan(facts)

    assert facts.source_row_count == source_count
    assert plan.counts.source_rows == source_count
    assert facts.duplicate_occurrence_count == (
        occurrence_duplicates if receipt_duplicates is None else receipt_duplicates
    )
    assert facts.source_review_occurrence_count == review_count
    assert ("occurrence_count_mismatch" in plan.blocking_codes) is (not allowed)
    assert plan.apply_allowed is allowed
