from pathlib import Path


SCHEMA_PATH = Path("db/schema_parts/80_government_subsidy_transactions.sql")


def _sql():
    return " ".join(SCHEMA_PATH.read_text(encoding="utf-8").split())


def test_allocation_foreign_keys_enforce_one_claim_batch():
    sql = _sql()

    assert (
        "FOREIGN KEY (transaction_id, claim_batch_id) "
        "REFERENCES government_subsidy_transactions(id, claim_batch_id)"
    ) in sql
    assert (
        "FOREIGN KEY (claim_item_id, claim_batch_id) "
        "REFERENCES subsidy_claim_batch_items(id, batch_id)"
    ) in sql
    assert "uq_subsidy_claim_item_id_batch" in sql


def test_reversals_must_target_an_original_receipt_in_the_same_batch():
    sql = _sql()

    assert (
        "FOREIGN KEY (reversal_of_transaction_id, claim_batch_id, reversal_target_type) "
        "REFERENCES government_subsidy_transactions(id, claim_batch_id, transaction_type)"
    ) in sql
    assert (
        "FOREIGN KEY (reversal_of_allocation_id, claim_batch_id, reversal_target_type) "
        "REFERENCES government_subsidy_allocations(id, claim_batch_id, allocation_type)"
    ) in sql
    assert sql.count("CHECK (reversal_target_type = 'receipt')") == 2


def test_existing_schema_upgrade_is_guarded_for_loader_replay():
    sql = _sql()

    assert "INFORMATION_SCHEMA.COLUMNS" in sql
    assert "INFORMATION_SCHEMA.STATISTICS" in sql
    assert "INFORMATION_SCHEMA.TABLE_CONSTRAINTS" in sql
    assert "INFORMATION_SCHEMA.TABLES" in sql
    deallocations = sql.count("DEALLOCATE PREPARE gov_subsidy_schema_stmt")
    preparations = sql.count("PREPARE gov_subsidy_schema_stmt") - deallocations
    assert preparations == deallocations
    assert preparations >= 10
