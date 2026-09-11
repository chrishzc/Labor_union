"""Recipient-bound LINE postback adapter for the candidate contact pool."""

from __future__ import annotations

import hashlib
import json
import re

from domains.line.identities import LineSourceType
from shared_kernel.identities import IdempotencyKey

_CANDIDATE_CONTACT_POSTBACK = re.compile(
    r"^candidate-contact:([0-9a-f]{64}):(willing|unwilling)$"
)


class LineCandidateContactPostbackApplication:
    def handle(self, inbox, unit_of_work) -> bool:
        event = inbox.event
        if event.source.source_type is not LineSourceType.USER:
            return False
        line_user_id = event.source.user_id
        if line_user_id is None:
            return False
        match = _CANDIDATE_CONTACT_POSTBACK.fullmatch(_postback_data(inbox))
        if match is None:
            return False
        try:
            unit_of_work.candidate_contact_pool_replies.record_willingness(
                match.group(1),
                match.group(2),
                line_user_id,
                IdempotencyKey(
                    "candidate-contact-postback:"
                    + hashlib.sha256(event.event_id.value.encode("utf-8")).hexdigest()
                ),
            )
        except (LookupError, ValueError):
            pass
        return True


def _postback_data(inbox) -> str:
    payload = json.loads(inbox.event.payload_json)
    postback = payload.get("postback")
    if not isinstance(postback, dict):
        return ""
    data = postback.get("data")
    return data.strip() if isinstance(data, str) else ""


__all__ = ["LineCandidateContactPostbackApplication"]
