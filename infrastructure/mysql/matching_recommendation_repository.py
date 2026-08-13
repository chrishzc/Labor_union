"""Read-only MySQL facts for Scheduling matching recommendations."""

from __future__ import annotations

from datetime import timedelta

from subsystems.scheduling.matching_recommendation_query import StaffCandidate


class MySqlMatchingRecommendationRepository:
    def __init__(self, connection): self._connection = connection

    def load_request_facts(self, case_no):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT o.planned_start_date,o.planned_end_date,o.service_days,c.city,c.address,c.service_time FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s", (case_no,))
            return cursor.fetchone()

    def load_candidates(self, service_dates):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id,name,phone,line_user_id,care_babies FROM staff WHERE status='active'")
            staff = tuple(cursor.fetchall())
            cursor.execute("SELECT staff_id,region_name FROM staff_regions")
            regions = _group(cursor.fetchall(), "region_name")
            cursor.execute("SELECT staff_id,slot_name FROM staff_time_slots")
            slots = _group(cursor.fetchall(), "slot_name")
            occupied = self._occupied_dates(cursor, service_dates)
        return tuple(StaffCandidate(int(row['id']), str(row['name']), row.get('phone'), row.get('line_user_id'), tuple(regions.get(row['id'], ())), int(row.get('care_babies') or 1), tuple(slots.get(row['id'], ())), frozenset(occupied.get(row['id'], ()))) for row in staff)

    def _occupied_dates(self, cursor, service_dates):
        if not service_dates: return {}
        start, end = min(service_dates), max(service_dates)
        cursor.execute("SELECT staff_id,assigned_start_date,assigned_end_date FROM case_staff_assignments WHERE status IN ('planned','active') AND assigned_start_date<=%s AND assigned_end_date>=%s", (end, start))
        assignments = cursor.fetchall()
        cursor.execute("SELECT staff_id,lock_date FROM caregiver_availability_lock_days WHERE active_marker=1 AND lock_date BETWEEN %s AND %s", (start, end + timedelta(days=7)))
        locks = cursor.fetchall()
        return _dates_by_staff(assignments, locks, start, end)


def _group(rows, value_key):
    grouped = {}
    for row in rows: grouped.setdefault(int(row['staff_id']), []).append(str(row[value_key]))
    return grouped


def _dates_by_staff(assignments, locks, start, end):
    occupied = {}
    for row in assignments:
        current = max(row['assigned_start_date'], start)
        final = min(row['assigned_end_date'], end)
        while current <= final:
            occupied.setdefault(int(row['staff_id']), set()).add(current); current += timedelta(days=1)
    for row in locks: occupied.setdefault(int(row['staff_id']), set()).add(row['lock_date'])
    return occupied
