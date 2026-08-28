"""
File: test_historical_client_finance_completion_read_adapter.py
Description: 驗證 Client Finance 完成讀取的 reducer、唯讀與 fail-closed 行為。
"""

from __future__ import annotations

from datetime import date

import pytest

from infrastructure.mysql.historical_client_finance_completion_read_adapter import (
    MySqlClientFinanceCompletionReadAdapter,
)
from subsystems.orders.historical_completion_oracle import CompletionOwner


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.parameters = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        self.statements.append(statement)
        self.parameters.append(parameters)

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.cursor_calls = 0
        self.writes = 0

    def cursor(self):
        self.cursor_calls += 1
        return self.cursor_instance


class _UnavailableCursor(_Cursor):
    def execute(self, statement, parameters):
        raise ConnectionError("mysql unavailable")


def _account(version=7, case_no="CASE-1"):
    return {
        "row_kind": "account",
        "account_case_no": case_no,
        "account_aggregate_version": version,
    }


def _obligation(
    identity,
    *,
    status="settled",
    amount=0,
    contracted=1000,
    projection_version=4,
    case_no="CASE-1",
    obligation_type="deposit",
    direction="receivable_from_client",
    event_id=11,
):
    return {
        "row_kind": "obligation",
        "obligation_identity": identity,
        "obligation_case_no": case_no,
        "obligation_type": obligation_type,
        "obligation_direction": direction,
        "obligation_status": status,
        "obligation_amount_due_ntd": amount,
        "obligation_current_event_id": event_id,
        "obligation_projection_version": projection_version,
        "obligation_contracted_amount_ntd": contracted,
    }


def _ledger(
    ledger_id,
    *,
    entry_type="receipt",
    amount=1000,
    obligation_identity="ob-1",
    allocation_amount=1000,
    ordinal=1,
    reversal_of=None,
    target_entry_id=None,
    target_case_no=None,
    target_entry_type=None,
    target_amount=None,
    target_reversal_of_entry_id=None,
    reference=None,
    case_no="CASE-1",
):
    return {
        "row_kind": "ledger",
        "account_case_no": case_no,
        "ledger_entry_id": ledger_id,
        "ledger_entry_type": entry_type,
        "ledger_amount_ntd": amount,
        "ledger_occurred_on": date(2026, 8, 1),
        "ledger_reconciliation_reference": reference or f"reference-{ledger_id}",
        "ledger_reversal_of_entry_id": reversal_of,
        "target_entry_id": target_entry_id,
        "target_case_no": target_case_no,
        "target_entry_type": target_entry_type,
        "target_amount_ntd": target_amount,
        "target_reversal_of_entry_id": target_reversal_of_entry_id,
        "allocation_obligation_identity": obligation_identity,
        "allocation_amount_ntd": allocation_amount,
        "allocation_ordinal": ordinal,
    }


def _adapter(*, obligations=None, ledger=None, account=None):
    rows = [] if account == [] else [_account() if account is None else account]
    rows.extend(obligations if obligations is not None else [_obligation("ob-1")])
    rows.extend(ledger if ledger is not None else [_ledger(21)])
    cursor = _Cursor(rows)
    return MySqlClientFinanceCompletionReadAdapter(_Connection(cursor)), cursor


def test_settled_readback_uses_complete_obligation_and_allocation_lineage():
    adapter, cursor = _adapter()

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert result.owner is CompletionOwner.CLIENT_FINANCE
    assert result.aggregate_version == 7
    assert result.obligation_count == 1
    assert result.open_obligation_count == 0
    assert result.settlement_lineage_identity
    assert result.allocation_lineage_identity
    assert result.integrity_blockers == ()
    assert len(cursor.statements) == 1
    assert all("FOR UPDATE" not in statement.upper() for statement in cursor.statements)


def test_open_obligation_is_not_terminal_evidence():
    adapter, _ = _adapter(
        obligations=[_obligation("ob-1", status="open", amount=500)],
        ledger=[_ledger(21, amount=500, allocation_amount=500)],
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert result.open_obligation_count == 1
    assert result.integrity_blockers == ()


def test_current_nine_entry_types_are_recognized():
    for entry_type in (
        "receipt",
        "refund",
        "subsidy_return",
        "subsidy_advance",
        "adjustment",
    ):
        payable = entry_type in {"refund", "subsidy_return", "subsidy_advance"}
        adapter, _ = _adapter(
            obligations=[
                _obligation(
                    "ob-1",
                    obligation_type="subsidy_return" if payable else "deposit",
                    direction="payable_to_client" if payable else "receivable_from_client",
                )
            ],
            ledger=[_ledger(21, entry_type=entry_type)],
        )
        result = adapter.load_completion_readback("CASE-1")
        assert result is not None
        assert "client_finance_ledger_entry_type_invalid" not in result.integrity_blockers


def test_multi_obligation_settlement_reduces_each_obligation_independently():
    adapter, _ = _adapter(
        obligations=[
            _obligation("ob-1", contracted=1000),
            _obligation("ob-2", contracted=500),
        ],
        ledger=[
            _ledger(21, amount=1000, allocation_amount=1000, obligation_identity="ob-1"),
            _ledger(22, amount=500, allocation_amount=500, obligation_identity="ob-2", reference="reference-22"),
        ],
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert result.obligation_count == 2
    assert result.integrity_blockers == ()
    assert result.settlement_lineage_identity


@pytest.mark.parametrize("allocated", [900, 1100])
def test_non_reversal_allocation_must_conserve_ledger_amount(allocated):
    adapter, _ = _adapter(ledger=[_ledger(21, allocation_amount=allocated)])

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert "client_finance_ledger_allocation_total_mismatch" in result.integrity_blockers
    assert result.settlement_lineage_identity is None
    assert not result.readback_available


def test_unallocated_non_reversal_is_not_silently_ignored():
    adapter, _ = _adapter(ledger=[_ledger(21, obligation_identity=None, allocation_amount=None, ordinal=None)])

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert "client_finance_ledger_allocation_missing" in result.integrity_blockers
    assert result.allocation_lineage_identity is None


def test_reversal_requires_existing_same_case_legal_target():
    adapter, _ = _adapter(
        obligations=[_obligation("ob-1", status="open", amount=1000)],
        ledger=[
            _ledger(
                30,
                entry_type="reversal",
                reversal_of=21,
                target_entry_id=21,
                target_case_no="CASE-1",
                target_entry_type="receipt",
                target_amount=1000,
            )
        ],
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert "client_finance_reversal_target_invalid" in result.integrity_blockers
    assert result.settlement_lineage_identity is None


def test_valid_receipt_reversal_reopens_the_obligation_without_losing_lineage():
    adapter, _ = _adapter(
        obligations=[_obligation("ob-1", status="open", amount=1000)],
        ledger=[
            _ledger(21, amount=1000),
            _ledger(
                30,
                entry_type="reversal",
                amount=1000,
                reversal_of=21,
                target_entry_id=21,
                target_case_no="CASE-1",
                target_entry_type="receipt",
                target_amount=1000,
                allocation_amount=1000,
            ),
        ],
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert result.open_obligation_count == 1
    assert result.integrity_blockers == ()
    assert result.settlement_lineage_identity
    assert result.allocation_lineage_identity


def test_one_reversal_with_multiple_allocations_is_counted_once():
    target = [
        _ledger(21, amount=1000, obligation_identity="ob-1", allocation_amount=600),
        _ledger(21, amount=1000, obligation_identity="ob-2", allocation_amount=400, ordinal=2),
    ]
    reversal = [
        _ledger(
            30,
            entry_type="reversal",
            amount=1000,
            reversal_of=21,
            target_entry_id=21,
            target_case_no="CASE-1",
            target_entry_type="receipt",
            target_amount=1000,
            obligation_identity="ob-1",
            allocation_amount=600,
        ),
        _ledger(
            30,
            entry_type="reversal",
            amount=1000,
            reversal_of=21,
            target_entry_id=21,
            target_case_no="CASE-1",
            target_entry_type="receipt",
            target_amount=1000,
            obligation_identity="ob-2",
            allocation_amount=400,
            ordinal=2,
        ),
    ]
    adapter, _ = _adapter(
        obligations=[
            _obligation("ob-1", status="open", amount=600, contracted=600),
            _obligation("ob-2", status="open", amount=400, contracted=400),
        ],
        ledger=target + reversal,
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert result.integrity_blockers == ()
    assert result.settlement_lineage_identity


def test_repeated_reversals_cannot_exceed_one_target():
    adapter, _ = _adapter(
        obligations=[_obligation("ob-1", status="open", amount=1)],
        ledger=[
            _ledger(21, amount=1000),
            _ledger(
                30,
                entry_type="reversal",
                amount=600,
                reversal_of=21,
                target_entry_id=21,
                target_case_no="CASE-1",
                target_entry_type="receipt",
                target_amount=1000,
                allocation_amount=600,
            ),
            _ledger(
                31,
                entry_type="reversal",
                amount=500,
                reversal_of=21,
                target_entry_id=21,
                target_case_no="CASE-1",
                target_entry_type="receipt",
                target_amount=1000,
                allocation_amount=500,
            ),
        ],
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert "client_finance_reversal_amount_exceeded" in result.integrity_blockers
    assert result.settlement_lineage_identity is None


def test_reversal_cannot_target_a_reversal():
    # The target row itself is changed to a reversal, making this a direct
    # reversal-of-reversal shape while retaining the self-join evidence.
    adapter, _ = _adapter(
        obligations=[_obligation("ob-1", status="open", amount=1000)],
        ledger=[
            _ledger(
                21,
                entry_type="reversal",
                reversal_of=19,
                target_entry_id=19,
                target_case_no="CASE-1",
                target_entry_type="reversal",
                target_amount=1000,
            ),
            _ledger(
                30,
                entry_type="reversal",
                reversal_of=21,
                target_entry_id=21,
                target_case_no="CASE-1",
                target_entry_type="reversal",
                target_amount=1000,
            ),
        ],
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert "client_finance_reversal_of_reversal_forbidden" in result.integrity_blockers


def test_reversal_allocation_must_conserve_and_not_exceed_target():
    adapter, _ = _adapter(
        obligations=[_obligation("ob-1", status="open", amount=1000)],
        ledger=[
            _ledger(21, amount=1000),
            _ledger(
                30,
                entry_type="reversal",
                amount=1000,
                reversal_of=21,
                target_entry_id=21,
                target_case_no="CASE-1",
                target_entry_type="receipt",
                target_amount=1000,
                allocation_amount=900,
            ),
        ],
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert "client_finance_reversal_allocation_total_mismatch" in result.integrity_blockers or "client_finance_reversal_allocation_exceeded" in result.integrity_blockers


def test_settled_obligation_net_amount_must_match_current_event_amount():
    adapter, _ = _adapter(
        obligations=[_obligation("ob-1", contracted=1200)],
        ledger=[_ledger(21, amount=1000, allocation_amount=1000)],
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert "client_finance_obligation_net_state_mismatch" in result.integrity_blockers
    assert result.settlement_lineage_identity is None


def test_projection_version_cannot_be_ahead_of_account_version():
    adapter, _ = _adapter(
        obligations=[_obligation("ob-1", projection_version=8)]
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None
    assert "client_finance_obligation_projection_version_ahead" in result.integrity_blockers
    assert result.settlement_lineage_identity is None


def test_missing_account_returns_unavailable_port_value():
    adapter, cursor = _adapter(account=[])

    assert adapter.load_completion_readback("CASE-1") is None
    assert len(cursor.statements) == 1


def test_unavailable_mysql_error_is_not_converted_to_settled():
    cursor = _UnavailableCursor([])
    adapter = MySqlClientFinanceCompletionReadAdapter(_Connection(cursor))

    with pytest.raises(ConnectionError, match="unavailable"):
        adapter.load_completion_readback("CASE-1")


def test_case_identity_is_validated_before_read():
    adapter, _ = _adapter(account=_account(case_no="CASE-2"))

    with pytest.raises(ValueError, match="case identity"):
        adapter.load_completion_readback("CASE-1")


def test_for_update_is_rejected_without_opening_cursor():
    adapter, cursor = _adapter()

    with pytest.raises(ValueError, match="read-only"):
        adapter.load_completion_readback("CASE-1", for_update=True)

    assert cursor.statements == []


def test_adapter_does_not_commit_or_issue_mutating_sql():
    connection = _Connection(_Cursor([]))
    adapter = MySqlClientFinanceCompletionReadAdapter(connection)

    adapter.load_completion_readback("CASE-1")

    assert connection.writes == 0
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in connection.cursor_instance.statements)


def test_positive_entry_rejects_target_shape_and_ledger_case_drift() -> None:
    target_shape, _ = _adapter(
        ledger=[_ledger(21, target_entry_id=20, target_amount=1000)]
    )
    target_result = target_shape.load_completion_readback("CASE-1")

    case_drift, _ = _adapter(ledger=[_ledger(21, case_no="CASE-OTHER")])
    case_result = case_drift.load_completion_readback("CASE-1")

    assert target_result is not None and not target_result.readback_available
    assert "client_finance_positive_entry_reversal_shape_invalid" in target_result.integrity_blockers
    assert case_result is not None and not case_result.readback_available
    assert "client_finance_ledger_case_identity_mismatch" in case_result.integrity_blockers


def test_reversal_target_mirror_fields_must_match_the_target_row() -> None:
    adapter, _ = _adapter(
        obligations=[_obligation("ob-1", status="open", amount=1000)],
        ledger=[
            _ledger(21),
            _ledger(
                30,
                entry_type="reversal",
                reversal_of=21,
                target_entry_id=21,
                target_case_no="CASE-1",
                target_entry_type="refund",
                target_amount=999,
                target_reversal_of_entry_id=19,
            ),
        ],
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None and not result.readback_available
    assert {
        "client_finance_reversal_target_type_mismatch",
        "client_finance_reversal_target_amount_mismatch",
        "client_finance_reversal_target_lineage_mismatch",
    }.issubset(result.integrity_blockers)


def test_boolean_reversal_target_fields_fail_closed() -> None:
    adapter, _ = _adapter(
        obligations=[_obligation("ob-1", status="open", amount=1, contracted=1)],
        ledger=[
            _ledger(1, amount=1, allocation_amount=1),
            _ledger(
                2,
                entry_type="reversal",
                amount=1,
                allocation_amount=1,
                reversal_of=True,
                target_entry_id=True,
                target_case_no="CASE-1",
                target_entry_type="receipt",
                target_amount=True,
            ),
        ],
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None and not result.readback_available
    assert "client_finance_reversal_target_invalid" in result.integrity_blockers


def test_database_identity_fields_enforce_signed_bigint_upper_bound() -> None:
    oversized = 9_223_372_036_854_775_808
    adapter, _ = _adapter(
        obligations=[_obligation("ob-1", event_id=oversized)],
        ledger=[_ledger(oversized)],
    )

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None and not result.readback_available
    assert {
        "client_finance_obligation_event_missing",
        "client_finance_ledger_identity_invalid",
    }.issubset(result.integrity_blockers)


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("obligation", "obligation_status"),
        ("ledger", "ledger_entry_type"),
        ("ledger", "allocation_obligation_identity"),
    ],
)
def test_unhashable_source_values_return_unavailable_without_type_error(section, field) -> None:
    obligation = _obligation("ob-1")
    ledger = _ledger(21)
    target = obligation if section == "obligation" else ledger
    target[field] = []
    adapter, _ = _adapter(obligations=[obligation], ledger=[ledger])

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None and not result.readback_available


def test_unhashable_row_kind_is_rejected_as_invalid_readback_not_raw_type_error() -> None:
    rows = [_account(), _obligation("ob-1"), _ledger(21)]
    rows[2]["row_kind"] = []
    adapter = MySqlClientFinanceCompletionReadAdapter(_Connection(_Cursor(rows)))

    with pytest.raises(ValueError, match="unknown row kind"):
        adapter.load_completion_readback("CASE-1")


@pytest.mark.parametrize("occurred_on", ["garbage", "2026-99-99", []])
def test_malformed_ledger_date_returns_unavailable(occurred_on) -> None:
    row = _ledger(21)
    row["ledger_occurred_on"] = occurred_on
    adapter, _ = _adapter(ledger=[row])

    result = adapter.load_completion_readback("CASE-1")

    assert result is not None and not result.readback_available
    assert "client_finance_ledger_date_invalid" in result.integrity_blockers
