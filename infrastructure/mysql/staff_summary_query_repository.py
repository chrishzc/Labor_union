"""MySQL adapter for the bounded Staff summary projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from domains.staff.retirement import StaffLifecycleState

from shared_kernel.performance import MAXIMUM_PAGE_SIZE


_STAFF_SUMMARY_COLUMNS = "id, name, phone, education, union_no"


class MySqlStaffSummaryQueryRepository:
    """Read-only adapter; it never owns connection lifecycle or transactions."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_page(
        self,
        *,
        after_id: int | None,
        page_size: int,
        staff_id: int | None,
        lifecycle_state: StaffLifecycleState | None = None,
    ) -> tuple[Mapping[str, object], ...]:
        if not isinstance(page_size, int) or isinstance(page_size, bool):
            raise TypeError("page_size must be an integer")
        if not 1 <= page_size <= MAXIMUM_PAGE_SIZE:
            raise ValueError("page_size is outside the bounded query policy")
        predicate = 'id=%s' if staff_id is not None else 'id > %s'
        params: tuple[object, ...] = (staff_id if staff_id is not None else (after_id or 0),)
        if lifecycle_state is not None:
            predicate += " AND COALESCE((SELECT lifecycle_state FROM staff_lifecycle_states WHERE staff_id=staff.id),'active')=%s"
            params += (lifecycle_state.value,)
        if staff_id is not None:
            sql = f"SELECT {_STAFF_SUMMARY_COLUMNS} FROM staff WHERE {predicate} LIMIT 1"
        else:
            sql = f"SELECT {_STAFF_SUMMARY_COLUMNS} FROM staff WHERE {predicate} ORDER BY id LIMIT %s"
            params += (page_size + 1,)
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return tuple(cursor.fetchall() or ())


__all__ = ["MySqlStaffSummaryQueryRepository"]
