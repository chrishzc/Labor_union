from pathlib import Path


SCHEMA_PART = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "schema_parts"
    / "140_client_refund_return.sql"
)


def test_refund_return_schema_adds_a_distinct_idempotency_kind() -> None:
    source = SCHEMA_PART.read_text(encoding="utf-8")

    assert "MODIFY COLUMN correction_type" in source
    assert "'refund_return'" in source
    assert "'refund'" in source
    assert "'reversal'" in source
