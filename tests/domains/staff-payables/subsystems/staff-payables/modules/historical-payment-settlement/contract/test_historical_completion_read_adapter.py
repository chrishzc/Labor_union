"""Historical payout evidence consumed by the Staff Payables completion readback."""

from copy import deepcopy

from infrastructure.mysql.historical_staff_payables_completion_read_adapter import (
    _build_readback,
)
from subsystems.orders.historical_completion_oracle import SettlementSourceKind


def _rows() -> list[dict[str, object]]:
    return [
        {"row_kind": "payroll_account", "case_no": "CASE-H", "version": 7},
        {
            "row_kind": "obligation",
            "case_no": "CASE-H",
            "identity": "staff-obligation:1",
            "staff_id": 8,
            "assignment_id": 3,
            "direction": "payable_to_staff",
            "version": 4,
            "status": "open",
            "amount_due_ntd": 1000,
            "current_event_id": 11,
            "resulting_version": 4,
            "event_type": "rebuilt",
            "event_amount_ntd": 1000,
            "account_version": 6,
            "historical_projection_event_id": 41,
            "historical_projection_case_no": "CASE-H",
            "historical_projection_staff_id": 8,
            "historical_confirmation_kind": "paid",
            "historical_amount_snapshot_ntd": 1000,
            "historical_obligation_payroll_version": 4,
            "historical_staff_payables_version": 6,
            "historical_event_identity": "historical-staff-payout:41",
            "historical_event_case_no": "CASE-H",
            "historical_event_staff_id": 8,
            "historical_event_confirmation_kind": "paid",
            "historical_event_payer_role": "union",
            "historical_event_payee_role": "staff",
            "historical_event_expected_version": 5,
            "historical_event_resulting_version": 6,
            "historical_event_adoption_receipt_id": 19,
            "historical_link_amount_snapshot_ntd": 1000,
            "historical_link_payroll_version": 4,
            "historical_link_ordinal": 1,
        },
    ]


def test_exact_historical_projection_is_terminal_without_bank_lineage() -> None:
    result = _build_readback("CASE-H", tuple(_rows()))

    assert result is not None and result.readback_available
    assert result.open_obligation_count == 0
    assert result.allocation_lineage_identity is not None
    assert {item.kind for item in result.source_versions} >= {
        SettlementSourceKind.HISTORICAL_STAFF_PAYOUT_PROJECTION,
        SettlementSourceKind.HISTORICAL_STAFF_PAYOUT_EVENT,
        SettlementSourceKind.HISTORICAL_STAFF_PAYOUT_LINK,
    }
    assert SettlementSourceKind.STAFF_BANK_FACT not in {
        item.kind for item in result.source_versions
    }


def test_stale_historical_projection_reopens_obligation() -> None:
    rows = deepcopy(_rows())
    rows[1]["version"] = 5
    rows[1]["resulting_version"] = 5

    result = _build_readback("CASE-H", tuple(rows))

    assert result is not None and result.readback_available
    assert result.open_obligation_count == 1


def test_new_obligation_without_payment_evidence_is_nonterminal() -> None:
    rows = deepcopy(_rows())
    for key in tuple(rows[1]):
        if key.startswith("historical_"):
            rows[1][key] = None

    result = _build_readback("CASE-H", tuple(rows))

    assert result is not None and result.readback_available
    assert result.open_obligation_count == 1
    assert result.allocation_lineage_identity is None
