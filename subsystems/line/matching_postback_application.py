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
from subsystems.line.webhook_event_consumer import RetryableLineEventError, TerminalLineEventError

_MATCHING_POSTBACK = re.compile(
    r"^matching:([A-Za-z0-9_-]{20,191}):(willing|unwilling|accepted|declined|rejected|contact_requested)$"
)
_SCHEDULE_POSTBACK = re.compile(
    r"^schedule:([A-Za-z0-9_-]{20,191}):(confirmed|rejected)$"
)


class LineMatchingPostbackApplication:
    def __init__(self, matching_application) -> None:
        self._matching_application = matching_application

    def handle(self, inbox, unit_of_work, *, reply_only: bool = False) -> bool:
        event = inbox.event
        if event.source.source_type is not LineSourceType.USER:
            return False
        line_user_id = event.source.user_id
        if line_user_id is None:
            return False
        postback_data = _postback_data(inbox)
        service_start_match = re.fullmatch(r"service-start:([A-Za-z0-9_-]{20,191}):(willing|unwilling)",postback_data)
        if service_start_match is not None:
            unit_of_work.service_starts.record_willingness(service_start_match.group(1),line_user_id.value,
                service_start_match.group(2),f"service-start-reply:{event.event_id.value}")
            return True

        if handle_deposit_assistance(postback_data, event, unit_of_work, reply_only=reply_only):
            return not reply_only
        match = _MATCHING_POSTBACK.fullmatch(postback_data)
        if match is not None:
            deferred = match.group(2) in {"accepted", "contact_requested"}
            if deferred and reply_only:
                try:
                    self._matching_application.acknowledge_customer_postback(
                        unit_of_work, match.group(1), match.group(2), line_user_id, event,
                    )
                except (LookupError, MatchingCommunicationConflictError, MatchingCommunicationStaleError,
                        MatchingRecipientMismatchError):
                    return True
                return False
            self._handle_matching_postback(match, line_user_id, event, unit_of_work, deferred=deferred)
            return True
        # Retired date-confirmation cards cannot authorize any new arrangement.
        return False

    def has_active_assistance(self, unit_of_work, line_user_id, occurred_at) -> bool:
        return self._matching_application.has_active_customer_assistance(unit_of_work, line_user_id) or (
            self._matching_application.has_pending_customer_assistance(unit_of_work, line_user_id, occurred_at)
        )

    def handle_message(self, inbox, unit_of_work, line_user_id, text) -> bool:
        if self._matching_application.has_pending_customer_assistance(unit_of_work, line_user_id, inbox.event.occurred_at):
            raise RetryableLineEventError("matching_assistance_not_processed")
        return self._matching_application.append_customer_assistance_message_in_unit_of_work(
            unit_of_work, line_user_id, text,
            f"matching-assistance-message:{inbox.event.event_id.value}",
        )

    def _handle_matching_postback(self, match, line_user_id, event, unit_of_work, *, deferred=False):
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
                send_reply=not deferred,
            )
        except (
            LookupError,
            MatchingCommunicationConflictError,
            MatchingCommunicationStaleError,
            MatchingDecisionNotReadyError,
            MatchingRecipientMismatchError,
        ) as error:
            if deferred:
                raise TerminalLineEventError(str(error)) from error
        except ValueError as error:
            if deferred and str(error) == "automatic_waiting_deposit_occupancy_conflict":
                raise TerminalLineEventError("automatic_waiting_deposit_occupancy_conflict") from error
            raise


def _postback_data(inbox) -> str:
    payload = json.loads(inbox.event.payload_json)
    postback = payload.get("postback")
    if not isinstance(postback, dict):
        return ""
    data = postback.get("data")
    return data.strip() if isinstance(data, str) else ""


__all__ = ["LineMatchingPostbackApplication"]
