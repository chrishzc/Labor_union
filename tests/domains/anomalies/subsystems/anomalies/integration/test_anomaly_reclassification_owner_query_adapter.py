"""
File: test_anomaly_reclassification_owner_query_adapter.py
Description: 驗證 Staff recovery target 的同 connection fresh-read 與 fail-closed 契約。
"""

import pytest

from domains.anomalies.maintenance import AnomalyReclassificationTargetBinding
from infrastructure.mysql.anomaly_reclassification_owner_query_adapter import (
    MySqlAnomalyReclassificationOwnerQueryAdapter,
)


_IDENTITY = "staff-overpayment-recovery:" + ("a" * 64)
_TARGET = AnomalyReclassificationTargetBinding("staff_payables", _IDENTITY, 7)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)
        self.cursor_calls = 0

    def cursor(self):
        self.cursor_calls += 1
        return self.cursor_instance


def _row(
    *,
    version=7,
    status="open",
    identity=_IDENTITY,
    remaining_amount_ntd=500,
    staff_id=12,
    staff_payables_version=4,
):
    return {
        "recovery_identity": identity,
        "aggregate_version": version,
        "status": status,
        "remaining_amount_ntd": remaining_amount_ntd,
        "staff_id": staff_id,
        "staff_payables_version": staff_payables_version,
    }


def test_exact_target_uses_same_connection_and_for_update() -> None:
    connection = _Connection([_row()])
    adapter = MySqlAnomalyReclassificationOwnerQueryAdapter(connection)

    result = adapter.load_reclassification_target(_TARGET, for_update=True)

    assert result == _TARGET
    assert connection.cursor_calls == 1
    sql, params = connection.cursor_instance.calls[0]
    assert sql.endswith(" FOR UPDATE")
    assert params == (_IDENTITY,)


def test_stale_target_materializes_current_version_for_workflow_recheck() -> None:
    connection = _Connection([_row(version=8)])
    adapter = MySqlAnomalyReclassificationOwnerQueryAdapter(connection)

    result = adapter.load_reclassification_target(_TARGET, for_update=True)

    assert result == AnomalyReclassificationTargetBinding(
        "staff_payables", _IDENTITY, 8
    )
    assert result != _TARGET


def test_missing_target_fails_closed() -> None:
    adapter = MySqlAnomalyReclassificationOwnerQueryAdapter(_Connection([]))

    assert adapter.load_reclassification_target(_TARGET, for_update=True) is None


@pytest.mark.parametrize("status", ["recovered", "adjusted"])
def test_terminal_target_fails_closed(status) -> None:
    adapter = MySqlAnomalyReclassificationOwnerQueryAdapter(
        _Connection([_row(status=status)])
    )

    assert adapter.load_reclassification_target(_TARGET, for_update=True) is None


@pytest.mark.parametrize("status", ["open", "partially_recovered"])
def test_active_status_with_zero_remaining_fails_closed(status) -> None:
    adapter = MySqlAnomalyReclassificationOwnerQueryAdapter(
        _Connection([_row(status=status, remaining_amount_ntd=0)])
    )

    assert adapter.load_reclassification_target(_TARGET, for_update=True) is None


def test_missing_staff_payable_account_fails_closed() -> None:
    adapter = MySqlAnomalyReclassificationOwnerQueryAdapter(
        _Connection([_row(staff_payables_version=None)])
    )

    assert adapter.load_reclassification_target(_TARGET, for_update=True) is None


def test_existing_canonical_non_hex_recovery_identity_is_accepted() -> None:
    identity = "staff-overpayment-recovery:1"
    target = AnomalyReclassificationTargetBinding("staff_payables", identity, 7)
    adapter = MySqlAnomalyReclassificationOwnerQueryAdapter(
        _Connection([_row(identity=identity)])
    )

    assert adapter.load_reclassification_target(target, for_update=True) == target


def test_ambiguous_target_fails_closed() -> None:
    adapter = MySqlAnomalyReclassificationOwnerQueryAdapter(
        _Connection([_row(), _row(version=8)])
    )

    with pytest.raises(ValueError, match="staff_overpayment_recovery_target_ambiguous"):
        adapter.load_reclassification_target(_TARGET, for_update=True)


@pytest.mark.parametrize(
    "target",
    [
        AnomalyReclassificationTargetBinding("orders", "work-item:1", 1),
        AnomalyReclassificationTargetBinding(
            "staff_payables", "recovery:1", 1
        ),
    ],
)
def test_unsupported_or_noncanonical_target_is_rejected_without_query(target) -> None:
    connection = _Connection([_row()])
    adapter = MySqlAnomalyReclassificationOwnerQueryAdapter(connection)

    with pytest.raises(ValueError):
        adapter.load_reclassification_target(target, for_update=True)
    assert connection.cursor_calls == 0
