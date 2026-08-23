"""
File: operations_reports.py
Description: 建立每次請求專用的營運週報唯讀 Query 並關閉 MySQL 連線。
"""

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.weekly_operations_report_query_adapter import (
    MySqlWeeklyOperationsReportQueryAdapter,
)
from shared_kernel.clock import SystemBusinessClock
from subsystems.reporting.weekly_operations_report_query import WeeklyOperationsReportQuery


def get_weekly_operations_report_query():
    connection = get_connection()
    try:
        yield WeeklyOperationsReportQuery(
            MySqlWeeklyOperationsReportQueryAdapter(connection),
            SystemBusinessClock().now,
        )
    finally:
        connection.close()


__all__ = ["get_weekly_operations_report_query"]
