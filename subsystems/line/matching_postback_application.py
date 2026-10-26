"""Canonical LINE postback adapter for matching decisions."""

from __future__ import annotations

import json
import re

from domains.line.identities import LineSourceType
from domains.scheduling.matching_communication import (
    MatchingCommunicationConflictError,
    MatchingCommunicationStaleError,
    MatchingDecisionNotReadyError,
    MatchingRecipientMismatchError,
)
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.deposit_notifications import handle_deposit_assistance

_MATCHING_POSTBACK = re.compile(
    r"^matching:([A-Za-z0-9_-]{20,191}):(willing|unwilling|accepted|declined|rejected|contact_requested)$"
)
_SCHEDULE_POSTBACK = re.compile(
    r"^schedule:([A-Za-z0-9_-]{20,191}):(confirmed|rejected)$"
)


class LineMatchingPostbackApplication:
    def __init__(self, matching_application) -> None:
        self._matching_application = matching_application

    def handle(self, inbox, unit_of_work) -> None:
        event = inbox.event
        if event.source.source_type is not LineSourceType.USER:
            return
        line_user_id = event.source.user_id
        if line_user_id is None:
            return
        postback_data = _postback_data(inbox)
        service_start_match = re.fullmatch(r"service-start:([A-Za-z0-9_-]{20,191}):(willing|unwilling)",postback_data)
        if service_start_match is not None:
            unit_of_work.service_starts.record_willingness(service_start_match.group(1),line_user_id.value,
                service_start_match.group(2),f"service-start-reply:{event.event_id.value}")
            return

        if handle_deposit_assistance(postback_data, event, unit_of_work):
            return
        match = _MATCHING_POSTBACK.fullmatch(postback_data)
        if match is not None:
            self._handle_matching_postback(match, line_user_id, event, unit_of_work)
            return
        # Retired date-confirmation cards cannot authorize any new arrangement.
        return

    def handle_message(self, inbox, unit_of_work, line_user_id, text) -> bool:
        return self._matching_application.append_customer_assistance_message_in_unit_of_work(
            unit_of_work, line_user_id, text,
            f"matching-assistance-message:{inbox.event.event_id.value}",
        )

    def _handle_matching_postback(self, match, line_user_id, event, unit_of_work):
        event_identity = event.event_id.value
        try:
            self._matching_application.record_line_response_in_unit_of_work(
                unit_of_work,
                token=match.group(1),
                # M3's public decision vocabulary is rejected; the legacy
                # communication root stores the equivalent declined value.
                decision="declined" if match.group(2) == "rejected" else match.group(2),
                line_user_id=line_user_id,
                idempotency_key=IdempotencyKey(f"matching-postback:{event_identity}"),
                correlation_id=CorrelationId(f"line-event:{event_identity}"),
                occurred_at=event.occurred_at,
            )
        except (
            LookupError,
            MatchingCommunicationConflictError,
            MatchingCommunicationStaleError,
            MatchingDecisionNotReadyError,
            MatchingRecipientMismatchError,
        ):
            return


def _postback_data(inbox) -> str:
    payload = json.loads(inbox.event.payload_json)
    postback = payload.get("postback")
    if not isinstance(postback, dict):
        return ""
    data = postback.get("data")
    return data.strip() if isinstance(data, str) else ""


__all__ = ["LineMatchingPostbackApplication"]
