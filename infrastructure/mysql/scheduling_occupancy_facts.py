"""MySQL facts shared by Scheduling availability and the locked generation writer."""

from domains.orders.lifecycle import OrderLifecycleStatus
from domains.scheduling.assignment_plan import StaffOccupancyFact
from infrastructure.mysql.order_terms_read_model import read_service_time_terms


def _lock_suffix(lock):
    return " FOR UPDATE" if lock else ""


def load_case_service_time(cursor, case_no, *, lock):
    cursor.execute(
        "SELECT service_start_time,service_end_time,service_end_day_offset "
        "FROM orders WHERE case_no=%s" + _lock_suffix(lock),
        (case_no,),
    )
    row = cursor.fetchone()
    return read_service_time_terms(row) if row is not None else None


def load_occupancy_snapshot(cursor, staff_ids, case_no, *, lock):
    if not staff_ids:
        return (), ()
    schedules = _effective_occupancy_rows(cursor, staff_ids, lock)
    waiting = _waiting_lock_rows(cursor, staff_ids, lock)
    facts = tuple(
        StaffOccupancyFact(
            int(row["staff_id"]), row["occupancy_date"], str(row["case_no"]),
            read_service_time_terms(row),
        )
        for row in (*schedules, *waiting)
    ) + _unavailability_occupancy(cursor, staff_ids, lock) + _legacy_assignment_occupancy(cursor, staff_ids, lock)
    facts += tuple(
        historical_reservation_occupancy(row)
        for row in load_historical_reservation_rows(cursor, staff_ids=staff_ids, lock=lock)
    )
    lock_ids = tuple(sorted({int(row["lock_id"]) for row in waiting if str(row["case_no"]) == case_no}))
    return facts, lock_ids


def load_historical_reservation_rows(cursor, *, staff_ids=None, window_start=None, window_end=None, lock=False):
    """Read planned occupancy until cancellation or replacement of the restart generation."""
    conditions = [
        "(o.status=%s OR (o.status=%s AND restart_event.before_status=%s))",
        "o.start_date<=o.end_date",
        "pairing.staff_id IS NOT NULL",
        "pairing.resolution IN ('evidence_only','assignment_candidate','assignment_reused')",
    ]
    params = [
        OrderLifecycleStatus.HISTORICAL_UNSERVED.value,
        OrderLifecycleStatus.ESTABLISHED.value,
        OrderLifecycleStatus.HISTORICAL_UNSERVED.value,
    ]
    if staff_ids is not None:
        if not staff_ids:
            return ()
        placeholders = ",".join("%s" for _ in staff_ids)
        conditions.append(f"pairing.staff_id IN ({placeholders})")
        params.extend(staff_ids)
    if window_start is not None:
        conditions.append("o.end_date>=%s")
        params.append(window_start)
    if window_end is not None:
        conditions.append("o.start_date<=%s")
        params.append(window_end)
    cursor.execute(
        "SELECT receipt.id AS source_id,pairing.staff_id,o.case_no,o.status AS order_status,"
        "o.start_date,o.end_date,c.name AS client_name,s.name AS staff_name "
        "FROM orders o "
        "JOIN historical_order_adoption_receipts receipt ON receipt.case_no=o.case_no AND receipt.outcome='adopted' "
        "LEFT JOIN historical_order_adoption_receipts newer ON newer.case_no=receipt.case_no "
        "AND newer.outcome='adopted' AND newer.id>receipt.id "
        "JOIN historical_order_pairing_evidence pairing ON pairing.receipt_id=receipt.id "
        "JOIN clients c ON c.id=o.client_id JOIN staff s ON s.id=pairing.staff_id "
        "LEFT JOIN scheduling_aggregates aggregate ON aggregate.case_no=o.case_no "
        "LEFT JOIN scheduling_generations generation ON generation.id=aggregate.effective_generation_id "
        "AND generation.effective_marker=1 "
        "LEFT JOIN scheduling_command_receipts restart ON restart.resulting_generation_id=generation.id "
        "AND restart.case_no=aggregate.case_no AND restart.command_family='orders_historical_precision_restart' "
        "LEFT JOIN order_lifecycle_state_events restart_event ON restart_event.case_no=aggregate.case_no "
        "AND restart_event.idempotency_key=restart.idempotency_key "
        "AND restart_event.trigger_event=restart.command_family "
        f"WHERE newer.id IS NULL AND {' AND '.join(conditions)} "
        "ORDER BY pairing.staff_id,o.start_date,o.case_no,pairing.caregiver_ordinal" + _lock_suffix(lock),
        tuple(params),
    )
    rows = cursor.fetchall()
    return tuple({(row["case_no"], row["staff_id"]): row for row in rows}.values())


def historical_reservation_occupancy(row):
    return StaffOccupancyFact(
        int(row["staff_id"]), row["start_date"], str(row["case_no"]),
        all_day=True, block_end=row["end_date"],
    )


def _effective_occupancy_rows(cursor, staff_ids, lock):
    placeholders = ",".join("%s" for _ in staff_ids)
    cursor.execute(
        "SELECT s.id AS source_id,s.staff_id,s.work_date AS occupancy_date,"
        "COALESCE(a.case_no,'legacy_schedule') AS case_no,"
        "o.service_start_time,o.service_end_time,o.service_end_day_offset "
        "FROM staff_schedule s "
        "LEFT JOIN scheduling_generations g ON g.id=s.generation_id "
        "LEFT JOIN case_staff_assignments a ON a.id=s.assignment_id "
        "LEFT JOIN orders o ON o.case_no=a.case_no "
        f"WHERE s.staff_id IN ({placeholders}) AND s.effective_marker=1 AND s.is_work_day=1 "
        "AND (s.generation_id IS NULL OR g.effective_marker=1) "
        "AND (a.id IS NULL OR a.status NOT IN ('cancelled','replaced','completed')) "
        "ORDER BY s.staff_id,s.work_date,s.id" + _lock_suffix(lock),
        staff_ids,
    )
    return tuple(cursor.fetchall())


def _legacy_assignment_occupancy(cursor, staff_ids, lock):
    return tuple(
        StaffOccupancyFact(int(row["staff_id"]), row["assigned_start_date"], str(row["case_no"]),
                           possible_end=row["assigned_end_date"])
        for row in _legacy_assignment_rows(cursor, staff_ids, lock)
    )


def _legacy_assignment_rows(cursor, staff_ids, lock):
    placeholders = ",".join("%s" for _ in staff_ids)
    cursor.execute(
        "SELECT a.id,a.staff_id,a.case_no,a.assigned_start_date,a.assigned_end_date "
        "FROM case_staff_assignments a "
        f"WHERE a.staff_id IN ({placeholders}) AND a.generation_id IS NULL "
        "AND a.status IN ('planned','active') "
        "AND a.assigned_start_date IS NOT NULL AND a.assigned_end_date IS NOT NULL "
        "AND NOT EXISTS(SELECT 1 FROM staff_schedule s WHERE s.assignment_id=a.id "
        "AND s.effective_marker=1 AND s.is_work_day=1) "
        "AND NOT EXISTS(SELECT 1 FROM order_lifecycle_state_events e WHERE e.case_no=a.case_no "
        "AND e.trigger_event='orders_historical_precision_restart') "
        "ORDER BY a.staff_id,a.id" + _lock_suffix(lock),
        staff_ids,
    )
    return tuple(cursor.fetchall())


def _waiting_lock_rows(cursor, staff_ids, lock):
    placeholders = ",".join("%s" for _ in staff_ids)
    cursor.execute(
        "SELECT d.id AS source_id,d.staff_id,d.lock_date AS occupancy_date,p.case_no,l.id AS lock_id,"
        "o.service_start_time,o.service_end_time,o.service_end_day_offset "
        "FROM caregiver_availability_lock_days d "
        "JOIN caregiver_availability_locks l ON l.id=d.lock_id "
        "JOIN caregiver_matching_plan_segments s ON s.id=d.segment_id "
        "JOIN caregiver_matching_plans p ON p.id=s.plan_id "
        "JOIN orders o ON o.case_no=p.case_no "
        f"WHERE d.staff_id IN ({placeholders}) "
        "AND d.active_marker=1 AND l.is_active=1 "
        "ORDER BY d.staff_id,d.lock_date,p.case_no" + _lock_suffix(lock),
        staff_ids,
    )
    return tuple(cursor.fetchall())


def _unavailability_occupancy(cursor, staff_ids, lock):
    return tuple(
        StaffOccupancyFact(int(row["staff_id"]), row["start_date"], "staff_unavailability",
                           all_day=True, block_end=row["end_date"])
        for row in _unavailability_rows(cursor, staff_ids, lock)
    )


def _unavailability_rows(cursor, staff_ids, lock):
    placeholders = ",".join("%s" for _ in staff_ids)
    cursor.execute(
        "SELECT id,staff_id,start_date,end_date FROM scheduling_staff_unavailability_blocks "
        f"WHERE staff_id IN ({placeholders}) AND status='effective' ORDER BY staff_id,id"
        + _lock_suffix(lock),
        staff_ids,
    )
    return tuple(cursor.fetchall())
