"""Per-request composition for the case-centered client registry."""

from __future__ import annotations

from infrastructure.mysql.beclass_correction_repository import MySqlBeClassCorrectionRepository
from infrastructure.mysql.client_registry_query_repository import MySqlClientRegistryQueryRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.case_import.beclass_correction_workflow import BeClassCorrectionWorkflow
from subsystems.client_profile.registry_query import ClientRegistryQueryApplication


def get_client_registry_query_application():
    connection = get_connection()
    try:
        yield ClientRegistryQueryApplication(MySqlClientRegistryQueryRepository(connection))
    finally:
        connection.close()


def get_beclass_correction_workflow():
    connection = get_connection()
    try:
        yield BeClassCorrectionWorkflow(
            MySqlBeClassCorrectionRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


__all__ = ["get_beclass_correction_workflow", "get_client_registry_query_application"]
