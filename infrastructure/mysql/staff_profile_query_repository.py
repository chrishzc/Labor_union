"""MySQL adapter for the bounded Staff personal profile projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_PROFILE_COLUMNS = (
    "id,registered_at,identity_card,phone,tel,tel_ext,email,birthday,city,zip_code,"
    "address,education,emergency_contact_name,emergency_contact_phone,admin_notes"
)


class MySqlStaffProfileQueryRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch(self, staff_id: int) -> Mapping[str, object] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_PROFILE_COLUMNS} FROM staff WHERE id=%s LIMIT 1",
                (staff_id,),
            )
            return cursor.fetchone()

    def fetch_bank_accounts(self, staff_id: int) -> tuple[Mapping[str, object], ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,bank_code,branch_code,account_no,is_primary "
                "FROM staff_bank_accounts WHERE staff_id=%s "
                "ORDER BY is_primary DESC,id ASC LIMIT 21",
                (staff_id,),
            )
            return tuple(cursor.fetchall())


__all__ = ["MySqlStaffProfileQueryRepository"]
