from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PART = PROJECT_ROOT / "db" / "schema_parts" / "138_client_subsidy_advance_settlement.sql"


def test_subsidy_advance_schema_is_additive_and_append_only():
    source = SCHEMA_PART.read_text(encoding="utf-8")

    assert "'subsidy_advance'" in source
    assert "'subsidy_advance_reversal'" in source
    assert "client_subsidy_advance_recoveries" in source
    assert "'subsidy_return'" in source
    assert "'subsidy_return_reversal'" in source
    assert "client_subsidy_return_claim_item_links" in source
    assert "government_allocation_id" in source
    assert "source_outbox_id" in source
    assert "uq_client_subsidy_recovery_outbox_advance" in source
    assert "cannot be updated" in source
    assert "cannot be deleted" in source


def test_government_receipt_outbox_has_a_distinct_allocation_fact_type():
    source = SCHEMA_PART.read_text(encoding="utf-8")

    assert "'government_subsidy_receipt_allocated'" in source
