"""Stage 7 canonical matching notification application transactions."""

from datetime import datetime, timezone
from types import SimpleNamespace

from domains.line.delivery import LineDeliveryStatus
from domains.line.identities import LineDeliveryTaskId, LineUserId
from domains.scheduling.matching_communication import (
    CaregiverWillingness,
    CustomerMatchingDecision,
    MatchingNotificationKind,
    MatchingPlanReference,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.scheduling.matching_notification_application import (
    MatchingNotificationApplication,
)
from subsystems.scheduling.matching_notification_contracts import (
    MatchingContactState,
    MatchingSegmentContact,
    RequestCaregiverInformationCommand,
)

NOW = datetime(2026, 8, 9, tzinfo=timezone.utc)


class _MatchingRepository:
    def __init__(self, state) -> None:
        self.state = state
        self.intent_arguments = None
        self.interaction_arguments = None
        self.projection_arguments = None

    def get_intent_result(self, key, fingerprint):
        return None

    def get_contact_state(self, case_no, plan_id, *, lock=False):
        return self.state

    def caregiver_card_facts(self, plan_id, segment_id):
        return {
            "case_no": "CASE-1",
            "start_date": "2026-09-01",
            "end_date": "2026-09-10",
            "city": "台北市",
            "service_type": "到府服務",
        }

    def append_notification_intent(self, **arguments):
        self.intent_arguments = arguments
        return 31

    def open_interaction(self, **arguments):
        self.interaction_arguments = arguments

    def project_intent(self, *arguments):
        self.projection_arguments = arguments


class _DeliveryRepository:
    def __init__(self) -> None:
        self.requests = []

    def enqueue(self, request):
        self.requests.append(request)
        return SimpleNamespace(task_id=LineDeliveryTaskId(41))


class _UnitOfWork:
    def __init__(self, state) -> None:
        self.matching_notifications = _MatchingRepository(state)
        self.delivery_tasks = _DeliveryRepository()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False

    def commit(self):
        self.committed = True


def _state():
    return MatchingContactState(
        MatchingPlanReference("CASE-1", 10, 0),
        "proposed",
        True,
        "洽談中",
        LineUserId("U-customer"),
        CustomerMatchingDecision.PENDING,
        None,
        (
            MatchingSegmentContact(
                20,
                1,
                30,
                "林月嫂",
                LineUserId("U-caregiver"),
                "2026-09-01",
                "2026-09-10",
                CaregiverWillingness.PENDING,
            ),
        ),
    )


def test_caregiver_card_intent_action_and_delivery_share_one_commit() -> None:
    unit_of_work = _UnitOfWork(_state())
    application = MatchingNotificationApplication(
        lambda: unit_of_work,
        lambda: NOW,
        token_factory=lambda: "safe-token-12345678901234567890",
        availability_validator=lambda state: None,
    )
    command = RequestCaregiverInformationCommand(
        MatchingPlanReference("CASE-1", 10, 0),
        20,
        MatchingNotificationKind.CAREGIVER_INFO_1,
        ActorContext("admin:1", ("line.matching.send",)),
        ExpectedVersion(0),
        IdempotencyKey("matching-info:1"),
        CorrelationId("correlation:1"),
    )

    result = application.request_caregiver_information(command)

    assert result.line_delivery_task_id == LineDeliveryTaskId(41)
    assert unit_of_work.committed
    assert unit_of_work.matching_notifications.intent_arguments["recipient"] == LineUserId(
        "U-caregiver"
    )
    assert "safe-token" not in str(
        unit_of_work.matching_notifications.intent_arguments["payload_snapshot"]
    )
    request = unit_of_work.delivery_tasks.requests[0]
    assert request.message_kind.value == "flex"
    assert "matching:safe-token-12345678901234567890:willing" in request.payload_json
    assert unit_of_work.matching_notifications.projection_arguments[0] == 31
