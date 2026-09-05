"""Build the read-only Historical Orders adoption-evidence query repository."""

from infrastructure.mysql.historical_order_adoption_evidence_repository import (
    MySqlHistoricalOrderAdoptionEvidenceRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection


def get_historical_order_adoption_evidence_repository():
    connection = get_connection()
    try:
        yield MySqlHistoricalOrderAdoptionEvidenceRepository(connection)
    finally:
        connection.close()


__all__ = ["get_historical_order_adoption_evidence_repository"]
