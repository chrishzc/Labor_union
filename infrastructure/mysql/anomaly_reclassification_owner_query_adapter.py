"""
File: anomaly_reclassification_owner_query_adapter.py
Description: 以同一 MySQL connection 鎖定 Staff Payables successor recovery target。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Mapping

from domains.anomalies.maintenance import AnomalyReclassificationTargetBinding


_STAFF_PAYABLES_DOMAIN = "staff_payables"
_RECOVERY_IDENTITY_PREFIX = "staff-overpayment-recovery:"
_OPEN_STATUSES = frozenset({"open", "partially_recovered"})
_RECOVERY_SELECT_SQL = (
    "SELECT r.recovery_identity,r.aggregate_version,r.status,"
    "r.remaining_amount_ntd,r.staff_id,"
    "a.aggregate_version AS staff_payables_version "
    "FROM staff_overpayment_recoveries r "
    "LEFT JOIN staff_payable_accounts a ON a.staff_id=r.staff_id "
    "WHERE r.recovery_identity=%s"
)


class MySqlAnomalyReclassificationOwnerQueryAdapter:
    """用 outer UoW 的既有 connection 驗證唯一、仍可操作的 Staff recovery。"""

    def __init__(self, connection) -> None:
        self._connection = connection

    def load_reclassification_target(
        self,
        target: AnomalyReclassificationTargetBinding,
        *,
        for_update: bool,
    ) -> AnomalyReclassificationTargetBinding | None:
        """鎖定讀取 successor；缺漏、終止或歧義一律不提供可套用 target。"""
        if target.target_domain != _STAFF_PAYABLES_DOMAIN:
            raise ValueError("anomaly_reclassification_target_unsupported")
        _validate_recovery_identity(target.target_reference)

        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(_RECOVERY_SELECT_SQL + suffix, (target.target_reference,))
            rows = cursor.fetchall()

        if len(rows) != 1:
            if len(rows) > 1:
                raise ValueError("staff_overpayment_recovery_target_ambiguous")
            return None

        row = rows[0]
        identity = str(_row_value(row, "recovery_identity"))
        version = _nonnegative_version(_row_value(row, "aggregate_version"))
        status = str(_row_value(row, "status"))
        remaining_amount = _nonnegative_amount(
            _row_value(row, "remaining_amount_ntd")
        )
        staff_payables_version = _row_value(row, "staff_payables_version")
        if staff_payables_version is None:
            return None
        _nonnegative_version(staff_payables_version)
        if (
            identity != target.target_reference
            or status not in _OPEN_STATUSES
            or remaining_amount == 0
        ):
            return None
        return AnomalyReclassificationTargetBinding(
            _STAFF_PAYABLES_DOMAIN,
            identity,
            version,
        )


# The shorter name is useful to composition roots while retaining the explicit
# MySQL adapter name for dependency wiring and test discovery.
AnomalyReclassificationOwnerQueryAdapter = (
    MySqlAnomalyReclassificationOwnerQueryAdapter
)


def _validate_recovery_identity(value: str | None) -> None:
    if not isinstance(value, str) or not value.startswith(_RECOVERY_IDENTITY_PREFIX):
        raise ValueError("staff_overpayment_recovery_target_invalid")
    if not value[len(_RECOVERY_IDENTITY_PREFIX) :]:
        raise ValueError("staff_overpayment_recovery_target_invalid")


def _row_value(row: Mapping[str, object], key: str) -> object:
    try:
        return row[key]
    except (KeyError, TypeError) as error:
        raise ValueError("staff_overpayment_recovery_target_invalid") from error


def _nonnegative_version(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("staff_overpayment_recovery_target_invalid")
    try:
        version = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("staff_overpayment_recovery_target_invalid") from error
    if version < 0:
        raise ValueError("staff_overpayment_recovery_target_invalid")
    return version


def _nonnegative_amount(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("staff_overpayment_recovery_target_invalid")
    try:
        amount = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("staff_overpayment_recovery_target_invalid") from error
    if amount < 0:
        raise ValueError("staff_overpayment_recovery_target_invalid")
    return amount


@contextmanager
def _cursor(connection) -> Iterator[object]:
    with connection.cursor() as cursor:
        yield cursor


__all__ = [
    "AnomalyReclassificationOwnerQueryAdapter",
    "MySqlAnomalyReclassificationOwnerQueryAdapter",
]
