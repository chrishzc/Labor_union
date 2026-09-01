"""Zero-payment terminal readback for historical Client Finance."""

from infrastructure.mysql.historical_client_finance_completion_read_adapter import _readback


def test_settled_zero_obligation_needs_no_ledger_or_allocation() -> None:
    result = _readback(
        "CASE-ZERO",
        {"account_aggregate_version": 3},
        ({
            "obligation_identity": "historical-service:CASE-ZERO:revision:1:client:receivable_from_client",
            "case_no": "CASE-ZERO",
            "obligation_type": "adjustment",
            "direction": "receivable_from_client",
            "status": "settled",
            "amount_due_ntd": 0,
            "current_event_id": 41,
            "projection_version": 3,
            "contracted_amount_ntd": 0,
        },),
        (),
    )

    assert result.readback_available is True
    assert result.open_obligation_count == 0
    assert result.settlement_lineage_identity is not None
    assert result.allocation_lineage_identity is not None
    assert result.integrity_blockers == ()


def test_open_obligation_is_terminal_through_historical_payment_lineage() -> None:
    identity = "historical-service:CASE-H:revision:1:client:receivable_from_client"
    result = _readback(
        "CASE-H",
        {"account_aggregate_version": 2},
        ({
            "obligation_identity": identity,
            "case_no": "CASE-H",
            "obligation_type": "adjustment",
            "direction": "receivable_from_client",
            "status": "open",
            "amount_due_ntd": 8700,
            "current_event_id": 41,
            "projection_version": 1,
            "contracted_amount_ntd": 8700,
        },),
        (),
        ({
            "obligation_identity": identity,
            "projection_event_id": 52,
            "projection_case_no": "CASE-H",
            "projection_confirmation_kind": "settled",
            "projection_amount_ntd": 8700,
            "projection_obligation_version": 1,
            "projection_account_version": 2,
            "event_identity": "historical-client-payment:CASE-H:52",
            "event_case_no": "CASE-H",
            "event_direction": "receivable_from_client",
            "event_confirmation_kind": "settled",
            "event_payer_role": "client",
            "event_payee_role": "union",
            "event_adoption_receipt_id": 19,
            "event_expected_version": 1,
            "event_resulting_version": 2,
            "link_amount_ntd": 8700,
            "link_obligation_type": "adjustment",
            "link_direction": "receivable_from_client",
            "link_obligation_version": 1,
            "link_ordinal": 1,
        },),
    )

    assert result.readback_available is True
    assert result.open_obligation_count == 0
    assert result.settlement_lineage_identity is not None
    assert result.allocation_lineage_identity is not None
    assert result.integrity_blockers == ()
