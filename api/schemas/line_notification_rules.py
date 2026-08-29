"""
File: line_notification_rules.py
Description: 定義 LINE 通知規則矩陣、預覽、儲存啟用與刪除 API 的 typed 輸入。
"""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from domains.line.notification_rules import registered_notification_event_codes

Identifier = Annotated[StrictStr, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
Sha256Hex = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImmediateSchedule(_ClosedModel):
    kind: Literal["immediate"]


class RelativeServiceTimeSchedule(_ClosedModel):
    kind: Literal["relative_service_time"]
    offset_seconds: StrictInt = Field(ge=0)


class ServiceEndSchedule(_ClosedModel):
    kind: Literal["service_end"]


NotificationSchedule = Annotated[
    ImmediateSchedule | RelativeServiceTimeSchedule | ServiceEndSchedule,
    Field(discriminator="kind"),
]


class OnceFrequency(_ClosedModel):
    kind: Literal["once"] = "once"


class RecurringBoundedFrequency(_ClosedModel):
    kind: Literal["recurring_bounded"]
    maximum_occurrences: StrictInt = Field(ge=1)
    interval_days: StrictInt = Field(ge=1)


NotificationFrequency = Annotated[
    OnceFrequency | RecurringBoundedFrequency,
    Field(discriminator="kind"),
]


class LineNotificationRuleInput(_ClosedModel):
    id: Identifier
    event_code: Identifier
    recipient_selector: Literal["client", "assigned_caregiver", "case_group"]
    template_id: Identifier
    enabled: StrictBool = False
    schedule: NotificationSchedule
    frequency: NotificationFrequency = Field(default_factory=OnceFrequency)
    predicates: tuple[
        Literal["requires_cooking_true", "baby_log_missing", "beclass_missing"], ...
    ] = ()

    @model_validator(mode="after")
    def require_registered_enabled_event(self):
        if self.enabled and self.event_code not in registered_notification_event_codes():
            raise ValueError("enabled notification event is not registered")
        if len(self.predicates) != len(set(self.predicates)):
            raise ValueError("notification predicates must be unique")
        return self


class LineNotificationRulesDefinition(_ClosedModel):
    rules: tuple[LineNotificationRuleInput, ...]


class LineNotificationRulesCatalogView(_ClosedModel):
    revision: StrictInt
    definition: LineNotificationRulesDefinition


class LineNotificationTimelineRecordView(_ClosedModel):
    source_event_id: StrictInt
    event_code: StrictStr
    occurred_at_utc: StrictStr
    historical_silent: StrictBool
    rule_id: StrictStr | None
    decision_status: StrictStr | None
    reason_code: StrictStr | None
    recipient_type: StrictStr | None
    recipient_masked: StrictStr | None
    occurrence_number: StrictInt | None
    intent_status: StrictStr | None
    scheduled_at_utc: StrictStr | None
    delivery_status: StrictStr | None
    delivery_task_id: StrictInt | None


class LineNotificationTimelineView(_ClosedModel):
    case_no: StrictStr
    records: list[LineNotificationTimelineRecordView]


class PreviewLineNotificationManualReplayView(_ClosedModel):
    source_event_id: StrictInt
    event_code: StrictStr
    historical_silent: StrictBool
    matching_rule_count: StrictInt
    will_create_new_immutable_source: StrictBool


class ApplyLineNotificationManualReplayView(_ClosedModel):
    source_event_id: StrictInt
    replayed_source_event_id: StrictInt


class _MutationRequest(_ClosedModel):
    expected_revision: StrictInt = Field(ge=0)
    preview_fingerprint: Sha256Hex
    reason: StrictStr = Field(min_length=1, max_length=1_000)
    idempotency_key: StrictStr = Field(min_length=1, max_length=191)
    correlation_id: StrictStr = Field(min_length=1, max_length=191)

    @field_validator("reason", "idempotency_key", "correlation_id")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("notification mutation text must not be blank")
        return value


class PreviewLineNotificationRulesRequest(_ClosedModel):
    expected_revision: StrictInt = Field(ge=0)
    definition: LineNotificationRulesDefinition


class SaveLineNotificationRulesRequest(_MutationRequest):
    definition: LineNotificationRulesDefinition


class DeleteLineNotificationRuleRequest(_MutationRequest):
    pass


class PreviewLineNotificationRulesView(_ClosedModel):
    before_revision: StrictInt
    resulting_revision: StrictInt
    definition: LineNotificationRulesDefinition
    fingerprint: Sha256Hex


class SaveLineNotificationRulesView(_ClosedModel):
    revision: StrictInt
    preview_fingerprint: Sha256Hex
    cancelled_intent_count: StrictInt = Field(ge=0)
    cancelled_task_count: StrictInt = Field(ge=0)


class DeleteLineNotificationRuleView(SaveLineNotificationRulesView):
    rule_id: Identifier


class ApplyLineNotificationManualReplayRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1_000)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)

    @field_validator("reason", "idempotency_key", "correlation_id")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("notification mutation text must not be blank")
        return value


__all__ = [
    "ApplyLineNotificationManualReplayView",
    "DeleteLineNotificationRuleRequest",
    "DeleteLineNotificationRuleView",
    "ApplyLineNotificationManualReplayRequest",
    "LineNotificationRuleInput",
    "LineNotificationRulesDefinition",
    "LineNotificationRulesCatalogView",
    "LineNotificationTimelineRecordView",
    "LineNotificationTimelineView",
    "PreviewLineNotificationManualReplayView",
    "PreviewLineNotificationRulesRequest",
    "PreviewLineNotificationRulesView",
    "SaveLineNotificationRulesRequest",
    "SaveLineNotificationRulesView",
]
