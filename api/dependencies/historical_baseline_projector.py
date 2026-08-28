"""Per-request read-only composition for historical-baseline projector state."""

from __future__ import annotations

from infrastructure.mysql.historical_baseline_projector_read_model import (
    HistoricalBaselineProjectorReadModel,
    HistoricalBaselineProjectorReadPort,
    HistoricalBaselineReconcileByIdentityResult,
    historical_baseline_reconcile_by_identity_disposition,
)
from infrastructure.mysql.historical_baseline_projector_repository import (
    MySqlHistoricalBaselineProjectorRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection


class HistoricalBaselineProjectorQueryApplication:
    def __init__(self, read_port: HistoricalBaselineProjectorReadPort) -> None:
        self._read_port = read_port

    def query_by_delivery_identity(
        self, delivery_identity: str
    ) -> tuple[
        HistoricalBaselineProjectorReadModel,
        HistoricalBaselineReconcileByIdentityResult,
    ] | None:
        model = self._read_port.query_by_delivery_identity(delivery_identity)
        return self._with_reconciliation(model)

    def query_latest_by_case(
        self, case_no: str
    ) -> tuple[
        HistoricalBaselineProjectorReadModel,
        HistoricalBaselineReconcileByIdentityResult,
    ] | None:
        model = self._read_port.query_latest_by_case(case_no)
        return self._with_reconciliation(model)

    @staticmethod
    def _with_reconciliation(model):
        if model is None:
            return None
        return model, historical_baseline_reconcile_by_identity_disposition(model)


def get_historical_baseline_projector_query_application():
    connection = get_connection()
    try:
        yield HistoricalBaselineProjectorQueryApplication(
            MySqlHistoricalBaselineProjectorRepository(connection)
        )
    finally:
        connection.close()


__all__ = [
    "HistoricalBaselineProjectorQueryApplication",
    "get_historical_baseline_projector_query_application",
]
