"""MySQL adapter for the bounded Staff personal profile projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from domains.staff.retirement import StaffLifecycleState

from shared_kernel.performance import MAXIMUM_PAGE_SIZE
from infrastructure.mysql.staff_qualification_master_repository import MySqlStaffQualificationMasterRepository
from subsystems.staff.qualification_master_query import StaffRosterServiceProfile
from subsystems.staff.profile_query import StaffSavedDocument, StaffSavedDocumentPage, StaffSavedDocumentSourceUnavailable, StaffSavedDocumentCursorInvalid
from subsystems.controlled_files.workflow import ControlledFilePurpose
from pymysql import MySQLError


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

    def fetch_saved_documents(self, staff_id, *, after=None, page_size=MAXIMUM_PAGE_SIZE, file_id=None):
        """Read current immutable revisions for each Staff-owned logical file."""
        if type(page_size) is not int or not 1 <= page_size <= MAXIMUM_PAGE_SIZE or after is not None and file_id is not None:
            raise StaffSavedDocumentCursorInvalid("Staff document page is invalid")
        try:
            with self._connection.cursor() as cursor:
                after_id = 0
                if after is not None:
                    cursor.execute("SELECT id FROM controlled_file_objects WHERE opaque_object_id=%s "
                        "AND owner_type='staff' AND subject_reference=%s AND purpose IN ('staff_certificate','staff_health_exam')",
                        (after, str(staff_id)))
                    position = cursor.fetchone()
                    if position is None:
                        raise StaffSavedDocumentCursorInvalid("Staff document cursor does not belong to this owner")
                    after_id = position["id"]
                predicate = " AND object.opaque_object_id=%s" if file_id is not None else " AND object.id>%s"
                cursor.execute(_SAVED_DOCUMENTS_SQL + predicate + " ORDER BY object.id LIMIT %s",
                    (staff_id, file_id if file_id is not None else after_id, 2 if file_id is not None else page_size + 1))
                rows = tuple(cursor.fetchall())
            return _saved_document_page(rows, staff_id, page_size, exact=file_id is not None)
        except MySQLError as error:
            raise StaffSavedDocumentSourceUnavailable("Staff saved file source is unavailable") from error

    def fetch_bank_accounts(self, staff_id: int) -> tuple[Mapping[str, object], ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,bank_code,branch_code,account_no,RIGHT(account_no,4) AS account_last4,is_primary,is_active "
                "FROM staff_bank_accounts WHERE staff_id=%s "
                "ORDER BY is_active DESC,is_primary DESC,id ASC LIMIT 21",
                (staff_id,),
            )
            return tuple(cursor.fetchall())

    def fetch_page(self, *, after_id: int | None, page_size: int, staff_id: int | None, lifecycle_state: StaffLifecycleState | None = None) -> tuple[Mapping[str, object], ...]:
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= MAXIMUM_PAGE_SIZE:
            raise ValueError("staff roster page_size is outside bounded policy")
        predicate = "id=%s" if staff_id is not None else "id > %s"
        parameters: list[object] = [staff_id if staff_id is not None else (after_id or 0)]
        if lifecycle_state is not None:
            predicate += " AND COALESCE((SELECT lifecycle_state FROM staff_lifecycle_states WHERE staff_id=staff.id),'active')=%s"
            parameters.append(lifecycle_state.value)
        parameters.append(1 if staff_id is not None else page_size + 1)
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_PROFILE_COLUMNS},CAST(COALESCE((SELECT aggregate_version FROM staff_bank_account_states "
                "WHERE staff_id=staff.id),0) AS UNSIGNED) AS bank_accounts_version "
                f"FROM staff WHERE {predicate} ORDER BY id LIMIT %s",
                tuple(parameters),
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


def _saved_document_page(rows, staff_id, page_size, *, exact=False):
    if len(rows) > (1 if exact else page_size + 1):
        raise StaffSavedDocumentSourceUnavailable("Staff document page exceeds its bounded source")
    items = tuple(_saved_document(row, staff_id) for row in rows)
    selected = items[:page_size]
    return StaffSavedDocumentPage("available", selected, selected[-1].file_id if len(items) > page_size else None)


def _saved_document(row, staff_id):
    if row["owner_type"] != "staff" or row["subject_reference"] != str(staff_id):
        raise ValueError("Staff saved file owner mismatch")
    return StaffSavedDocument(staff_id, str(row["opaque_object_id"]), ControlledFilePurpose(row["purpose"]),
        str(row["filename"]), row["version_number"], str(row["content_sha256"]), str(row["content_type"]), row["size_bytes"])


_SAVED_DOCUMENTS_SQL = (
    "SELECT object.opaque_object_id,object.owner_type,object.purpose,object.subject_reference,object.filename,"
    "object.version_number,object.content_sha256,object.content_type,object.size_bytes "
    "FROM staff JOIN controlled_file_objects object ON object.subject_reference=CAST(staff.id AS CHAR) "
    "JOIN controlled_file_apply_receipts receipt ON receipt.controlled_object_id=object.id "
    "WHERE staff.id=%s AND object.owner_type='staff' AND object.purpose IN ('staff_certificate','staff_health_exam') "
    "AND NOT EXISTS (SELECT 1 FROM controlled_file_objects newer WHERE newer.owner_type=object.owner_type "
    "AND newer.subject_reference=object.subject_reference AND newer.purpose=object.purpose "
    "AND newer.object_key=object.object_key AND newer.version_number>object.version_number)"
)


__all__ = ["MySqlStaffProfileQueryRepository"]
