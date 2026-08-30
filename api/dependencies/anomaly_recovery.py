"""Per-request composition for current-only Anomalies recovery reads."""

from infrastructure.mysql.current_anomaly_issue_repository import (
    MySqlCurrentIssueRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection


def get_current_anomaly_issue_repository():
    connection = get_connection()
    repository = MySqlCurrentIssueRepository(connection)
    try:
        yield repository
    finally:
        connection.close()


__all__ = ["get_current_anomaly_issue_repository"]
