"""
File: orders_stage_projection.py
Description: 建立每次請求專用的 Orders 七階段唯讀 query application。
"""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.historical_orders_stage_projection_repository import (
    MySqlHistoricalAwareOrdersStageProjectionRepository,
)
from infrastructure.mysql.historical_stage_baseline_repository import (
    MySqlHistoricalStageBaselineRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.historical_stage_baseline_overlay import (
    HistoricalStageBaselineOverlayService,
    OperationalTimelineQueryPort,
)
from subsystems.orders.stage_projection_query import OrderStageProjectionQueryService, StageProjectionQuery


@dataclass(slots=True)
class OrdersStageProjectionApplication:
    service: OperationalTimelineQueryPort

    def query(self, request: StageProjectionQuery):
        return self.service.query(request)


def get_orders_stage_projection_application():
    connection = get_connection()
    try:
        base = OrderStageProjectionQueryService(
            MySqlHistoricalAwareOrdersStageProjectionRepository(connection),
            SystemBusinessClock(),
        )
        yield OrdersStageProjectionApplication(
            HistoricalStageBaselineOverlayService(
                base,
                MySqlHistoricalStageBaselineRepository(connection),
            )
        )
    finally:
        connection.close()


__all__ = ["OrdersStageProjectionApplication", "get_orders_stage_projection_application"]
