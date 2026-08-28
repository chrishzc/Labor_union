"""
File: anomaly_necessity_migration.py
Description: 組合異常必要性移轉的 server-owned policy 與單一 request 資源。
"""

from __future__ import annotations

from dataclasses import dataclass

from api.dependencies.anomaly_recovery import _maintenance_application
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.anomalies.maintenance_workflow import AnomalyMaintenanceApplication
from subsystems.anomalies.necessity_migration_policy import (
    ApprovedAnomalyNecessityMigrationPolicy,
    approved_anomaly_necessity_migration_policy,
)


@dataclass(frozen=True, slots=True)
class AnomalyNecessityMigrationApplication:
    workflow: AnomalyMaintenanceApplication
    policy: ApprovedAnomalyNecessityMigrationPolicy


def get_anomaly_necessity_migration_application():
    source_connection = get_connection()
    projection_connection = get_connection()
    application = AnomalyNecessityMigrationApplication(
        _maintenance_application(source_connection, projection_connection),
        approved_anomaly_necessity_migration_policy(),
    )
    try:
        yield application
    finally:
        projection_connection.close()
        source_connection.close()


__all__ = [
    "AnomalyNecessityMigrationApplication",
    "get_anomaly_necessity_migration_application",
]
