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

_MATCHING_POSTBACK = re.compile(
    r"^matching:([A-Za-z0-9_-]{20,191}):(willing|unwilling|accepted|declined|contact_requested)$"
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
        match = _MATCHING_POSTBACK.fullmatch(postback_data)
        if match is not None:
            self._handle_matching_postback(match, line_user_id, event, unit_of_work)
            return
        schedule_match = _SCHEDULE_POSTBACK.fullmatch(postback_data)
        if schedule_match is None:
            return
        try:
            unit_of_work.matching_schedule_confirmations.confirm_line_postback(
                schedule_match.group(1), schedule_match.group(2), line_user_id,
                f"matching-schedule-postback:{event.event_id.value}",
            )
        except (LookupError, ValueError):
            return

    def handle_message(self, inbox, unit_of_work, line_user_id, text) -> bool:
        event_key = f"matching-schedule-rejection-reason:{inbox.event.event_id.value}"
        try:
            return bool(
                unit_of_work.matching_schedule_confirmations.confirm_line_rejection_reason(
                    line_user_id,
                    text,
                    event_key,
                )
            )
        except (LookupError, ValueError):
            return False

    def _handle_matching_postback(self, match, line_user_id, event, unit_of_work):
        event_identity = event.event_id.value
        try:
            self._matching_application.record_line_response_in_unit_of_work(
                unit_of_work,
                token=match.group(1),
                decision=match.group(2),
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
