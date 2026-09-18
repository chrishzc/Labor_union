from subsystems.line.notification_policy import NotificationSourceEvent, evaluate_notification_rules


def _definition() -> dict[str, object]:
    return {
        "rules": [
            {
                "id": "post-service-satisfaction-survey",
                "event_code": "order_lifecycle_transition",
                "recipient_selector": "client.bound_case",
                "template_id": "post_service_satisfaction_survey",
                "enabled": True,
                "schedule": {"kind": "immediate"},
                "frequency": {"kind": "once"},
                "predicates": ["service_completion_reached"],
            }
        ]
    }


def test_survey_is_created_only_when_service_completion_is_reached() -> None:
    completed = NotificationSourceEvent(
        identity="orders-domain-outbox:1",
        event_code="order_lifecycle_transition",
        historical_silent=False,
        facts={"case_no": "CASE-1", "service_completion_reached": True},
    )
    not_completed = NotificationSourceEvent(
        identity="orders-domain-outbox:2",
        event_code="order_lifecycle_transition",
        historical_silent=False,
        facts={"case_no": "CASE-1", "service_completion_reached": False},
    )

    assert evaluate_notification_rules(completed, _definition())[0].status == "intent_created"
    assert evaluate_notification_rules(not_completed, _definition())[0].reason_code == "prerequisite_not_satisfied"
