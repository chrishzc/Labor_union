"""Compose typed Scheduling gaps and current original case-group binding for LINE."""
from datetime import date

from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.service_day_log_repository import MySqlServiceDayLogRepository
from subsystems.line.service_day_log_reminders import (
    PREFIX, SendServiceDayLogReminder, ServiceDayLogReminder, reminder_text,
)
from domains.line.identities import LineDeliveryTaskId
from subsystems.line.delivery_contracts import EnqueueLineDeliveryResult, LineDeliveryCommandOutcome


class MySqlServiceDayLogReminderRepository:
    def message(self, staff_name):
        from infrastructure.mysql.line_message_copy import configured_message_payload
        return configured_message_payload(self.connection, 'service-day-log-reminder', {"type": "text", "text": reminder_text(staff_name)}, {'staff_name': staff_name})["text"]

    def __init__(self, connection):
        self.connection = connection
        self.scheduling = MySqlServiceDayLogRepository(connection)

    def _group(self, case_no, *, lock=False):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT group_id,aggregate_version FROM line_order_group_bindings WHERE case_no=%s "
                           "AND binding_status IN ('bound','inviting','active','attention')"
                           + (" FOR UPDATE" if lock else ""), (case_no,))
            row = cursor.fetchone()
        return (str(row["group_id"]), int(row["aggregate_version"])) if row and row["group_id"] else None

    def list(self, now, page, page_size):
        gaps, total = self.scheduling.missing_runs(now, page=page, page_size=page_size)
        names = {}
        if gaps:
            identities = tuple({gap.staff_id for gap in gaps})
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT id,name FROM staff WHERE id IN (" + ",".join(["%s"]*len(identities)) + ")", identities)
                names = {int(row['id']):str(row['name']) for row in cursor.fetchall()}
        return tuple(ServiceDayLogReminder(gap, f"案件 {gap.case_no} 群組", bool(self._group(gap.case_no)),
                                         self.message(names[gap.staff_id]) if gap.staff_id in names else None)
                     for gap in gaps), total

    def recipient(self, command, now):
        # Same assignment lock as the log writer, before the fresh missing-log read.
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE", (command.case_no,))
            if cursor.fetchone() is None:
                return None
            cursor.execute("SELECT id FROM case_staff_assignments WHERE case_no=%s AND staff_id=%s FOR UPDATE",
                           (command.case_no, command.staff_id))
            cursor.fetchall()
        binding = self._group(command.case_no, lock=True)
        if not binding:
            return None
        # Exact selected interval must still be an unbroken missing run; growing runs remain applicable.
        if not self.scheduling.interval_is_missing(command.case_no, command.staff_id,
                                                   command.missing_from, command.missing_through, now):
            return None
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT name FROM staff WHERE id=%s FOR SHARE", (command.staff_id,))
            staff = cursor.fetchone()
        return (binding[0], str(staff["name"]), binding[1]) if staff and staff["name"] else None

    def enqueue(self, request):
        return MySqlLineDeliveryTaskRepository(self.connection).enqueue(request)

    def replay(self, command):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id FROM line_delivery_tasks WHERE idempotency_key=%s FOR UPDATE",
                           (f"service-day-log-manual:{command.idempotency_key}",))
            row = cursor.fetchone()
        if row is None:
            return None
        task = MySqlLineDeliveryTaskRepository(self.connection).get(LineDeliveryTaskId(int(row["id"])))
        if (task.request.source_aggregate_identity != command.case_no
                or not task.request.correlation_id.value.startswith(command.correlation.value + ":")):
            raise RuntimeError("line_delivery_idempotency_conflict")
        return EnqueueLineDeliveryResult(LineDeliveryCommandOutcome.EXISTING, task.task_id, task.status)

    def delivery_is_current(self, task, now):
        try:
            staff_id, start, end, version = task.request.correlation_id.value.removeprefix(PREFIX).split(":")
            command = SendServiceDayLogReminder(task.request.source_aggregate_identity, int(staff_id),
                                               date.fromisoformat(start), date.fromisoformat(end), "delivery")
        except (ValueError, TypeError):
            return False
        recipient = self.recipient(command, now)
        return bool(recipient and task.request.recipient.recipient_type.value == "group"
                    and recipient[0] == task.request.recipient.identity.value and recipient[2] == int(version))
