"""Per-request construction for Anomalies root-fact recovery."""

from __future__ import annotations

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.anomaly_maintenance_repository import (
    AnomalyReclassificationMySqlUnitOfWork,
    MySqlAnomalyMaintenanceRepository,
)
from infrastructure.mysql.anomaly_reclassification_owner_query_adapter import (
    MySqlAnomalyReclassificationOwnerQueryAdapter,
)
from infrastructure.mysql.anomaly_root_fact_projection_repository import (
    MySqlRootFactProjectionRepository,
    RootFactProjectionMySqlUnitOfWork,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.anomalies.maintenance_workflow import (
    AnomalyMaintenanceApplication,
)
from subsystems.anomalies.root_fact_projection_workflow import (
    RootFactProjectionApplication,
)


def get_anomaly_recovery_application():
    connection = get_connection()
    repository = MySqlRootFactProjectionRepository(connection)
    application = RootFactProjectionApplication(
        default_anomaly_registry(),
        repository,
        lambda: RootFactProjectionMySqlUnitOfWork(connection),
    )
    try:
        yield application
    finally:
        connection.close()


def get_anomaly_maintenance_application():
    source_connection = get_connection()
    projection_connection = get_connection()
    application = _maintenance_application(
        source_connection,
        projection_connection,
    )
    try:
        yield application
    finally:
        projection_connection.close()
        source_connection.close()


def _maintenance_application(source_connection, projection_connection):
    repository = MySqlAnomalyMaintenanceRepository(source_connection)
    projector = RootFactProjectionApplication(
        default_anomaly_registry(),
        MySqlRootFactProjectionRepository(projection_connection),
        lambda: RootFactProjectionMySqlUnitOfWork(projection_connection),
    )
    return AnomalyMaintenanceApplication(
        default_anomaly_registry(),
        repository,
        repository,
        projector,
        lambda: AnomalyReclassificationMySqlUnitOfWork(source_connection),
        reclassification_port=repository,
        target_verifier=MySqlAnomalyReclassificationOwnerQueryAdapter(
            source_connection
        ),
    )


__all__ = [
    "get_anomaly_maintenance_application",
    "get_anomaly_recovery_application",
]
