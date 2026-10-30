"""Current payment reminder schedule in the existing versioned LINE configuration."""
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
import json
import re

from domains.line.configuration import LineConfigurationKind
from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.line.message_configuration import LineMessageConfigurationError


@dataclass(frozen=True, slots=True)
class PaymentReminderSchedule:
    deposit_mode: str = 'immediate'
    deposit_time: str = '09:00'
    first_time: str = '09:00'
    second_time: str = '09:00'
    overdue_time: str = '10:00'


def parse_schedule(value) -> PaymentReminderSchedule:
    if not isinstance(value,dict) or set(value)!=set(asdict(PaymentReminderSchedule())):
        raise LineMessageConfigurationError('繳款提醒排程欄位不完整或不支援。')
    if value['deposit_mode'] not in ('immediate','daily'):
        raise LineMessageConfigurationError('訂金提醒時機不正確。')
    for field in ('deposit_time','first_time','second_time','overdue_time'):
        if not isinstance(value[field],str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',value[field]):
            raise LineMessageConfigurationError('請使用有效的 24 小時制提醒時間。')
    return PaymentReminderSchedule(**value)


def schedule_from_unit(unit) -> PaymentReminderSchedule:
    snapshot=unit.configurations.get(LineConfigurationKind.MESSAGE_SCHEDULES)
    definition=json.loads(snapshot.definition_json)
    return parse_schedule(definition['payment_reminders']) if 'payment_reminders' in definition else PaymentReminderSchedule()


def at_time(day: date, value: str) -> datetime:
    return datetime.combine(day,time.fromisoformat(value),TAIPEI_TIME_ZONE)


def followup_earliest(due_date: date, original_sent_at: datetime) -> datetime:
    return max(at_time(due_date+timedelta(days=1),'00:00'),original_sent_at.astimezone(TAIPEI_TIME_ZONE)+timedelta(hours=24))


def followup_at(due_date: date, original_sent_at: datetime, schedule: PaymentReminderSchedule) -> datetime:
    earliest=followup_earliest(due_date,original_sent_at)
    result=at_time(earliest.date(),schedule.overdue_time)
    return result+timedelta(days=1) if result<earliest else result
