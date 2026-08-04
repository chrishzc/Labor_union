from pathlib import Path


SCHEMA_PART = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "schema_parts"
    / "143_client_refund_return_review.sql"
)


def test_refund_return_review_schema_is_append_only_and_explicit() -> None:
    source = SCHEMA_PART.read_text(encoding="utf-8")

    assert "'refund_return_review_recorded'" in source
    assert "CREATE TABLE IF NOT EXISTS client_refund_return_review_events" in source
    assert "original_refund_ledger_entry_id" in source
    assert "UNIQUE KEY uq_client_refund_return_review_bank_refund" in source
    assert "JSON_TYPE(evidence) = 'ARRAY'" in source
    assert "trg_client_refund_return_review_event_before_update" in source
    assert "trg_client_refund_return_review_receipt_before_delete" in source
