"""Manual reminder composition only; no runtime or LINE provider is started."""
from datetime import UTC, datetime
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from subsystems.line.payment_overdue_reminders import PaymentOverdueReminderApplication


def get_payment_overdue_reminders():
    return PaymentOverdueReminderApplication(open_line_unit_of_work,lambda:datetime.now(UTC))
