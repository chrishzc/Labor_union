"""Public notification workbench projections; no additional task state."""
from enum import StrEnum
from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator
from api.routes.line_payment_overdue_reminders import PaymentSnapshot
from api.schemas.line_candidate_contact import CandidateInformationStaffItemView


class LogReminderContext(BaseModel):
    case_no: str
    staff_id: int
    missing_from: date
    missing_through: date


NotificationCursor = Annotated[
    Annotated[int, Field(ge=0)] | Annotated[str, Field(min_length=1, max_length=2048)],
    BeforeValidator(lambda value: int(value) if isinstance(value, str) and value.isdecimal() else value),
]


class NotificationFailureContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    issue_key: str = Field(pattern=r'^ci_[0-9a-f]{64}$')
    notification_reason: Literal['recipient_unavailable', 'template_or_schedule_invalid']
    related_task_ids: list[int] = Field(default_factory=list)


class NotificationFailureSourceView(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_event_id: int = Field(gt=0)
    event_code: str
    can_replay: bool
    unavailable_reason: str | None


class NotificationFailureDetailView(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_no: str
    notification_reason: Literal['recipient_unavailable', 'template_or_schedule_invalid']
    sources: list[NotificationFailureSourceView]
    related_task_ids: list[int]


class NotificationSource(StrEnum):
    REGISTRATION = 'registration'
    IDENTITY = 'identity'
    CUSTOMER_BINDING = 'customer_binding'
    STAFF_BINDING = 'staff_binding'
    PROFILE = 'profile'
    INFORMATION = 'information'
    FOLLOWUP = 'followup'
    RECOMMENDATION = 'recommendation'
    SERVICE_START = 'service_start'
    LEAVE = 'leave'
    DEPOSIT = 'deposit'
    GROUP = 'group'
    OVERDUE = 'overdue'
    LOG = 'log'
    CUSTOMER_SERVICE = 'customer_service'
    DELIVERY = 'delivery'
    NOTIFICATION_FAILURE = 'notification_failure'
    RUNTIME = 'runtime'


class NotificationItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    source: NotificationSource
    group: Literal['review', 'reminder', 'support']
    title: str
    case_no: str | None = None
    reference_id: int | None = None
    person: str = ''
    summary: str
    reason: str
    time: str = ''
    tag: str = '待處理'
    recipient: str | None = None
    message: str | None = None
    unavailable_reason: str | None = None
    expected_version: int | None = None
    delivery_status: str | None = None
    payment: PaymentSnapshot | None = None
    log: LogReminderContext | None = None
    information: CandidateInformationStaffItemView | None = None
    failure: NotificationFailureContext | None = None


class NotificationPage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[NotificationItem]
    total: int | None = None
    next_cursor: NotificationCursor | None = None


class NotificationSourceView(BaseModel):
    source: NotificationSource
    label: str
    group: Literal['review', 'reminder', 'support']


class MobileNotificationQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    line_id_token: str = Field(min_length=1, max_length=4096)
    cursor: NotificationCursor = 0
