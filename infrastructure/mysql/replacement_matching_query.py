"""Project candidate matching eligibility from the current Orders and Scheduling facts."""

from domains.scheduling.matching_communication import CandidateMatchingError


_CURRENT_R04_MATCHING_SQL = """
    EXISTS (
        SELECT 1 FROM scheduling_service_before_replacement_events AS event
        JOIN scheduling_service_before_replacement_receipts AS receipt
          ON receipt.replacement_event_id=event.id
        WHERE event.case_no=orders.case_no AND event.scenario='R-04'
          AND event.replacement_generation_id=generation.id
    )
"""

_CURRENT_REOPEN_MATCHING_SQL = """
    EXISTS (
        SELECT 1 FROM order_reopen_apply_receipts AS reopen
        JOIN order_lifecycle_control_events AS cleared
          ON cleared.id=reopen.cancellation_control_event_id
          AND cleared.case_no=reopen.case_no AND cleared.control_type='cancellation'
          AND cleared.control_key='order_cancelled' AND cleared.action='clear'
        JOIN order_cancellation_apply_receipts AS cancellation
          ON cancellation.cancellation_event_id=reopen.cancellation_event_id
          AND cancellation.case_no=reopen.case_no
        JOIN order_lifecycle_control_events AS activated
          ON activated.id=cancellation.cancellation_control_event_id
          AND activated.case_no=reopen.case_no AND activated.control_type='cancellation'
          AND activated.control_key='order_cancelled' AND activated.action='activate'
        LEFT JOIN scheduling_command_receipts AS schedule_receipt
          ON schedule_receipt.id=cancellation.scheduling_command_receipt_id
          AND schedule_receipt.case_no=reopen.case_no
        WHERE reopen.case_no=orders.case_no AND reopen.lifecycle_status IN ('洽談中','訂單成立')
          AND control.state='cleared' AND control.current_event_id=cleared.id
          AND activated.id<cleared.id
          AND NOT EXISTS (
              SELECT 1 FROM order_lifecycle_control_events AS later
              WHERE later.case_no=reopen.case_no AND later.control_type='cancellation'
                AND later.control_key='order_cancelled'
                AND later.id>activated.id AND later.id<cleared.id
          )
          AND cancellation.official_service_day_count=0
          AND (
              (
                  generation.id IS NULL AND COALESCE(aggregate.aggregate_version,0)=0
                  AND cancellation.scheduling_version IS NULL
                  AND cancellation.scheduling_generation IS NULL
                  AND cancellation.scheduling_command_receipt_id IS NULL
              )
              OR (
                  generation.generation_number=cancellation.scheduling_generation
                  AND aggregate.aggregate_version=cancellation.scheduling_version
                  AND generation.resulting_aggregate_version=cancellation.scheduling_version
                  AND schedule_receipt.resulting_generation_id=generation.id
                  AND schedule_receipt.resulting_scheduling_version=cancellation.scheduling_version
              )
          )
    )
"""

_MATCHING_BLOCKER_SQL = """
    SELECT CASE
        WHEN orders.actual_start_date IS NOT NULL OR orders.actual_end_date IS NOT NULL
          OR orders.status IN ('服務中','訂單完成')
          OR EXISTS (
              SELECT 1 FROM order_service_data_locks AS service_lock
              WHERE service_lock.case_no=orders.case_no
          )
          THEN 'candidate_matching_service_started'
        WHEN orders.status NOT IN ('洽談中','訂單成立') OR control.state='active'
          THEN 'candidate_contact_order_not_negotiating'
        WHEN (aggregate.effective_generation_id IS NOT NULL AND generation.id IS NULL)
          OR EXISTS (
              SELECT 1 FROM case_staff_assignments AS assignment
              WHERE assignment.case_no=orders.case_no AND assignment.generation_id=generation.id
                AND (assignment.status IS NULL OR assignment.status NOT IN ('planned','active','completed'))
          )
          THEN 'candidate_matching_data_needs_review'
        WHEN EXISTS (
            SELECT 1 FROM case_staff_assignments AS assignment
            WHERE assignment.case_no=orders.case_no AND assignment.generation_id=generation.id
              AND assignment.status IN ('planned','active','completed')
        )
          THEN 'candidate_matching_assignment_present'
        WHEN orders.status='洽談中' OR {r04} OR {reopen} THEN NULL
        ELSE 'candidate_contact_order_not_negotiating'
    END
    FROM orders AS current_order
    LEFT JOIN scheduling_aggregates AS aggregate ON aggregate.case_no=current_order.case_no
    LEFT JOIN scheduling_generations AS generation
      ON generation.id=aggregate.effective_generation_id AND generation.case_no=aggregate.case_no
      AND generation.status='effective' AND generation.effective_marker=1
    LEFT JOIN order_lifecycle_control_state AS control
      ON control.case_no=current_order.case_no AND control.control_type='cancellation'
      AND control.control_key='order_cancelled'
    WHERE current_order.case_no=orders.case_no
""".format(r04=_CURRENT_R04_MATCHING_SQL, reopen=_CURRENT_REOPEN_MATCHING_SQL)

# The same SQL is used by the bounded follow-up scan and the case-scoped gates.
CANDIDATE_CONTACT_OPEN_SQL = f"(({_MATCHING_BLOCKER_SQL}) IS NULL)"


def candidate_matching_blocker(cursor, case_no: str) -> str | None:
    cursor.execute(
        f"SELECT ({_MATCHING_BLOCKER_SQL}) AS blocker FROM orders WHERE orders.case_no=%s",
        (case_no,),
    )
    row = cursor.fetchone()
    return row["blocker"] if row is not None else "candidate_contact_order_not_negotiating"


def replacement_matching_open(cursor, case_no: str) -> bool:
    return candidate_matching_blocker(cursor, case_no) is None


def candidate_contact_open(cursor, case_no: str, order_status: str) -> bool:
    return order_status in {"洽談中", "訂單成立"} and candidate_matching_blocker(cursor, case_no) is None


def require_candidate_matching_open(cursor, case_no: str) -> None:
    blocker = candidate_matching_blocker(cursor, case_no)
    if blocker is not None:
        raise CandidateMatchingError(blocker)
