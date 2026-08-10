from pathlib import Path


SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "schema_parts"
    / "139_finance_import_historical_reprocess.sql"
)


def test_historical_reprocess_schema_is_additive_and_append_only():
    source = SCHEMA.read_text(encoding="utf-8")

    assert "DROP TABLE" not in source
    assert "TRUNCATE" not in source
    assert "finance_import_historical_reprocess_receipts" in source
    assert "historical_reprocess_completed" in source
    assert "'client_refund'" in source
    assert "cannot be updated" in source
    assert "cannot be deleted" in source
