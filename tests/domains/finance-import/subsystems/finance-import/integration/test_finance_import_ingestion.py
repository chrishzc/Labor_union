import json

import pytest

from domains.finance_import.ingestion import InitialClassificationFacts
from shared_kernel.identities import ActorContext, IdempotencyKey
from subsystems.finance_import.ingestion import (
    _append_missing_classifications,
    _command_fingerprint,
    _find_replay,
    _integer_tuple,
    _unique_rows,
)


class _Cursor:
    def __init__(self, row=None) -> None:
        self.row = row
        self.calls = []

    def execute(self, statement, params) -> None:
        self.calls.append((statement, params))

    def fetchone(self):
        return self.row


def test_replay_rehydrates_receipt_when_command_fingerprint_matches() -> None:
    actor = ActorContext("admin")
    digest = "a" * 64
    fingerprint = _command_fingerprint(digest, actor)
    cursor = _Cursor(
        {
            "command_fingerprint": fingerprint,
            "result_snapshot": json.dumps(
                {
                    "batch_identity": "finance-import-batch:7",
                    "source_content_digest": digest,
                    "source_row_count": 2,
                    "canonical_created_count": 1,
                    "duplicate_occurrence_count": 1,
                }
            ),
        }
    )

    receipt = _find_replay(cursor, IdempotencyKey("same-workbook"), fingerprint)

    assert receipt.batch_identity == "finance-import-batch:7"
    assert "FOR UPDATE" in cursor.calls[0][0]


def test_replay_rejects_idempotency_key_with_different_command() -> None:
    cursor = _Cursor({"command_fingerprint": "other", "result_snapshot": "{}"})

    with pytest.raises(ValueError, match="idempotency_conflict"):
        _find_replay(cursor, IdempotencyKey("same-workbook"), "expected")


def test_unique_rows_prefers_inserted_row_and_stable_identity_order() -> None:
    rows = _unique_rows(
        [
            {"row_id": 2, "result": "skipped_existing"},
            {"row_id": 1, "result": "skipped_existing"},
            {"row_id": 2, "result": "inserted"},
        ]
    )

    assert rows == (
        {"row_id": 1, "result": "skipped_existing"},
        {"row_id": 2, "result": "inserted"},
    )


@pytest.mark.parametrize("value", ["[3,2,3]", [3, 2, 3]])
def test_identity_ids_are_positive_unique_sorted_integers(value) -> None:
    assert _integer_tuple(value) == (2, 3)


@pytest.mark.parametrize("value", ["{}", [0]])
def test_identity_ids_reject_non_array_or_nonpositive_values(value) -> None:
    with pytest.raises(ValueError, match="matched_identity_ids"):
        _integer_tuple(value)


def test_duplicate_staged_row_still_creates_only_one_canonical_event(monkeypatch) -> None:
    cursor = _Cursor()
    monkeypatch.setattr(
        "subsystems.finance_import.ingestion._classification_exists",
        lambda *_arguments: False,
    )
    monkeypatch.setattr(
        "subsystems.finance_import.ingestion._load_initial_facts",
        lambda *_arguments: InitialClassificationFacts(
            4, "non_business_review", (), "source_requires_review"
        ),
    )
    monkeypatch.setattr(
        "subsystems.finance_import.ingestion.build_initial_classification",
        lambda _facts: object(),
    )
    inserted = []
    monkeypatch.setattr(
        "subsystems.finance_import.ingestion._insert_initial_classification",
        lambda *_arguments: inserted.append("event"),
    )
    monkeypatch.setattr(
        "subsystems.finance_import.ingestion._append_classification_outbox",
        lambda *_arguments: None,
    )

    created = _append_missing_classifications(
        cursor,
        7,
        [
            {"row_id": 4, "result": "skipped_existing"},
            {"row_id": 4, "result": "inserted"},
        ],
        ActorContext("admin"),
    )

    assert created == 1
    assert inserted == ["event"]
