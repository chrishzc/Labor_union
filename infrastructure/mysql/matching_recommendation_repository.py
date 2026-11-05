"""
File: matching_recommendation_repository.py
Description: 讀取排班媒合候選事實，排除 legacy inactive 與 lifecycle retired 人員。
"""

from __future__ import annotations

from domains.scheduling.assignment_plan import service_shift_may_overlap
from infrastructure.mysql.order_terms_read_model import read_service_time_terms
from infrastructure.mysql.scheduling_occupancy_facts import load_occupancy_snapshot
from subsystems.scheduling.matching_recommendation_query import StaffCandidate


class MySqlMatchingRecommendationRepository:
    def __init__(self, connection): self._connection = connection

    def load_request_facts(self, case_no):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT o.start_date AS planned_start_date,"
                "o.end_date AS planned_end_date,o.service_days,"
                "c.city,c.address,c.service_time,"
                "o.service_start_time,o.service_end_time,o.service_end_day_offset "
                "FROM orders o JOIN clients c ON c.id=o.client_id "
                "WHERE o.case_no=%s",
                (case_no,),
            )
            row = cursor.fetchone()
            return {**row, "service_time_terms": read_service_time_terms(row)} if row else None

    def load_candidates(self, service_dates, *, case_no, service_time):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT s.id,s.name,s.phone,binding.line_user_id,s.care_babies FROM staff s "
                "LEFT JOIN staff_lifecycle_states lifecycle ON lifecycle.staff_id=s.id "
                "LEFT JOIN line_identity_role_bindings binding ON binding.subject_type='staff' "
                "AND binding.subject_reference=CAST(s.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
                "AND binding.binding_status='bound' AND binding.line_user_id=s.line_user_id "
                "WHERE s.status='active' AND COALESCE(lifecycle.lifecycle_state,'active')='active'"
            )
            staff = tuple(cursor.fetchall())
            cursor.execute("SELECT staff_id,region_name FROM staff_regions")
            regions = _group(cursor.fetchall(), "region_name")
            cursor.execute("SELECT staff_id,slot_name FROM staff_time_slots")
            slots = _group(cursor.fetchall(), "slot_name")
            facts, _ = load_occupancy_snapshot(cursor, tuple(int(row["id"]) for row in staff), case_no, lock=False)
            occupied = {}
            for fact in facts:
                if fact.source_case_no == case_no:
                    continue
                occupied.setdefault(fact.staff_id, set()).update(
                    day for day in service_dates if service_shift_may_overlap(day, service_time, fact)
                )
        return tuple(StaffCandidate(int(row['id']), str(row['name']), row.get('phone'), row.get('line_user_id'), tuple(regions.get(row['id'], ())), int(row.get('care_babies') or 1), tuple(slots.get(row['id'], ())), frozenset(occupied.get(row['id'], ()))) for row in staff)

def _group(rows, value_key):
    grouped = {}
    for row in rows: grouped.setdefault(int(row['staff_id']), []).append(str(row[value_key]))
    return grouped
