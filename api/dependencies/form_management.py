"""Per-request construction for Form Management read-only queries."""

from __future__ import annotations

from infrastructure.mysql.form_management_query_repository import (
    MySqlFormManagementQueryRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.orders.form_management_query import FormManagementQueryService


class FormManagementQueryApplication:
    def __init__(self, service: FormManagementQueryService) -> None:
        self._service = service

    def statistics(self):
        return self._service.statistics()

    def case_context(self, case_no: str):
        return self._service.case_context(case_no)


def get_form_management_query_application():
    connection = get_connection()
    try:
        yield FormManagementQueryApplication(
            FormManagementQueryService(
                MySqlFormManagementQueryRepository(connection)
            )
        )
    finally:
        connection.close()


__all__ = [
    "FormManagementQueryApplication",
    "get_form_management_query_application",
]
