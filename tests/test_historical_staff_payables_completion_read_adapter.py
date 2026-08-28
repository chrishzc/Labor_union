"""
File: test_historical_staff_payables_completion_read_adapter.py
Description: 驗證 Staff Payables 完成讀取的單一快照、完整向量與追回非阻擋語意。
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest

from infrastructure.mysql.historical_staff_payables_completion_read_adapter import (
    MySqlStaffPayablesCompletionReadAdapter,
    _CURRENT_CASE_READ_SQL,
)
from subsystems.orders.historical_completion_oracle import (
    CompletionOwner,
    SettlementSourceKind,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, parameters):
        self.calls.append((sql, parameters))

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.cursor_value = _Cursor(rows)

    def cursor(self):
        return self.cursor_value


def _rows():
    return [
        {"row_kind": "payroll_account", "case_no": "CASE-1", "version": 7},
        {
            "row_kind": "obligation",
            "case_no": "CASE-1",
            "identity": "obligation:1",
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
            "projection_amount_ntd": 1000,
            "net_paid_ntd": 1000,
            "balance_ntd": 0,
            "projection_status": "completed",
            "account_version": 5,
            "projection_version": 5,
            "target_event_id": 21,
            "target_staff_id": 8,
        },
        {
            "row_kind": "payout",
            "case_no": "CASE-1",
            "identity": "21",
            "related_identity": "obligation:1",
            "staff_id": 8,
            "version": 21,
            "event_type": "payout",
            "event_amount_ntd": 1000,
            "allocated_amount_ntd": 1000,
            "allocation_ordinal": 1,
            "reversal_of_event_id": None,
            "target_event_id": None,
            "target_staff_id": None,
            "finance_import_row_id": 31,
            "bank_identity_hash": "a" * 64,
            "reconciliation_reference": "bank-row:31",
            "target_event_type": None,
            "target_event_amount_ntd": None,
            "linked_staff_id": 8,
        },
    ]


def _load(rows=None):
    connection = _Connection(_rows() if rows is None else rows)
    result = MySqlStaffPayablesCompletionReadAdapter(connection).load_completion_readback("CASE-1")
    return result, connection.cursor_value


def _open_recovery_row(version=0):
    return {
        "row_kind": "recovery",
        "case_no": "CASE-1",
        "identity": "recovery:1",
        "staff_id": 8,
        "version": version,
        "status": "open",
        "amount_due_ntd": 300,
        "event_amount_ntd": 300,
        "source_event_ids": "[21]",
        "source_obligation_identities": '["obligation:1"]',
        "source_bank_fact_identities": '["finance-import-row:31"]',
        "recovery_event_id": None,
    }


def test_reads_one_statement_and_returns_uncompressed_source_vector() -> None:
    result, cursor = _load()

    assert result is not None
    assert result.owner is CompletionOwner.STAFF_PAYABLES
    assert result.aggregate_version is None
    assert result.readback_available
    assert result.open_obligation_count == 0
    assert len(cursor.calls) == 1
    assert cursor.calls[0][1] == ("CASE-1",) * 5
    assert {item.kind for item in result.source_versions} >= {
        SettlementSourceKind.PAYROLL_CASE_ACCOUNT,
        SettlementSourceKind.STAFF_OBLIGATION,
        SettlementSourceKind.STAFF_PAYABLE_ACCOUNT,
        SettlementSourceKind.STAFF_PAYABLE_PROJECTION,
        SettlementSourceKind.STAFF_PAYOUT_EVENT,
        SettlementSourceKind.STAFF_PAYOUT_ALLOCATION,
        SettlementSourceKind.STAFF_BANK_FACT,
    }


def test_mysql_union_decimal_versions_are_accepted_when_integral() -> None:
    rows = deepcopy(_rows())
    rows[0]["version"] = Decimal("7")
    rows[1]["version"] = Decimal("4")
    rows[2]["version"] = Decimal("21")

    result, _ = _load(rows)

    assert result is not None and result.readback_available
    assert "staff_payables_source_version_invalid" not in result.integrity_blockers
    assert "staff_payables_obligation_version_invalid" not in result.integrity_blockers


def test_open_recovery_remains_in_lineage_without_blocking_completion() -> None:
    rows = _rows() + [_open_recovery_row()]

    result, _ = _load(rows)

    assert result is not None and result.readback_available
    assert result.open_obligation_count == 0
    assert any(item.kind is SettlementSourceKind.STAFF_OVERPAYMENT_RECOVERY for item in result.source_versions)


def test_projection_current_event_must_allocate_to_projected_obligation() -> None:
    rows = deepcopy(_rows())
    rows[2]["related_identity"] = "obligation:other"

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert (
        "staff_payables_projection_event_obligation_mismatch"
        in result.integrity_blockers
    )


def test_recovery_claim_cannot_exceed_source_payout_amount() -> None:
    rows = _rows() + [
        {
            **_open_recovery_row(),
            "amount_due_ntd": 1_001,
            "event_amount_ntd": 1_001,
        }
    ]

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_recovery_amount_exceeds_sources" in result.integrity_blockers


def test_recovery_roots_cannot_reuse_one_payout_source() -> None:
    rows = _rows() + [
        _open_recovery_row(),
        {**_open_recovery_row(), "identity": "recovery:2"},
    ]

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_recovery_payout_source_reused" in result.integrity_blockers


def test_recovery_required_projection_is_terminal_but_anomaly_is_open() -> None:
    recovery_rows = deepcopy(_rows()) + [_open_recovery_row()]
    recovery_rows[1]["projection_status"] = "recovery_required"
    recovery_result, _ = _load(recovery_rows)

    anomaly_rows = deepcopy(_rows())
    anomaly_rows[1]["projection_status"] = "anomaly"
    anomaly_rows[1]["net_paid_ntd"] = 1200
    anomaly_rows[1]["balance_ntd"] = -200
    anomaly_rows[2]["event_amount_ntd"] = 1200
    anomaly_rows[2]["allocated_amount_ntd"] = 1200
    anomaly_result, _ = _load(anomaly_rows)

    assert recovery_result is not None and recovery_result.open_obligation_count == 0
    assert anomaly_result is not None and anomaly_result.open_obligation_count == 1


def test_recovery_required_projection_without_applicable_root_fails_closed() -> None:
    rows = deepcopy(_rows())
    rows[1]["projection_status"] = "recovery_required"

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_recovery_required_root_missing" in result.integrity_blockers


def test_recovery_version_must_equal_immutable_event_count() -> None:
    rows = _rows() + [
        {
            **_open_recovery_row(version=2),
            "status": "partially_recovered",
            "amount_due_ntd": 200,
            "recovery_event_id": 41,
            "recovery_before_ntd": 300,
            "recovery_after_ntd": 200,
            "recovery_event_status": "partially_recovered",
        }
    ]

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_recovery_event_version_mismatch" in result.integrity_blockers


def test_recovery_events_must_form_one_continuous_amount_lineage() -> None:
    base = {
        **_open_recovery_row(version=2),
        "status": "recovered",
        "amount_due_ntd": 0,
    }
    rows = _rows() + [
        {
            **base,
            "recovery_event_id": 41,
            "recovery_before_ntd": 300,
            "recovery_after_ntd": 200,
            "recovery_event_status": "partially_recovered",
        },
        {
            **base,
            "recovery_event_id": 42,
            "recovery_before_ntd": 150,
            "recovery_after_ntd": 0,
            "recovery_event_status": "recovered",
        },
    ]

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_recovery_event_lineage_discontinuous" in result.integrity_blockers


def test_payout_allocation_case_and_obligation_attribution_fail_closed() -> None:
    case_mismatch = deepcopy(_rows())
    case_mismatch[2]["case_no"] = "CASE-OTHER"
    mismatch_result, _ = _load(case_mismatch)

    missing_obligation = deepcopy(_rows())
    missing_obligation[2]["allocated_amount_ntd"] = 500
    missing_obligation.append(
        {
            **missing_obligation[2],
            "related_identity": "obligation:ghost",
            "allocated_amount_ntd": 500,
            "allocation_ordinal": 2,
        }
    )
    missing_result, _ = _load(missing_obligation)

    assert mismatch_result is not None and not mismatch_result.readback_available
    assert "staff_payables_payout_allocation_case_mismatch" in mismatch_result.integrity_blockers
    assert missing_result is not None and not missing_result.readback_available
    assert "staff_payables_payout_allocation_obligation_missing" in missing_result.integrity_blockers


def test_duplicate_source_identity_with_different_version_returns_unavailable() -> None:
    rows = deepcopy(_rows())
    duplicate = deepcopy(rows[1])
    duplicate["version"] = 5
    rows.append(duplicate)

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_obligation_duplicate" in result.integrity_blockers


def test_duplicate_recovery_sources_events_and_invalid_intermediate_status_fail_closed() -> None:
    duplicate_sources = {
        **_open_recovery_row(),
        "source_event_ids": "[21,21]",
        "source_obligation_identities": '["obligation:1","obligation:1"]',
        "source_bank_fact_identities": '["finance-import-row:31","finance-import-row:31"]',
    }
    source_result, _ = _load(_rows() + [duplicate_sources])

    base = {**_open_recovery_row(version=2), "status": "recovered", "amount_due_ntd": 0}
    event_rows = _rows() + [
        {**base, "recovery_event_id": 41, "recovery_before_ntd": 300, "recovery_after_ntd": 200, "recovery_event_status": "recovered"},
        {**base, "recovery_event_id": 41, "recovery_before_ntd": 200, "recovery_after_ntd": 0, "recovery_event_status": "recovered"},
    ]
    event_result, _ = _load(event_rows)

    assert source_result is not None and not source_result.readback_available
    assert "staff_payables_recovery_sources_invalid" in source_result.integrity_blockers
    assert event_result is not None and not event_result.readback_available
    assert {
        "staff_payables_recovery_event_duplicate",
        "staff_payables_recovery_event_status_invalid",
    }.issubset(event_result.integrity_blockers)


def test_obligation_event_type_and_reversal_target_amount_fail_closed() -> None:
    invalid_event = deepcopy(_rows())
    invalid_event[1]["event_type"] = "future_event"
    event_result, _ = _load(invalid_event)

    reversal = deepcopy(_rows())
    reversal.append(
        {
            **reversal[2],
            "identity": "22",
            "event_type": "return",
            "event_amount_ntd": 100,
            "allocated_amount_ntd": 100,
            "reversal_of_event_id": 21,
            "target_event_id": 21,
            "target_event_type": "payout",
            "target_event_amount_ntd": 999,
            "finance_import_row_id": 32,
            "bank_identity_hash": "b" * 64,
            "reconciliation_reference": "bank-row:32",
        }
    )
    reversal_result, _ = _load(reversal)

    assert event_result is not None and not event_result.readback_available
    assert "staff_payables_obligation_event_type_invalid" in event_result.integrity_blockers
    assert reversal_result is not None and not reversal_result.readback_available
    assert "staff_payables_reversal_target_amount_mismatch" in reversal_result.integrity_blockers


def test_bank_evidence_is_fingerprint_material_and_cannot_be_reused() -> None:
    first, _ = _load()
    changed_rows = deepcopy(_rows())
    changed_rows[2]["bank_identity_hash"] = "b" * 64
    changed_rows[2]["reconciliation_reference"] = "bank-row:31-reconciled"
    changed, _ = _load(changed_rows)

    reused_rows = deepcopy(_rows())
    reused_rows.append(
        {
            **reused_rows[2],
            "identity": "22",
            "allocated_amount_ntd": 1000,
        }
    )
    reused, _ = _load(reused_rows)

    assert first is not None and changed is not None
    assert first.settlement_lineage_identity != changed.settlement_lineage_identity
    assert first.allocation_lineage_identity != changed.allocation_lineage_identity
    assert reused is not None and not reused.readback_available
    assert "staff_payables_bank_fact_reused" in reused.integrity_blockers


def test_obligation_material_fields_are_validated_and_fingerprint_material() -> None:
    baseline, _ = _load()
    changed_rows = deepcopy(_rows())
    changed_rows[1]["event_type"] = "established"
    changed, _ = _load(changed_rows)

    invalid_rows = deepcopy(_rows())
    invalid_rows[1]["direction"] = "receivable_from_staff"
    invalid, _ = _load(invalid_rows)

    assert baseline is not None and changed is not None
    assert baseline.settlement_lineage_identity != changed.settlement_lineage_identity
    assert baseline.allocation_lineage_identity != changed.allocation_lineage_identity
    assert invalid is not None and not invalid.readback_available
    assert "staff_payables_obligation_direction_invalid" in invalid.integrity_blockers


def test_recovery_source_event_must_allocate_exact_claimed_obligations_for_staff() -> None:
    rows = deepcopy(_rows())
    rows.append(
        {
            **rows[2],
            "case_no": "CASE-OTHER",
            "identity": "22",
            "related_identity": "obligation:other",
            "staff_id": 9,
            "linked_staff_id": 9,
            "finance_import_row_id": 32,
            "bank_identity_hash": "b" * 64,
            "reconciliation_reference": "bank-row:32",
        }
    )
    rows.append(
        {
            **_open_recovery_row(),
            "source_event_ids": "[22]",
            "source_bank_fact_identities": '["finance-import-row:32"]',
        }
    )

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert {
        "staff_payables_recovery_obligation_source_mismatch",
        "staff_payables_recovery_source_staff_mismatch",
    }.issubset(result.integrity_blockers)


@pytest.mark.parametrize(
    ("row_index", "field", "blocker"),
    [
        (0, "row_kind", "staff_payables_row_kind_invalid"),
        (1, "event_type", "staff_payables_obligation_event_type_invalid"),
        (1, "projection_status", "staff_payables_projection_status_invalid"),
        (2, "event_type", "staff_payables_payout_event_type_invalid"),
    ],
)
def test_unhashable_source_enum_values_return_unavailable(
    row_index, field, blocker
) -> None:
    rows = deepcopy(_rows())
    rows[row_index][field] = []

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert blocker in result.integrity_blockers


def test_payout_event_rejects_non_null_or_malformed_reversal_target_fields() -> None:
    rows = deepcopy(_rows())
    rows[2]["target_event_amount_ntd"] = []

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_payout_reversal_shape_invalid" in result.integrity_blockers

    reversal_rows = deepcopy(_rows())
    reversal_rows.append(
        {
            **reversal_rows[2],
            "identity": "22",
            "event_type": "return",
            "event_amount_ntd": 100,
            "allocated_amount_ntd": 100,
            "reversal_of_event_id": [],
            "target_event_id": 21,
            "target_staff_id": 8,
            "target_event_type": "payout",
            "target_event_amount_ntd": 1000,
            "finance_import_row_id": 32,
        }
    )
    reversal_result, _ = _load(reversal_rows)

    assert reversal_result is not None and not reversal_result.readback_available
    assert "staff_payables_reversal_target_invalid" in reversal_result.integrity_blockers


@pytest.mark.parametrize("reference", ["   ", "x" * 192, []])
def test_bank_reconciliation_reference_must_be_canonical(reference) -> None:
    rows = deepcopy(_rows())
    rows[2]["reconciliation_reference"] = reference

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_reconciliation_reference_missing" in result.integrity_blockers


def test_cross_case_extra_allocation_and_cross_staff_ownership_fail_closed() -> None:
    rows = deepcopy(_rows())
    rows[2]["allocated_amount_ntd"] = 500
    rows.append(
        {
            **rows[2],
            "case_no": "CASE-OTHER",
            "related_identity": "obligation:other",
            "staff_id": 9,
            "linked_staff_id": 9,
            "allocated_amount_ntd": 500,
            "allocation_ordinal": 2,
        }
    )

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert {
        "staff_payables_payout_allocation_case_mismatch",
        "staff_payables_payout_allocation_obligation_missing",
        "staff_payables_payout_event_identity_conflict",
    }.issubset(result.integrity_blockers)


def test_payout_and_reversal_staff_must_match_obligation_and_target_owner() -> None:
    rows = deepcopy(_rows())
    rows[2]["staff_id"] = 9
    rows[2]["linked_staff_id"] = 9
    payout_result, _ = _load(rows)

    reversal_rows = deepcopy(_rows())
    reversal_rows.append(
        {
            **reversal_rows[2],
            "identity": "22",
            "event_type": "return",
            "event_amount_ntd": 100,
            "allocated_amount_ntd": 100,
            "staff_id": 9,
            "linked_staff_id": 9,
            "reversal_of_event_id": 21,
            "target_event_id": 21,
            "target_staff_id": 9,
            "target_event_type": "payout",
            "target_event_amount_ntd": 1000,
            "finance_import_row_id": 32,
        }
    )
    reversal_result, _ = _load(reversal_rows)

    assert payout_result is not None and not payout_result.readback_available
    assert "staff_payables_payout_obligation_staff_mismatch" in payout_result.integrity_blockers
    assert reversal_result is not None and not reversal_result.readback_available
    assert "staff_payables_reversal_target_staff_mismatch" in reversal_result.integrity_blockers


def test_duplicate_or_conflicting_recovery_and_unattributed_sources_fail_closed() -> None:
    duplicate_result, _ = _load(_rows() + [_open_recovery_row(), _open_recovery_row()])

    conflicting = _rows() + [
        _open_recovery_row(),
        {**_open_recovery_row(), "status": "recovered", "amount_due_ntd": 0},
    ]
    conflict_result, _ = _load(conflicting)

    unattributed = {
        **_open_recovery_row(),
        "source_obligation_identities": '["obligation:other"]',
    }
    unattributed_result, _ = _load(_rows() + [unattributed])

    assert duplicate_result is not None and not duplicate_result.readback_available
    assert "staff_payables_recovery_duplicate" in duplicate_result.integrity_blockers
    assert conflict_result is not None and not conflict_result.readback_available
    assert "staff_payables_recovery_identity_conflict" in conflict_result.integrity_blockers
    assert unattributed_result is not None and not unattributed_result.readback_available
    assert "staff_payables_recovery_case_attribution_missing" in unattributed_result.integrity_blockers


def test_malformed_source_identity_returns_unavailable_instead_of_raising() -> None:
    rows = deepcopy(_rows())
    rows[1]["identity"] = " bad identity "

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_obligation_identity_invalid" in result.integrity_blockers


def test_immutable_open_obligation_uses_terminal_payout_projection() -> None:
    rows = deepcopy(_rows())
    rows[1].update(
        status="open",
        amount_due_ntd=1000,
        event_amount_ntd=1000,
    )

    result, _ = _load(rows)

    assert result is not None and result.readback_available
    assert result.open_obligation_count == 0


def test_unknown_row_kind_and_invalid_obligation_state_fail_closed() -> None:
    rows = deepcopy(_rows())
    rows[1]["status"] = "settled"
    rows[1]["amount_due_ntd"] = 1
    rows[1]["event_amount_ntd"] = 1
    rows.append({"row_kind": "future_source", "case_no": "CASE-1"})

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert {
        "staff_payables_row_kind_invalid",
        "staff_payables_obligation_status_invalid",
    }.issubset(result.integrity_blockers)


def test_cross_case_recovery_source_fails_closed() -> None:
    rows = _rows() + [
        {
            "row_kind": "recovery",
            "case_no": "CASE-1",
            "identity": "recovery:1",
            "staff_id": 8,
            "version": 2,
            "status": "open",
            "amount_due_ntd": 300,
            "source_event_ids": "[21]",
            "source_obligation_identities": '["obligation:1", "obligation:other-case"]',
            "source_bank_fact_identities": '["finance-import-row:31"]',
            "recovery_event_id": None,
        }
    ]

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_recovery_cross_case_ambiguous" in result.integrity_blockers


def test_recovery_row_case_identity_must_match_query_case() -> None:
    recovery = _open_recovery_row()
    recovery["case_no"] = "CASE-OTHER"

    result, _ = _load(_rows() + [recovery])

    assert result is not None and not result.readback_available
    assert "staff_payables_recovery_case_mismatch" in result.integrity_blockers


def test_boolean_staff_and_target_mirrors_fail_closed() -> None:
    payout_rows = deepcopy(_rows())
    payout_rows[2]["staff_id"] = 1
    payout_rows[2]["linked_staff_id"] = True
    payout_result, _ = _load(payout_rows)

    reversal_rows = deepcopy(_rows())
    reversal_rows.append(
        {
            **reversal_rows[2],
            "identity": "22",
            "event_type": "return",
            "event_amount_ntd": 1,
            "allocated_amount_ntd": 1,
            "reversal_of_event_id": 21,
            "target_event_id": 21,
            "target_staff_id": True,
            "target_event_type": "payout",
            "target_event_amount_ntd": True,
            "finance_import_row_id": 32,
        }
    )
    reversal_result, _ = _load(reversal_rows)

    assert payout_result is not None and not payout_result.readback_available
    assert "staff_payables_payout_staff_mismatch" in payout_result.integrity_blockers
    assert reversal_result is not None and not reversal_result.readback_available
    assert "staff_payables_reversal_target_invalid" in reversal_result.integrity_blockers


def test_incomplete_full_event_allocation_fails_closed() -> None:
    rows = deepcopy(_rows())
    rows[2]["event_amount_ntd"] = 1200

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_payout_allocation_incomplete" in result.integrity_blockers


def test_projection_uses_its_own_version_and_rejects_invalid_money_formula() -> None:
    rows = deepcopy(_rows())
    rows[1]["projection_version"] = 6
    rows[1]["account_version"] = 6
    result, _ = _load(rows)

    invalid_rows = deepcopy(rows)
    invalid_rows[1]["projection_status"] = "partially_paid"
    invalid_rows[1]["net_paid_ntd"] = 400
    invalid_rows[1]["balance_ntd"] = 999
    invalid_result, _ = _load(invalid_rows)

    assert result is not None
    projection_source = next(
        item for item in result.source_versions
        if item.kind is SettlementSourceKind.STAFF_PAYABLE_PROJECTION
    )
    assert projection_source.version == 6
    assert invalid_result is not None and not invalid_result.readback_available
    assert "staff_payables_projection_balance_invalid" in invalid_result.integrity_blockers


def test_return_allocation_must_match_target_payout_allocation() -> None:
    rows = _rows() + [
        {
            "row_kind": "payout",
            "case_no": "CASE-OTHER",
            "identity": "22",
            "related_identity": "obligation:other",
            "staff_id": 8,
            "version": 22,
            "event_type": "return",
            "event_amount_ntd": 100,
            "allocated_amount_ntd": 100,
            "allocation_ordinal": 1,
            "reversal_of_event_id": 21,
            "target_event_id": 21,
            "target_staff_id": 8,
            "target_event_type": "payout",
            "target_event_amount_ntd": 1000,
            "finance_import_row_id": 32,
            "bank_identity_hash": "b" * 64,
            "reconciliation_reference": "bank-row:32",
            "linked_staff_id": 8,
        }
    ]

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_reversal_allocation_exceeds_target" in result.integrity_blockers


def test_incomplete_recovery_sources_and_non_exact_versions_fail_closed() -> None:
    rows = _rows() + [
        {
            "row_kind": "recovery",
            "case_no": "CASE-1",
            "identity": "recovery:1",
            "staff_id": 8,
            "version": 2.5,
            "status": "recovered",
            "amount_due_ntd": 10,
            "event_amount_ntd": 300,
            "source_event_ids": "[]",
            "source_obligation_identities": '["obligation:1"]',
            "source_bank_fact_identities": "[]",
            "recovery_event_id": None,
        }
    ]

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert {
        "staff_payables_recovery_sources_incomplete",
        "staff_payables_recovery_terminal_amount_invalid",
        "staff_payables_source_version_invalid",
    }.issubset(result.integrity_blockers)


def test_numeric_strings_are_rejected_except_union_event_identity() -> None:
    rows = deepcopy(_rows())
    rows[1]["version"] = "4"
    rows[1]["amount_due_ntd"] = "0"
    rows[1]["projection_version"] = "5"
    rows[2]["allocated_amount_ntd"] = "1000"
    rows[2]["allocation_ordinal"] = "1"
    rows[2]["finance_import_row_id"] = "31"

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert {
        "staff_payables_obligation_version_invalid",
        "staff_payables_obligation_amount_invalid",
        "staff_payables_projection_version_invalid",
        "staff_payables_allocation_amount_invalid",
        "staff_payables_allocation_ordinal_invalid",
        "staff_payables_bank_fact_missing",
    }.issubset(result.integrity_blockers)


def test_oversized_union_event_identity_returns_unavailable() -> None:
    rows = deepcopy(_rows())
    rows[2]["identity"] = "9" * 192

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_payout_event_invalid" in result.integrity_blockers


def test_database_identity_fields_enforce_signed_bigint_upper_bound() -> None:
    oversized = 9_223_372_036_854_775_808
    rows = deepcopy(_rows())
    rows[1]["staff_id"] = oversized
    rows[1]["assignment_id"] = oversized
    rows[1]["current_event_id"] = oversized
    rows[2]["finance_import_row_id"] = oversized

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert {
        "staff_payables_staff_identity_invalid",
        "staff_payables_assignment_identity_invalid",
        "staff_payables_obligation_event_missing",
        "staff_payables_bank_fact_missing",
    }.issubset(result.integrity_blockers)


def test_malformed_obligation_event_bank_and_reversal_shapes_fail_closed() -> None:
    rows = deepcopy(_rows())
    rows[1]["amount_due_ntd"] = -1
    rows[1]["event_amount_ntd"] = -1
    rows[1]["resulting_version"] = 0
    rows[2]["bank_identity_hash"] = "A" * 64
    rows[2]["reversal_of_event_id"] = 20

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert {
        "staff_payables_obligation_amount_invalid",
        "staff_payables_obligation_event_missing",
        "staff_payables_bank_identity_invalid",
        "staff_payables_payout_reversal_shape_invalid",
    }.issubset(result.integrity_blockers)


def test_terminal_recovery_requires_matching_current_event_lineage() -> None:
    rows = _rows() + [
        {
            "row_kind": "recovery",
            "case_no": "CASE-1",
            "identity": "recovery:1",
            "staff_id": 8,
            "version": 1,
            "status": "recovered",
            "amount_due_ntd": 0,
            "event_amount_ntd": 300,
            "source_event_ids": "[21]",
            "source_obligation_identities": '["obligation:1"]',
            "source_bank_fact_identities": '["finance-import-row:31"]',
            "recovery_event_id": None,
        }
    ]

    result, _ = _load(rows)

    assert result is not None and not result.readback_available
    assert "staff_payables_recovery_event_lineage_missing" in result.integrity_blockers


def test_for_update_is_rejected_before_database_access() -> None:
    connection = _Connection(_rows())
    adapter = MySqlStaffPayablesCompletionReadAdapter(connection)

    with pytest.raises(ValueError, match="read-only"):
        adapter.load_completion_readback("CASE-1", for_update=True)

    assert connection.cursor_value.calls == []


def test_payout_identity_cast_uses_the_canonical_union_collation() -> None:
    assert (
        "CAST(e.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci"
        in _CURRENT_CASE_READ_SQL
    )
