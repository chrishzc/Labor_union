from pathlib import Path


def test_overpayment_disposition_schema_preserves_root_and_mutually_exclusive_return_payable() -> None:
    sql = Path("db/schema_parts/169_government_subsidy_overpayment_disposition.sql").read_text(encoding="utf-8")
    assert "government_subsidy_overpayments" in sql
    assert "government_subsidy_overpayment_offsets" in sql
    assert "government_subsidy_overpayment_established" in sql
    assert "government_overpayment_return_payables" in sql
    assert "government_overpayment_return_payables" in sql
    assert "agency_identity" in sql
    assert "account_fingerprint" in sql
    assert "uq_government_overpayment_return_root" in sql
    assert "trg_government_subsidy_overpayment_events_before_update" in sql
    assert "'return_reconciled'" in sql


def test_return_payable_is_export_only_and_has_no_outbound_bank_link() -> None:
    sql = Path("db/schema_parts/169_government_subsidy_overpayment_disposition.sql").read_text(encoding="utf-8")

    return_payable_section = sql.split("CREATE TABLE IF NOT EXISTS government_overpayment_return_payables", 1)[1]
    assert "finance_import_row_id" not in return_payable_section.split("CREATE TABLE IF NOT EXISTS government_overpayment_return_payouts", 1)[0]
    assert "remaining_amount_ntd >= 0" in return_payable_section
    assert "status = 'paid'" in return_payable_section


def test_disposition_contract_accepts_only_the_selected_branch_inputs() -> None:
    from api.schemas.government_subsidy import (
        GovernmentSubsidyOverpaymentDispositionPreviewBody,
    )

    offset = GovernmentSubsidyOverpaymentDispositionPreviewBody(
        overpayment_identity="over-1",
        disposition="offset",
        targets=[{"claim_item_id": 7, "amount_ntd": 100}],
        evidence_reference="notice-1",
    )
    returned = GovernmentSubsidyOverpaymentDispositionPreviewBody(
        overpayment_identity="over-1",
        disposition="return",
        due_date="2026-09-05",
        evidence_reference="notice-1",
    )

    assert offset.disposition == "offset"
    assert returned.disposition == "return"
