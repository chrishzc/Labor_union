"""Read committed Orders/Scheduling facts without changing either owner."""
from datetime import date, datetime

from subsystems.orders.notification_continuation_query import OrderNotificationContinuationFacts


def historical_case_sql(order_alias):
    return (
        f"({order_alias}.status LIKE '歷史訂單%%' OR EXISTS ("
        "SELECT 1 FROM historical_order_adoption_receipts adoption "
        f"WHERE adoption.case_no={order_alias}.case_no AND adoption.outcome='adopted') "
        "OR EXISTS (SELECT 1 FROM order_lifecycle_state_events historical_restart "
        f"WHERE historical_restart.case_no={order_alias}.case_no "
        "AND historical_restart.trigger_event='orders_historical_precision_restart'))"
    )


def _restart_id_sql(order_alias):
    return (
        "(SELECT MAX(restart.id) FROM order_lifecycle_state_events restart "
        f"WHERE restart.case_no={order_alias}.case_no "
        "AND restart.trigger_event='orders_historical_precision_restart' "
        "AND restart.before_status IN ('歷史訂單－未服務','歷史訂單－服務中') "
        "AND restart.after_status='訂單成立')"
    )


def notification_continuation_eligible_sql(order_alias):
    return (
        f"(NOT {historical_case_sql(order_alias)} OR ("
        f"{order_alias}.status IN ('訂單成立','服務中') "
        f"AND {_restart_id_sql(order_alias)} IS NOT NULL "
        f"AND {order_alias}.actual_start_date IS NOT NULL "
        "AND EXISTS (SELECT 1 FROM scheduling_aggregates aggregate "
        "JOIN scheduling_generations generation ON generation.id=aggregate.effective_generation_id "
        "AND generation.case_no=aggregate.case_no AND generation.status='effective' AND generation.effective_marker=1 "
        "JOIN case_staff_assignments assignment ON assignment.generation_id=generation.id "
        "AND assignment.case_no=generation.case_no AND assignment.status IN ('planned','active','completed') "
        "JOIN staff_schedule schedule ON schedule.assignment_id=assignment.id "
        "AND schedule.generation_id=generation.id AND schedule.case_no=generation.case_no "
        "AND schedule.effective_marker=1 AND schedule.is_work_day=1 "
        f"WHERE aggregate.case_no={order_alias}.case_no)))"
    )


def _continuation_day_sql(order_alias):
    # A newer generation's creation date cannot prove when continuation began.
    return (
        "(SELECT MIN(event.business_date) FROM order_lifecycle_state_events event "
        f"WHERE event.case_no={order_alias}.case_no AND event.id>{_restart_id_sql(order_alias)} "
        "AND ((event.trigger_event='orders_historical_restart_arrangement' "
        "AND JSON_UNQUOTE(JSON_EXTRACT(event.facts_snapshot,'$.actual_start_date')) IS NOT NULL "
        "AND JSON_UNQUOTE(JSON_EXTRACT(event.facts_snapshot,'$.actual_start_date'))<>'null') "
        "OR (event.trigger_event IN ('actual_start_confirmed','actual_start_corrected') "
        "AND EXISTS (SELECT 1 FROM order_actual_start_apply_receipts receipt "
        "WHERE receipt.case_no=event.case_no AND receipt.lifecycle_event_id=event.id "
        "AND receipt.scheduling_command_receipt_id IS NOT NULL AND receipt.actual_start_date IS NOT NULL))))"
    )


def notification_continuation_columns(order_alias):
    return (
        f"{historical_case_sql(order_alias)} notification_historical,"
        f"{notification_continuation_eligible_sql(order_alias)} notification_eligible,"
        f"{_continuation_day_sql(order_alias)} notification_continuation_day"
    )


def notification_continuation_from_row(row):
    value = row['notification_continuation_day']
    if isinstance(value, datetime):
        value = value.date()
    elif isinstance(value, str):
        value = date.fromisoformat(value)
    elif value is not None and not isinstance(value, date):
        raise TypeError('notification_continuation_day must be a date or None')
    return OrderNotificationContinuationFacts(
        bool(row['notification_historical']), bool(row['notification_eligible']), value,
    )


class MySqlOrderNotificationContinuationQueryRepository:
    def __init__(self, connection):
        self.connection = connection

    def get(self, case_no, *, lock=False):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT '+notification_continuation_columns('o')+
                ' FROM orders o WHERE o.case_no=%s'+(' FOR UPDATE' if lock else ''), (case_no,))
            row = cursor.fetchone()
        return notification_continuation_from_row(row) if row else None
