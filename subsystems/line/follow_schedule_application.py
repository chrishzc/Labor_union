"""Expand a committed LINE follow event into idempotent D+N deliveries."""

from __future__ import annotations

from domains.line.configuration import LineConfigurationKind
from domains.line.delivery import LineDeliveryRequest, LineRecipient, LineRecipientType
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.message_configuration import (
    configuration_definition,
    follow_schedule_steps,
    render_message_template,
)


def enqueue_follow_schedule(inbox, unit_of_work, line_user_id) -> int:
    schedules = configuration_definition(
        unit_of_work.configurations.get(LineConfigurationKind.MESSAGE_SCHEDULES)
    )
    templates = configuration_definition(
        unit_of_work.configurations.get(LineConfigurationKind.MESSAGE_TEMPLATES)
    )
    if not schedules or not templates:
        return 0
    event_identity = inbox.event.event_id.value
    count = 0
    for step in follow_schedule_steps(
        schedules,
        templates,
        inbox.event.occurred_at,
    ):
        message = render_message_template(templates, step.template_id)
        schedule_identity = (
            event_identity
            if step.restart_on_refollow
            else line_user_id.value
        )
        key = (
            f"follow-schedule:{schedule_identity}:{step.schedule_id}:d{step.day}"
        )
        unit_of_work.delivery_tasks.enqueue(
            LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, line_user_id),
                message.message_kind,
                message.payload_json,
                step.scheduled_at,
                IdempotencyKey(key),
                CorrelationId(f"line-event:{event_identity}"),
                "line_follow_schedule",
                f"{schedule_identity}:{step.schedule_id}",
            )
        )
        count += 1
    return count


__all__ = ["enqueue_follow_schedule"]
