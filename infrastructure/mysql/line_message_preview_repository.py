"""Read-only, bounded projections for the LINE message preview workspace."""

from __future__ import annotations

from infrastructure.mysql.effective_case_service_rate import BIRTH_COUNT_JOINS, BIRTH_COUNT_SQL

import json
from contextlib import contextmanager
from datetime import datetime, timezone

from subsystems.line.message_preview import (
    PreviewCase, PreviewLeave, PreviewOption, PreviewOptionPage, PreviewStaff, PreviewCardSource,
)


@contextmanager
def open_message_preview_reader():
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("START TRANSACTION READ ONLY")
        yield MySqlLineMessagePreviewReader(connection)
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()


class MySqlLineMessagePreviewReader:
    def __init__(self, connection):
        self._connection = connection

    def _one(self, sql, params):
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def options(self, kind, search, after):
        pattern = "%" + search.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        if kind == "case":
            sql = ("SELECT o.case_no AS id,CONCAT(o.case_no,'｜',c.name) AS label "
                   "FROM orders o JOIN clients c ON c.id=o.client_id "
                   "WHERE o.case_no>%s AND (o.case_no LIKE %s ESCAPE '!' OR c.name LIKE %s ESCAPE '!') "
                   "ORDER BY o.case_no LIMIT 21")
            params = (after or "", pattern, pattern)
        elif kind == "staff":
            sql = ("SELECT id,CONCAT(name,'（',id,'）') AS label FROM staff "
                   "WHERE id>%s AND name LIKE %s ESCAPE '!' ORDER BY id LIMIT 21")
            params = (int(after) if after else 0, pattern)
        else:
            raise ValueError("invalid subject kind")
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        items = tuple(PreviewOption(str(r["id"]), str(r["label"])) for r in rows[:20])
        return PreviewOptionPage(items, items[-1].id if len(rows) > 20 else None)

    def case(self, case_no):
        row = self._one(
            "SELECT o.case_no,c.name AS client_name,o.start_date,o.end_date,c.city,c.service_type,c.service_time,"
            + BIRTH_COUNT_SQL + " AS multi_birth_count,c.residence_type "
            "FROM orders o JOIN clients c ON c.id=o.client_id"
            + BIRTH_COUNT_JOINS + "WHERE o.case_no=%s", (case_no,))
        return PreviewCase(**{k: _text(row[k]) for k in PreviewCase.__dataclass_fields__}) if row else None

    def staff(self, staff_id):
        row = self._one(
            "SELECT id,name,city,care_babies,has_massage_cert,service_regions,special_skills FROM staff WHERE id=%s",
            (staff_id,))
        if not row:
            return None
        return PreviewStaff(int(row["id"]), _text(row["name"]), _text(row["city"]), row["care_babies"],
                            bool(row["has_massage_cert"]), _list(row["service_regions"]), _list(row["special_skills"]))

    def leave(self, case_no, staff_id):
        row = self._one(
            "SELECT DISTINCT r.id,r.aggregate_version,r.leave_start_date,r.leave_end_date "
            "FROM scheduling_staff_leave_request_aggregates r "
            "JOIN case_staff_assignments a ON a.staff_id=r.staff_id "
            "JOIN scheduling_aggregates g ON g.case_no=a.case_no AND g.effective_generation_id=a.generation_id "
            "JOIN staff_schedule ss ON ss.assignment_id=a.id AND ss.staff_id=a.staff_id "
            "WHERE a.case_no=%s AND a.status NOT IN ('cancelled','replaced') AND ss.is_work_day=1 "
            "AND ss.work_date BETWEEN r.leave_start_date AND r.leave_end_date "
            "AND (%s IS NULL OR r.staff_id=%s) ORDER BY r.id DESC LIMIT 1", (case_no, staff_id, staff_id))
        return PreviewLeave(int(row["id"]), int(row["aggregate_version"]),
                            _text(row["leave_start_date"]), _text(row["leave_end_date"])) if row else None

    def service_date(self, case_no, staff_id):
        row = self._one(
            "SELECT MAX(ss.work_date) AS service_date FROM staff_schedule ss "
            "JOIN case_staff_assignments a ON a.id=ss.assignment_id AND a.staff_id=ss.staff_id "
            "JOIN scheduling_aggregates g ON g.case_no=a.case_no AND g.effective_generation_id=a.generation_id "
            "WHERE a.case_no=%s AND ss.staff_id=%s AND ss.is_work_day=1 "
            "AND a.status NOT IN ('cancelled','replaced')", (case_no, staff_id))
        return _text(row["service_date"]) if row and row["service_date"] else None

    def payment_values(self, case_no):
        # 繳款提醒改走客戶私訊排程；預覽不再從群組來源掃描帶入金額。
        return {}

    def card(self, case_no, staff_id, kind):
        from infrastructure.mysql.matching_notification_repository import MySqlMatchingNotificationRepository
        from infrastructure.mysql.order_information_repository import MySqlOrderInformationRepository
        from subsystems.scheduling.matching_line_cards import candidate_contact_information_card, customer_confirmation_card

        repository = MySqlMatchingNotificationRepository(self._connection)
        if kind == "card-customer-confirmation":
            from dataclasses import asdict
            from subsystems.line.table_image_contracts import information_document, weekly_document
            plan = self._one(
                "SELECT p.id FROM caregiver_matching_plans p JOIN caregiver_matching_plan_segments s ON s.plan_id=p.id "
                "WHERE p.case_no=%s AND p.is_active=1 AND s.staff_id=%s ORDER BY p.id DESC LIMIT 1", (case_no, staff_id))
            if not plan:
                return None
            projection = repository.customer_confirmation_preview(case_no, int(plan["id"]))
            if projection["blockers"]:
                return None
            profiles = repository.customer_profile_facts(int(plan["id"]))
            # Only show the download action when an actual current resume exists; never issue a download token.
            resumes = {int(item["staff_id"]): "https://preview.invalid/resume" for item in projection["caregiver_resumes"]}
            documents = (information_document('訂單資訊－1｜客戶費用', case_no, projection['order_information_1'], info_type=1),
                information_document('訂單資訊－2', case_no, projection['order_information_2'], info_type=2),
                weekly_document(case_no, projection['weekly_service_rows']))
            return PreviewCardSource(customer_confirmation_card(case_no, profiles, projection["order_information_1"],
                projection["order_information_2"], projection["weekly_service_rows"], resumes, "preview-only", ""),
                json.dumps([asdict(item) for item in documents], ensure_ascii=False))

        entry = self._one(
            "SELECT e.id FROM caregiver_candidate_contact_entries e JOIN caregiver_candidate_contact_pools p ON p.id=e.pool_id "
            "WHERE p.case_no=%s AND e.staff_id=%s AND e.active_marker=1 ORDER BY e.id DESC LIMIT 1", (case_no, staff_id))
        if not entry:
            return None
        numbers = (1, 2, 3) if kind == "card-candidate-information-package" else (int(kind.rsplit("-", 1)[1]),)
        try:
            order_information = MySqlOrderInformationRepository(self._connection)
            previews = tuple(order_information.preview_candidate_information(case_no, int(entry["id"]), value) for value in numbers)
        except (LookupError, ValueError):
            return None
        from dataclasses import asdict
        from subsystems.line.table_image_contracts import candidate_information_document
        documents = tuple(candidate_information_document(
            case_no, item.info_type, tuple((section.title, section.rows) for section in item.line_sections),
        ) for item in previews)
        preview = previews[0]
        info_type = preview.info_type
        return PreviewCardSource(candidate_contact_information_card(case_no, info_type,
            tuple((section.title, section.rows) for section in preview.line_sections), "preview-only"), json.dumps([asdict(document) for document in documents], ensure_ascii=False))


def _text(value):
    return "" if value is None else str(value)


def _list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return (value,) if value else ()
    return tuple(str(v) for v in value) if isinstance(value, (list, tuple)) else ()
