"""MySQL adapter for the bounded Orders lifecycle control query."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from subsystems.orders.lifecycle_control_read_facts import (
    OrderLifecycleControlReadFacts,
    load_order_lifecycle_control_read_facts,
)


class MySqlOrderLifecycleControlQueryRepository:
    """Read lifecycle control facts using the request-owned connection."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_by_case_no(
        self, case_no: str, as_of: datetime
    ) -> OrderLifecycleControlReadFacts:
        with self._connection.cursor() as cursor:
            return load_order_lifecycle_control_read_facts(
                cursor=cursor, case_no=case_no, as_of=as_of
            )


__all__ = ["MySqlOrderLifecycleControlQueryRepository"]
