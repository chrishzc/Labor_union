"""
File: contract_context_repository.py
Description: 以正式 Client BeClass 綁定與指派根事實讀取契約內容。
"""

from datetime import time, timedelta


class MySqlContractContextRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load_case_facts(self, case_no: str):
        with self._connection.cursor() as cursor:
            cursor.execute(_CASE_FACTS_SQL, (case_no,))
            row = cursor.fetchone()
        if row is not None:
            row["service_time"] = _service_time(row)
        return row

    def load_assignments(self, case_no: str):
        with self._connection.cursor() as cursor:
            cursor.execute(_ASSIGNMENTS_SQL, (case_no,))
            return tuple(cursor.fetchall() or ())


_CASE_FACTS_SQL = """SELECT o.case_no,o.status,o.contract_identity,o.service_days,
o.service_hours_per_day,o.service_start_time,o.service_end_time,o.service_end_day_offset,
o.floor_fee,o.start_date,o.end_date,o.actual_start_date,
o.actual_end_date,c.id AS client_id,c.name AS client_name,c.phone AS client_phone,
c.city AS client_city,c.address AS client_address,c.identity_status AS client_identity_status,
c.service_type,c.service_time,c.due_month,c.baby_info,c.delivery_type,c.residence_type,
c.notes AS client_notes,o.custom_rest_dates,
b.query_no AS beclass_query_no,b.survey_details,b.admin_notes AS beclass_admin_notes
FROM orders o JOIN clients c ON c.case_no=o.case_no
LEFT JOIN beclass_records b ON b.bound_case_no=o.case_no WHERE o.case_no=%s"""

_ASSIGNMENTS_SQL = """SELECT a.id AS assignment_id,a.case_no,a.staff_id,
a.assignment_sequence,a.assigned_start_date,a.assigned_end_date,a.planned_hours,
a.actual_hours,a.hourly_rate,a.floor_fee_allocated,a.status,a.replacement_reason,
s.name AS staff_name,s.identity_card AS staff_identity_card,s.phone AS staff_phone,
s.email AS staff_email,s.city AS staff_city,s.address AS staff_address,
s.weekly_rest_days,s.service_regions FROM case_staff_assignments a
JOIN staff s ON s.id=a.staff_id WHERE a.case_no=%s AND a.status<>'cancelled'
ORDER BY a.assignment_sequence,a.id"""


def _service_time(row):
    start, end = row.get("service_start_time"), row.get("service_end_time")
    offset = row.get("service_end_day_offset")
    if start is None or end is None or offset is None:
        return None

    def clock_text(value):
        if isinstance(value, timedelta):
            seconds = int(value.total_seconds())
            if not 0 <= seconds < 86400:
                return None
            return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"
        if isinstance(value, time):
            return value.strftime("%H:%M")
        return None

    start_text, end_text = clock_text(start), clock_text(end)
    if start_text is None or end_text is None:
        return None
    suffix = "（翌日）" if offset == 1 else ""
    return f"{start_text}–{end_text}{suffix}"


__all__ = ["MySqlContractContextRepository"]
