"""Historical payout evidence consumed by the Staff Payables completion readback."""

from copy import deepcopy

from infrastructure.mysql.historical_staff_payables_completion_read_adapter import (
    _build_readback,
)
from shared_kernel.fingerprints import fingerprint_payload
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


def test_payroll_correction_recovery_preserves_historical_payout_and_can_clear() -> None:
    rows = _rows()
    correction = "payroll-correction:1"
    identity = "staff-overpayment-recovery:payroll:" + fingerprint_payload({
        "payroll_correction_identity": correction, "staff_id": 8,
    }).value
    recovery = {
        "row_kind": "recovery",
        "case_no": "CASE-H",
        "identity": identity,
        "staff_id": 8,
        "version": 0,
        "status": "open",
        "amount_due_ntd": 200,
        "event_amount_ntd": 200,
        "source_event_ids": "[]",
        "source_obligation_identities": '["staff-obligation:1", "payroll-correction:1"]',
        "source_bank_fact_identities": "[]",
        "payroll_correction_identity": correction,
        "payroll_recovery_receipt_staff_id": 8,
        "payroll_recovery_receipt_amount": 200,
    }
    opened = _build_readback("CASE-H", tuple([*rows, recovery]))
    assert opened is not None and opened.readback_available
    assert opened.open_obligation_count == 0
    assert opened.open_payroll_recovery_count == 1

    cleared = _build_readback("CASE-H", tuple([*rows, {
        **recovery,
        "version": 1,
        "status": "recovered",
        "amount_due_ntd": 0,
        "recovery_event_id": 81,
        "recovery_before_ntd": 200,
        "recovery_after_ntd": 0,
        "recovery_event_status": "recovered",
    }]))
    assert cleared is not None and cleared.readback_available
    assert cleared.open_payroll_recovery_count == 0
    assert cleared.allocation_lineage_identity == opened.allocation_lineage_identity
    assert cleared.settlement_lineage_identity != opened.settlement_lineage_identity

    invalid = _build_readback("CASE-H", tuple([*rows, {
        **recovery, "payroll_recovery_receipt_amount": 201,
    }]))
    assert invalid is not None and not invalid.readback_available
    assert "staff_payables_payroll_recovery_receipt_mismatch" in invalid.integrity_blockers

    unrelated = _build_readback("CASE-H", tuple([*rows, {
        **recovery, "source_obligation_identities": '["staff-obligation:2", "payroll-correction:1"]',
    }]))
    assert unrelated is not None and unrelated.readback_available
    assert unrelated.open_payroll_recovery_count == 0


def test_frozen_payable_uses_linked_reversal_and_recovered_cash_as_terminal_evidence() -> None:
    payroll, root = _rows()
    root = {key: value for key, value in root.items() if not key.startswith("historical_")}
    root.update(projection_amount_ntd=800, net_paid_ntd=1000, balance_ntd=-200,
                projection_status="anomaly", projection_version=6, account_version=8,
                target_event_id=71, target_staff_id=8)
    correction = "staff-handover:synthetic"
    reversal = {
        "row_kind": "obligation", "case_no": "CASE-H", "identity": correction,
        "related_identity": root["identity"], "staff_id": 8, "assignment_id": 3,
        "direction": "receivable_from_staff", "version": 7, "resulting_version": 7,
        "current_event_id": 12, "status": "open", "event_type": "reversal",
        "amount_due_ntd": 200, "event_amount_ntd": 200, "account_version": 8,
    }
    payout = {
        "row_kind": "payout", "case_no": "CASE-H", "identity": "71",
        "related_identity": root["identity"], "staff_id": 8, "linked_staff_id": 8,
        "event_type": "payout", "event_amount_ntd": 1000, "allocated_amount_ntd": 1000,
        "allocation_ordinal": 1, "finance_import_row_id": 15, "bank_identity_hash": "a" * 64,
        "reconciliation_reference": "synthetic-payout",
    }
    recovery_identity = "staff-overpayment-recovery:payroll:" + fingerprint_payload({
        "payroll_correction_identity": correction, "staff_id": 8,
    }).value
    recovery = {
        "row_kind": "recovery", "case_no": "CASE-H", "identity": recovery_identity,
        "staff_id": 8, "version": 1, "status": "recovered", "amount_due_ntd": 0,
        "event_amount_ntd": 200, "source_event_ids": "[]", "source_bank_fact_identities": "[]",
        "source_obligation_identities": '["staff-obligation:1", "staff-handover:synthetic"]',
        "payroll_correction_identity": correction, "payroll_recovery_receipt_staff_id": 8,
        "payroll_recovery_receipt_amount": 200, "recovery_event_id": 81,
        "recovery_before_ntd": 200, "recovery_after_ntd": 0, "recovery_event_status": "recovered",
    }

    result = _build_readback("CASE-H", (payroll, root, reversal, payout, recovery))
    assert result is not None and result.readback_available, result
    assert result.obligation_count == 1
    assert result.open_obligation_count == 0
    assert result.open_payroll_recovery_count == 0
    assert result.allocation_lineage_identity is not None

    missing = _build_readback("CASE-H", (payroll, root, reversal, payout))
    assert missing is not None and not missing.readback_available
    assert "staff_payables_payroll_recovery_coverage_missing" in missing.integrity_blockers
