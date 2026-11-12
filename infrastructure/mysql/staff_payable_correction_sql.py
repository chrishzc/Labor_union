"""Effective legal amount for one frozen obligation and its handover deltas.

Original obligations/events and actual payout links remain immutable. Correction
rows are accounting events, never independently selectable payment obligations.
"""


def effective_staff_obligation_amount(alias="obligations"):
    return (
        f"COALESCE((SELECT COALESCE(c.settlement_base_ntd,c.effective_ntd) FROM payroll_amount_controls c WHERE c.obligation_identity={alias}.obligation_identity),({alias}.amount_due_ntd + COALESCE((SELECT SUM(CASE "
        "WHEN handover_delta.direction='payable_to_staff' THEN handover_delta.amount_due_ntd "
        "ELSE -handover_delta.amount_due_ntd END) FROM staff_obligations handover_delta "
        f"WHERE handover_delta.source_obligation_identity={alias}.obligation_identity "
        f"AND handover_delta.case_no={alias}.case_no AND handover_delta.staff_id={alias}.staff_id "
        "AND handover_delta.obligation_identity LIKE 'staff-handover:%%' "
        "AND handover_delta.status<>'cancelled'),0)))"
    )


def selectable_staff_obligation(alias="obligations"):
    return f"{alias}.obligation_identity NOT LIKE 'staff-handover:%%'"


def staff_obligation_funding_not_held(alias="obligations"):
    return (
        "NOT COALESCE(JSON_CONTAINS((SELECT JSON_EXTRACT(e.facts_snapshot,'$.funding_review.obligation_ids') "
        f"FROM order_lifecycle_state_events e WHERE e.case_no={alias}.case_no "
        "AND e.trigger_event IN ('official_service_attribution_corrected','official_service_attribution_funding_confirmed') "
        "AND JSON_CONTAINS_PATH(e.facts_snapshot,'one','$.funding_review') ORDER BY e.id DESC LIMIT 1), "
        f"JSON_QUOTE({alias}.obligation_identity)),0)"
    )
