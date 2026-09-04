"""Request-scoped MySQL dependency for the Order -> Government Subsidy read projection."""

from __future__ import annotations

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.order_government_subsidy_projection_repository import (
    MySqlOrderGovernmentSubsidyProjectionRepository,
)


def get_order_government_subsidy_projection_repository():
    connection = get_connection()
    try:
        yield MySqlOrderGovernmentSubsidyProjectionRepository(connection)
    finally:
        connection.close()


__all__ = ["get_order_government_subsidy_projection_repository"]
