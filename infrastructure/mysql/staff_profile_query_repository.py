"""MySQL adapter for the bounded Staff personal profile projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shared_kernel.performance import MAXIMUM_PAGE_SIZE
from infrastructure.mysql.staff_qualification_master_repository import MySqlStaffQualificationMasterRepository
from subsystems.staff.qualification_master_query import StaffRosterServiceProfile


_PROFILE_COLUMNS = (
    "id,name,union_no,staff_profile_version,registered_at,identity_card,phone,tel,tel_ext,email,birthday,city,zip_code,"
    "address,education,emergency_contact_name,emergency_contact_phone,admin_notes"
)


class MySqlStaffProfileQueryRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_service_profiles(self, staff_ids: tuple[int, ...]) -> Mapping[int, StaffRosterServiceProfile]:
        return MySqlStaffQualificationMasterRepository(self._connection).fetch_service_profiles(staff_ids)

    def fetch(self, staff_id: int) -> Mapping[str, object] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_PROFILE_COLUMNS},CAST(COALESCE((SELECT aggregate_version FROM staff_bank_account_states "
                "WHERE staff_id=staff.id),0) AS UNSIGNED) AS bank_accounts_version "
                "FROM staff WHERE id=%s LIMIT 1",
                (staff_id,),
            )
            return cursor.fetchone()

    def fetch_bank_accounts(self, staff_id: int) -> tuple[Mapping[str, object], ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,bank_code,branch_code,account_no,RIGHT(account_no,4) AS account_last4,is_primary,is_active "
                "FROM staff_bank_accounts WHERE staff_id=%s "
                "ORDER BY is_active DESC,is_primary DESC,id ASC LIMIT 21",
                (staff_id,),
            )
            return tuple(cursor.fetchall())

    def fetch_page(self, *, after_id: int | None, page_size: int, staff_id: int | None) -> tuple[Mapping[str, object], ...]:
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= MAXIMUM_PAGE_SIZE:
            raise ValueError("staff roster page_size is outside bounded policy")
        predicate = "id=%s" if staff_id is not None else "id > %s"
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_PROFILE_COLUMNS},CAST(COALESCE((SELECT aggregate_version FROM staff_bank_account_states "
                "WHERE staff_id=staff.id),0) AS UNSIGNED) AS bank_accounts_version "
                f"FROM staff WHERE {predicate} ORDER BY id LIMIT %s",
                (staff_id if staff_id is not None else (after_id or 0), 1 if staff_id is not None else page_size + 1),
            )
            return tuple(cursor.fetchall())

    def fetch_bank_accounts_for_staff(self, staff_ids: tuple[int, ...]) -> Mapping[int, tuple[Mapping[str, object], ...]]:
        if not staff_ids:
            return {}
        if len(staff_ids) > MAXIMUM_PAGE_SIZE:
            raise ValueError("staff roster account batch exceeds bounded maximum")
        placeholders = ",".join(["%s"] * len(staff_ids))
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT staff_id,id,bank_code,branch_code,account_no,RIGHT(account_no,4) AS account_last4,is_primary,is_active "
                "FROM (SELECT staff_id,id,bank_code,branch_code,account_no,is_primary,is_active,"
                "ROW_NUMBER() OVER (PARTITION BY staff_id ORDER BY is_active DESC,is_primary DESC,id) AS account_position "
                f"FROM staff_bank_accounts WHERE staff_id IN ({placeholders})) AS bounded_accounts "
                "WHERE account_position <= 21 ORDER BY staff_id,account_position", staff_ids,
            )
            rows = cursor.fetchall()
        grouped: dict[int, list[Mapping[str, object]]] = {identity: [] for identity in staff_ids}
        for row in rows:
            values = dict(row)
            identity = int(values.pop("staff_id"))
            grouped[identity].append(values)
        return {identity: tuple(items) for identity, items in grouped.items()}


__all__ = ["MySqlStaffProfileQueryRepository"]
