"""Per-request construction for the Anomalies registry vertical."""

from __future__ import annotations

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import (
    AnomalyMySqlUnitOfWork,
    MySqlAnomalyRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.anomalies.alert_workflow import AnomalyApplication


def get_anomaly_application():
    connection = get_connection()
    repository = MySqlAnomalyRepository(connection)
    application = AnomalyApplication(
        default_anomaly_registry(),
        repository,
        lambda: AnomalyMySqlUnitOfWork(connection),
    )
    try:
        yield application
    finally:
        connection.close()


__all__ = ["get_anomaly_application"]
