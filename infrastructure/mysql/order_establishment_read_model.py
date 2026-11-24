"""Read committed Orders establishment references without inferring them from fees."""
from __future__ import annotations

from domains.orders.lifecycle import OrderEstablishmentEvidence, OrderLifecycleStatus

ESTABLISHMENT_EVENT_STATUS_VALUES = (
    OrderLifecycleStatus.ESTABLISHED.value,
    OrderLifecycleStatus.IN_SERVICE.value,
    OrderLifecycleStatus.COMPLETED.value,
    OrderLifecycleStatus.ESTABLISHED_UNSERVED.value,
)
_ESTABLISHMENT_EVENT_STATUSES_SQL = ",".join(f"'{value}'" for value in ESTABLISHMENT_EVENT_STATUS_VALUES)


def establishment_event_exists_sql(case_expression: str) -> str:
    statuses = _ESTABLISHMENT_EVENT_STATUSES_SQL
    return (
        "(EXISTS(SELECT 1 FROM order_lifecycle_state_events establishment_event "
        f"WHERE establishment_event.case_no={case_expression} AND "
        f"(establishment_event.before_status IN ({statuses}) OR "
        f"establishment_event.after_status IN ({statuses}))) OR "
        "EXISTS(SELECT 1 FROM historical_order_adoption_receipts establishment_adoption "
        "JOIN order_lifecycle_state_events adoption_event ON adoption_event.id=establishment_adoption.lifecycle_event_id "
        "AND adoption_event.case_no=establishment_adoption.case_no "
        f"WHERE establishment_adoption.case_no={case_expression} AND establishment_adoption.outcome='adopted' "
        "AND adoption_event.trigger_event='historical_order_adoption' "
        "AND adoption_event.after_status IN ('歷史訂單－未服務','歷史訂單－服務中','歷史訂單－服務完成','歷史訂單－帳務完成')))"
    )


def load_order_establishment_evidence(cursor, case_no, current_status=None, *, lock=False, historical_adoption_ids=()):
    cursor.execute(
        "SELECT id FROM order_lifecycle_state_events WHERE case_no=%s AND "
        f"(before_status IN ({_ESTABLISHMENT_EVENT_STATUSES_SQL}) OR "
        f"after_status IN ({_ESTABLISHMENT_EVENT_STATUSES_SQL})) ORDER BY id"
        + (" FOR UPDATE" if lock else ""),
        (case_no,),
    )
    return OrderEstablishmentEvidence(
        tuple(int(row["id"]) for row in cursor.fetchall()),
        historical_adoption_ids,
        OrderLifecycleStatus(current_status) if current_status is not None else None,
    )
