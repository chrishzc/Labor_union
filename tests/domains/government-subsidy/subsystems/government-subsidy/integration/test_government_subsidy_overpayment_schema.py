from pathlib import Path


def test_preserved_release_schema_keeps_historical_overpayment_and_return_evidence() -> None:
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


def test_preserved_legacy_return_schema_is_not_a_runtime_export_source() -> None:
    sql = Path("db/schema_parts/169_government_subsidy_overpayment_disposition.sql").read_text(encoding="utf-8")

    return_payable_section = sql.split("CREATE TABLE IF NOT EXISTS government_overpayment_return_payables", 1)[1]
    assert "finance_import_row_id" not in return_payable_section.split("CREATE TABLE IF NOT EXISTS government_overpayment_return_payouts", 1)[0]
    assert "remaining_amount_ntd >= 0" in return_payable_section
    assert "status = 'paid'" in return_payable_section


def test_disposition_contract_accepts_only_offset_and_rejects_retired_return_inputs() -> None:
    import pytest
    from pydantic import ValidationError
    from api.schemas.government_subsidy import GovernmentSubsidyOverpaymentDispositionPreviewBody
    common = {"overpayment_identity": "over-1", "evidence_reference": "notice-1"}
    offset = GovernmentSubsidyOverpaymentDispositionPreviewBody(
        **common, disposition="offset", targets=[{"claim_item_id": 7, "amount_ntd": 100}],
    )
    assert offset.disposition == "offset"
    for payload in (
        {"disposition": "return", "due_date": "2026-09-05"},
        {"disposition": "offset", "targets": []},
        {"disposition": "offset", "targets": [{"claim_item_id": 7, "amount_ntd": 100}], "due_date": "2026-09-05"},
    ):
        with pytest.raises(ValidationError):
            GovernmentSubsidyOverpaymentDispositionPreviewBody(**common, **payload)


def test_retired_return_and_refund_account_endpoints_are_absent():
    from fastapi.testclient import TestClient
    from api.main import app
    schema = app.openapi()
    prefix = "/api/v1/government-subsidy"
    removed = [
        "/overpayments/{identity}/return/preview", "/overpayments/{identity}/return/apply",
        "/overpayments/{identity}/return-reconciliation/preview", "/overpayments/{identity}/return-reconciliation/apply",
        "/overpayments/{identity}/return-reconciliation-with-excess/preview", "/overpayments/{identity}/return-reconciliation-with-excess/apply",
        "/payer/refund-account/preview", "/payer/refund-account/apply",
    ]
    client = TestClient(app)
    for path in removed:
        assert prefix + path not in schema["paths"]
        assert client.post(prefix + path.replace("{identity}", "retired"), json={}).status_code == 404
    current = schema["components"]["schemas"]["GovernmentSubsidyOverpaymentDispositionPreviewBody"]
    assert current["properties"]["disposition"]["const"] == "offset"
    assert "due_date" not in current["properties"]
