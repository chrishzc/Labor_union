"""Per-request construction for the Anomalies registry vertical."""

from __future__ import annotations

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.anomaly_runtime import build_anomaly_runtime
from infrastructure.mysql.current_anomaly_issue_repository import (
    MySqlCurrentIssueRepository,
)
from subsystems.anomalies.current_issue_query import (
    CurrentIssueCursorCodec,
    CurrentIssueQueryApplication,
)


def get_anomaly_application():
    connection = get_connection()
    application = build_anomaly_runtime().anomaly_application(connection)
    try:
        yield application
    finally:
        connection.close()


def get_current_issue_query_application():
    connection = get_connection()
    application = CurrentIssueQueryApplication(
        MySqlCurrentIssueRepository(connection),
        CurrentIssueCursorCodec(),
    )
    try:
        yield application
    finally:
        connection.close()


__all__ = ["get_anomaly_application", "get_current_issue_query_application"]
