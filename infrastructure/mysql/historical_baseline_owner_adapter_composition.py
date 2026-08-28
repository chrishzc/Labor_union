"""
File: historical_baseline_owner_adapter_composition.py
Description: 以同一借用連線組合六個 HCAT owner adapter 與 v2 查詢。
"""

from __future__ import annotations

from typing import Any

from infrastructure.mysql.historical_baseline_client_finance_owner_adapter import (
    MySqlHistoricalBaselineClientFinanceOwnerAdapter,
)
from infrastructure.mysql.historical_baseline_contract_signing_owner_adapter import (
    MySqlHistoricalBaselineContractSigningOwnerAdapter,
)
from infrastructure.mysql.historical_baseline_matching_owner_adapter import (
    MySqlHistoricalBaselineMatchingOwnerAdapter,
)
from infrastructure.mysql.historical_baseline_orders_owner_adapter import (
    MySqlHistoricalBaselineOrdersOwnerAdapter,
)
from infrastructure.mysql.historical_baseline_scheduling_owner_adapter import (
    MySqlHistoricalBaselineSchedulingOwnerAdapter,
)
from infrastructure.mysql.historical_baseline_staff_payables_owner_adapter import (
    MySqlHistoricalBaselineStaffPayablesOwnerAdapter,
)
from shared_kernel.clock import BusinessClock
from subsystems.orders.historical_baseline_owner_vector import (
    HistoricalBaselineOwnerVectorV2Query,
)


def compose_historical_baseline_owner_vector_v2_query(
    connection: Any,
    *,
    scheduling_clock: BusinessClock | None = None,
) -> HistoricalBaselineOwnerVectorV2Query:
    """Build the exact six-owner query without taking transaction ownership."""

    orders = MySqlHistoricalBaselineOrdersOwnerAdapter(connection)
    matching = MySqlHistoricalBaselineMatchingOwnerAdapter(connection)
    contract_signing = MySqlHistoricalBaselineContractSigningOwnerAdapter(connection)
    client_finance = MySqlHistoricalBaselineClientFinanceOwnerAdapter(connection)
    scheduling = (
        MySqlHistoricalBaselineSchedulingOwnerAdapter(connection)
        if scheduling_clock is None
        else MySqlHistoricalBaselineSchedulingOwnerAdapter(
            connection, clock=scheduling_clock
        )
    )
    staff_payables = MySqlHistoricalBaselineStaffPayablesOwnerAdapter(connection)
    return HistoricalBaselineOwnerVectorV2Query.from_ports(
        {
            "orders": orders,
            "matching": matching,
            "contract_signing": contract_signing,
            "client_finance": client_finance,
            "scheduling": scheduling,
            "staff_payables": staff_payables,
        }
    )


__all__ = ["compose_historical_baseline_owner_vector_v2_query"]
