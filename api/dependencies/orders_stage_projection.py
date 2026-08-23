"""
File: orders_stage_projection.py
Description: 建立每次請求專用的 Orders 七階段唯讀 query application。
"""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.orders_stage_projection_repository import MySqlOrdersStageProjectionRepository
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.stage_projection_query import OrderStageProjectionQueryService, StageProjectionQuery


@dataclass(slots=True)
class OrdersStageProjectionApplication:
    service: OrderStageProjectionQueryService

    def query(self, request: StageProjectionQuery):
        return self.service.query(request)


def get_orders_stage_projection_application():
    connection = get_connection()
    try:
        yield OrdersStageProjectionApplication(
            OrderStageProjectionQueryService(
                MySqlOrdersStageProjectionRepository(connection),
                SystemBusinessClock(),
            )
        )
    finally:
        connection.close()


__all__ = ["OrdersStageProjectionApplication", "get_orders_stage_projection_application"]
