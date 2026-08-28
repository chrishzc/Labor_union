"""
File: historical_baseline_staff_payables_owner_adapter.py
Description: 以借用的 MySQL 連線讀取 Staff Payables HCAT v2 完整來源向量。
"""

from __future__ import annotations

from typing import Any

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalBaselineOwnerObservation,
    HistoricalBaselineOwnerRootDescriptor,
    HistoricalOrderIdentity,
)
from infrastructure.mysql.historical_staff_payables_completion_read_adapter import (
    _CURRENT_CASE_READ_SQL,
    _build_readback,
    _mapping_rows,
)
from shared_kernel.validation import require_canonical_text
from subsystems.orders.historical_baseline_owner_vector import (
    HistoricalBaselineOwnerObservationReadback,
)
from subsystems.orders.historical_completion_oracle import (
    CompletionOwner,
    HistoricalSettlementReadback,
    HistoricalSettlementSourceVersion,
)


_CASE_NUMBER_MAXIMUM_LENGTH = 50
_IDENTITY_MAXIMUM_LENGTH = 191
_DESCRIPTOR = next(
    item
    for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.owner_domain == "staff_payables"
)
_UNAVAILABLE_CODE = "staff_payables_step_11_staff_payout_readback_unavailable"


class MySqlHistoricalBaselineStaffPayablesOwnerAdapter:
    """Read exact Staff Payables observations without owning transaction state."""

    owner_domain = "staff_payables"

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def read_owner_observations(
        self,
        identity: HistoricalOrderIdentity,
        descriptor: HistoricalBaselineOwnerRootDescriptor,
        *,
        for_update: bool = False,
    ) -> HistoricalBaselineOwnerObservationReadback:
        self._validate_request(identity, descriptor, for_update)
        try:
            readback = self._read_case(identity.case_no, for_update=for_update)
            observations = self._observations(identity, descriptor, readback)
        except Exception:
            observations = (_unavailable(descriptor, identity.case_no),)
        return HistoricalBaselineOwnerObservationReadback(identity, observations)

    def load_completion_readback(
        self, case_no: str, *, for_update: bool = False
    ) -> HistoricalSettlementReadback | None:
        """Expose the same complete readback used by the HCAT observations."""

        if not isinstance(for_update, bool):
            raise TypeError("historical baseline Staff Payables read mode is invalid")
        return self._read_case(case_no, for_update=for_update)

    @classmethod
    def _validate_request(cls, identity, descriptor, for_update) -> None:
        if not isinstance(identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline Staff Payables identity is invalid")
        if not isinstance(descriptor, HistoricalBaselineOwnerRootDescriptor):
            raise TypeError("historical baseline Staff Payables descriptor is invalid")
        if not isinstance(for_update, bool):
            raise TypeError("historical baseline Staff Payables read mode is invalid")
        if (
            descriptor.owner_domain != cls.owner_domain
            or descriptor.canonical_tuple != _DESCRIPTOR.canonical_tuple
        ):
            raise ValueError("historical_baseline_staff_payables_descriptor_unsupported")

    def _read_case(
        self, case_no: str, *, for_update: bool
    ) -> HistoricalSettlementReadback | None:
        require_canonical_text(case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CURRENT_CASE_READ_SQL + suffix,
                (case_no, case_no, case_no, case_no, case_no),
            )
            rows = _mapping_rows(cursor.fetchall())
        return _build_readback(case_no, rows)

    @staticmethod
    def _observations(identity, descriptor, readback):
        if (
            readback is None
            or readback.owner is not CompletionOwner.STAFF_PAYABLES
            or readback.case_no != identity.case_no
            or not readback.readback_available
            or readback.integrity_blockers
            or not readback.source_versions
        ):
            return (_unavailable(descriptor, identity.case_no),)
        terminal = (
            readback.open_obligation_count == 0
            and readback.settlement_lineage_identity is not None
            and readback.allocation_lineage_identity is not None
        )
        observations = tuple(
            _available(descriptor, identity.case_no, source, terminal)
            for source in readback.source_versions
        )
        if len({item.canonical_order_key for item in observations}) != len(observations):
            return (_unavailable(descriptor, identity.case_no),)
        return observations


def _available(
    descriptor: HistoricalBaselineOwnerRootDescriptor,
    case_no: str,
    source: HistoricalSettlementSourceVersion,
    terminal: bool,
) -> HistoricalBaselineOwnerObservation:
    typed_identity = f"{source.kind.value}:{source.identity}"
    require_canonical_text(
        typed_identity,
        "historical Staff Payables source identity",
        _IDENTITY_MAXIMUM_LENGTH,
    )
    return HistoricalBaselineOwnerObservation(
        descriptor,
        typed_identity,
        typed_identity,
        source.version,
        terminal,
        None,
        case_no,
    )


def _unavailable(
    descriptor: HistoricalBaselineOwnerRootDescriptor, case_no: str
) -> HistoricalBaselineOwnerObservation:
    return HistoricalBaselineOwnerObservation.unavailable(
        descriptor,
        code=_UNAVAILABLE_CODE,
        case_no=case_no,
    )


HistoricalBaselineStaffPayablesOwnerAdapter = (
    MySqlHistoricalBaselineStaffPayablesOwnerAdapter
)
MySqlHistoricalBaselineOwnerStaffPayablesAdapter = (
    MySqlHistoricalBaselineStaffPayablesOwnerAdapter
)


__all__ = [
    "HistoricalBaselineStaffPayablesOwnerAdapter",
    "MySqlHistoricalBaselineOwnerStaffPayablesAdapter",
    "MySqlHistoricalBaselineStaffPayablesOwnerAdapter",
]
