"""Read whether an established case is in its committed R-04 matching round."""

from domains.scheduling.matching_communication import matching_order_is_open


_CURRENT_R04_MATCHING_SQL = (
        "EXISTS (SELECT 1 FROM scheduling_aggregates aggregate "
        "JOIN scheduling_service_before_replacement_events event "
        "ON event.case_no=aggregate.case_no "
        "AND event.replacement_generation_id=aggregate.effective_generation_id "
        "JOIN scheduling_service_before_replacement_receipts receipt "
        "ON receipt.replacement_event_id=event.id "
        "WHERE aggregate.case_no=orders.case_no AND event.scenario='R-04' "
        "AND NOT EXISTS (SELECT 1 FROM case_staff_assignments assignment "
        "WHERE assignment.case_no=aggregate.case_no "
        "AND assignment.generation_id=aggregate.effective_generation_id))"
)

# SQL projection of matching_order_is_open, shared by bounded scans and cancellation.
CANDIDATE_CONTACT_OPEN_SQL = (
    "(orders.status='洽談中' OR (orders.status='訂單成立' AND "
    + _CURRENT_R04_MATCHING_SQL + "))"
)


def replacement_matching_open(cursor, case_no: str) -> bool:
    cursor.execute(
        "SELECT orders.case_no FROM orders WHERE orders.case_no=%s AND " + _CURRENT_R04_MATCHING_SQL,
        (case_no,),
    )
    return cursor.fetchone() is not None


def candidate_contact_open(cursor, case_no: str, order_status: str) -> bool:
    return matching_order_is_open(
        order_status,
        replacement_round=(order_status == "訂單成立" and replacement_matching_open(cursor, case_no)),
    )
