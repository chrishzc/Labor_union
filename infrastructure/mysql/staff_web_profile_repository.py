from datetime import date
import json
from uuid import UUID

from domains.staff.web_profile import (
    PublishedWebProfilePhoto,
    ReminderLead,
    WebProfileCategory,
    WebProfileConflict,
    WebProfileEntryVersion,
    WebProfilePhoto,
    WebProfileTemplateItem,
)


_TEMPLATE_COLS = """t.id AS template_item_id, t.version AS template_version, t.name,
    t.category, t.display_order, t.reminder_enabled, t.reminder_months, t.reminder_days"""

_PUBLISHED = f"""SELECT {_TEMPLATE_COLS}, e.id AS entry_id, e.staff_id, e.removed_at,
    p.version, p.original_file_id, p.crop_file_id, p.expiry_date
FROM staff_web_entries e
JOIN staff_web_publications p ON p.entry_id=e.id AND p.version=e.published_version
JOIN staff_web_template_items t ON t.id=e.template_item_id"""

_CURRENT = """e.removed_at IS NULL AND (t.category <> 'other' OR NOT EXISTS (
    SELECT 1 FROM staff_web_entries newer
    WHERE newer.staff_id=e.staff_id AND newer.template_item_id=e.template_item_id AND newer.id > e.id
        AND (newer.removed_at IS NULL OR newer.removed_as_other=TRUE)
))"""


class MySqlStaffWebProfileRepository:
    def __init__(self, connection):
        self._connection = connection

    def templates(self) -> tuple[WebProfileTemplateItem, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(f"SELECT {_TEMPLATE_COLS} FROM staff_web_template_items t ORDER BY t.category,t.display_order,t.id")
            return tuple(_template(row) for row in cursor.fetchall())

    def template(self, item_id: int, *, lock: bool = False) -> WebProfileTemplateItem | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_TEMPLATE_COLS} FROM staff_web_template_items t WHERE t.id=%s"
                + (" FOR UPDATE" if lock else ""),
                (item_id,),
            )
            row = cursor.fetchone()
        return _template(row) if row else None

    def save_template(self, item: WebProfileTemplateItem, actor: str) -> WebProfileTemplateItem:
        values = (
            item.name, item.category.value, item.display_order, item.reminder_enabled,
            item.reminder_lead.months, item.reminder_lead.days, actor,
        )
        with self._connection.cursor() as cursor:
            if item.item_id is None:
                cursor.execute(
                    """INSERT INTO staff_web_template_items
                    (name,category,display_order,reminder_enabled,reminder_months,reminder_days,updated_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    values,
                )
                item_id = int(cursor.lastrowid)
            else:
                item_id = item.item_id
                cursor.execute(
                    """UPDATE staff_web_template_items SET name=%s,category=%s,display_order=%s,
                       reminder_enabled=%s,reminder_months=%s,reminder_days=%s,updated_by=%s,version=version+1
                    WHERE id=%s AND version=%s""",
                    (*values, item_id, item.version),
                )
                if cursor.rowcount != 1:
                    raise WebProfileConflict("staff_web_template_stale")
        saved = self.template(item_id)
        if saved is None:
            raise RuntimeError("staff_web_template_readback_missing")
        return saved

    def staff_name(self, staff_id: int, *, lock: bool = False) -> str | None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT name FROM staff WHERE id=%s" + (" FOR UPDATE" if lock else ""), (staff_id,))
            row = cursor.fetchone()
        return str(row["name"]) if row else None

    def current(self, staff_id: int) -> tuple[PublishedWebProfilePhoto, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _PUBLISHED + f" WHERE e.staff_id=%s AND {_CURRENT} ORDER BY t.category,t.display_order,t.id,e.id",
                (staff_id,),
            )
            return tuple(_published(row) for row in cursor.fetchall())

    def entry(self, staff_id: int, entry_id: int, *, lock: bool = False) -> PublishedWebProfilePhoto | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _PUBLISHED + f" WHERE e.staff_id=%s AND e.id=%s AND {_CURRENT}" + (" FOR UPDATE" if lock else ""),
                (staff_id, entry_id),
            )
            row = cursor.fetchone()
        return _published(row) if row else None

    def other_current(self, staff_id: int, item_id: int, *, lock: bool) -> PublishedWebProfilePhoto | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _PUBLISHED + """ WHERE e.staff_id=%s AND e.template_item_id=%s
                AND (e.removed_at IS NULL OR e.removed_as_other=TRUE)
                ORDER BY e.id DESC LIMIT 1"""
                + (" FOR UPDATE" if lock else ""),
                (staff_id, item_id),
            )
            row = cursor.fetchone()
        return _published(row) if row and row["removed_at"] is None else None

    def has_multiple_active_entries(self, item_id: int) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT staff_id FROM staff_web_entries WHERE template_item_id=%s AND removed_at IS NULL
                ORDER BY staff_id, id FOR UPDATE""",
                (item_id,),
            )
            staff_ids: set[int] = set()
            for row in cursor.fetchall():
                staff_id = int(row["staff_id"])
                if staff_id in staff_ids:
                    return True
                staff_ids.add(staff_id)
        return False

    def removed(self, staff_id: int, item_id: int, expected: WebProfileEntryVersion) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT 1 FROM staff_web_entries WHERE staff_id=%s AND template_item_id=%s
                AND id=%s AND published_version=%s AND removed_at IS NOT NULL FOR UPDATE""",
                (staff_id, item_id, expected.entry_id, expected.entry_version),
            )
            return cursor.fetchone() is not None

    def remove(self, staff_id: int, item_id: int, expected: WebProfileEntryVersion, actor: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """UPDATE staff_web_entries e JOIN staff_web_template_items t ON t.id=e.template_item_id
                SET e.removed_at=UTC_TIMESTAMP(6), e.removed_by=%s, e.removed_as_other=(t.category='other')
                WHERE e.staff_id=%s AND e.template_item_id=%s AND e.id=%s
                AND e.published_version=%s AND e.removed_at IS NULL""",
                (actor, staff_id, item_id, expected.entry_id, expected.entry_version),
            )
            if cursor.rowcount != 1:
                raise WebProfileConflict("staff_web_publication_stale")

    def original_used(self, file_id: str, *, lock: bool) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT entry_id FROM staff_web_publications WHERE original_file_id=%s" + (" FOR UPDATE" if lock else ""),
                (file_id,),
            )
            return cursor.fetchone() is not None

    def publish(self, staff_id: int, photo: WebProfilePhoto, actor: str) -> PublishedWebProfilePhoto:
        with self._connection.cursor() as cursor:
            entry_id = photo.entry_id
            version = (photo.entry_version or 0) + 1
            if entry_id is None:
                cursor.execute(
                    "INSERT INTO staff_web_entries (staff_id,template_item_id,published_version) VALUES (%s,%s,%s)",
                    (staff_id, photo.template_item_id, version),
                )
                entry_id = int(cursor.lastrowid)
            else:
                cursor.execute(
                    """UPDATE staff_web_entries SET published_version=%s
                    WHERE id=%s AND staff_id=%s AND template_item_id=%s AND published_version=%s
                    AND removed_at IS NULL""",
                    (version, entry_id, staff_id, photo.template_item_id, photo.entry_version),
                )
                if cursor.rowcount != 1:
                    raise WebProfileConflict("staff_web_publication_stale")
            cursor.execute(
                """INSERT INTO staff_web_publications
                    (entry_id,version,original_file_id,crop_file_id,expiry_date,approved_by)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (entry_id, version, photo.original_file_id, photo.crop_file_id, photo.expiry_date, actor),
            )
        saved = self.entry(staff_id, entry_id, lock=True)
        if saved is None or saved.version != version:
            raise RuntimeError("staff_web_publication_readback_missing")
        return saved

    def approval(
        self, operation_id: UUID, staff_id: int, *, lock: bool = False, command: dict | None = None,
    ) -> tuple[dict, ...] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT staff_id,publication_results FROM staff_web_approval_receipts WHERE operation_id=%s"
                + (" FOR UPDATE" if lock else ""),
                (str(operation_id),),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        if int(row["staff_id"]) != staff_id:
            raise WebProfileConflict("staff_web_approval_owner_mismatch")
        payload = json.loads(row["publication_results"])
        if isinstance(payload, list):
            saved_command, results = None, payload
        else:
            saved_command, results = payload["command"], payload["results"]
        if (lock or command is not None) and saved_command != command:
            raise WebProfileConflict("staff_web_operation_mismatch")
        return tuple(results)

    def record_approval(
        self, operation_id: UUID, staff_id: int, results: tuple[dict, ...], *, command: dict | None = None,
    ) -> None:
        payload = results if command is None else {"command": command, "results": results}
        with self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO staff_web_approval_receipts
                (operation_id,staff_id,publication_results) VALUES (%s,%s,%s)""",
                (str(operation_id), staff_id, json.dumps(payload)),
            )

    def reminder_candidates(self, today: date, after: int, limit: int) -> tuple[PublishedWebProfilePhoto, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _PUBLISHED + f""" WHERE {_CURRENT} AND t.category='other' AND t.reminder_enabled=1
                AND p.expiry_date >= %s AND e.id > %s ORDER BY e.id LIMIT %s""",
                (today, after, limit),
            )
            return tuple(_published(row) for row in cursor.fetchall())


def _template(row) -> WebProfileTemplateItem:
    return WebProfileTemplateItem(
        int(row["template_item_id"]), int(row["template_version"]), str(row["name"]),
        WebProfileCategory(row["category"]), int(row["display_order"]), bool(row["reminder_enabled"]),
        ReminderLead(int(row["reminder_months"]), int(row["reminder_days"])),
    )


def _published(row) -> PublishedWebProfilePhoto:
    return PublishedWebProfilePhoto(
        int(row["entry_id"]), int(row["version"]), int(row["staff_id"]), _template(row),
        str(row["original_file_id"]), row["crop_file_id"], row["expiry_date"],
    )
