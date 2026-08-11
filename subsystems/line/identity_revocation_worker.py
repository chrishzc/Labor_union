"""Durable provider worker that resets Rich Menu before identity finalization."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Callable

from domains.line.identities import LineUserId
from subsystems.line.identity_management_application import (
    IDENTITY_MENU_RESET_INTENT,
    LineIdentityManagementApplication,
)
from subsystems.line.outbox_contracts import ClaimLineOutboxQuery, CompleteLineOutboxCommand
from subsystems.line.rich_menu_contracts import LineRichMenuProviderOutcomeType


class LineIdentityRevocationWorker:
    def __init__(
        self,
        unit_of_work_factory,
        provider,
        worker_identity: str,
        now: Callable[[], datetime],
        batch_size: int = 10,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._provider = provider
        self._worker_identity = worker_identity
        self._now = now
        self._batch_size = batch_size
        self._application = LineIdentityManagementApplication(unit_of_work_factory, now)

    def run_once(self) -> int:
        items = self._claim()
        for item in items:
            self._process(item)
        return len(items)

    def _claim(self):
        query = ClaimLineOutboxQuery(
            self._worker_identity,
            self._now(),
            self._batch_size,
            IDENTITY_MENU_RESET_INTENT,
        )
        with self._unit_of_work_factory() as unit_of_work:
            items = unit_of_work.outbox.claim(query)
            unit_of_work.commit()
        return items

    def _process(self, item) -> None:
        try:
            payload = json.loads(item.payload_json)
            request_id = int(payload["request_id"])
            outcome = self._provider.link_to_user(
                str(payload["provider_menu_id"]),
                LineUserId(str(payload["line_user_id"])),
            )
            if outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS:
                self._application.finalize(request_id)
                self._complete(item)
                return
            self._fail(item, request_id, outcome)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._record_exception_failure(item, error, retryable=False)
        except Exception as error:
            self._record_exception_failure(item, error, retryable=True)

    def _fail(self, item, request_id: int, outcome) -> None:
        retryable = outcome.outcome_type in _RETRYABLE_OUTCOMES
        code = str(outcome.error_code or "line_identity_menu_reset_failed")
        message = str(outcome.error_message or "Rich Menu reset failed")[:1000]
        self._record_failure(item, request_id, code, message, retryable)

    def _record_exception_failure(self, item, error: Exception, *, retryable: bool) -> None:
        code = (
            "line_identity_menu_reset_unavailable"
            if retryable
            else "line_identity_menu_reset_payload_invalid"
        )
        try:
            request_id = int(item.aggregate_identity)
        except (TypeError, ValueError):
            self._complete(item, code, str(error)[:1000], retryable)
            return
        self._record_failure(item, request_id, code, str(error)[:1000], retryable)

    # Request failure state and outbox attempt must commit together.
    def _record_failure(
        self,
        item,
        request_id: int,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        terminal = not retryable or item.attempt_count + 1 >= item.maximum_attempts
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.identity_management.mark_failure(
                request_id,
                code,
                message,
                terminal=terminal,
            )
            unit_of_work.outbox.complete(
                CompleteLineOutboxCommand(
                    item,
                    self._now(),
                    code,
                    message,
                    retryable=retryable,
                )
            )
            unit_of_work.commit()

    def _complete(self, item, code=None, message=None, retryable=True) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.outbox.complete(
                CompleteLineOutboxCommand(
                    item,
                    self._now(),
                    code,
                    message,
                    retryable=retryable,
                )
            )
            unit_of_work.commit()


_RETRYABLE_OUTCOMES = {
    LineRichMenuProviderOutcomeType.RATE_LIMITED,
    LineRichMenuProviderOutcomeType.UNAVAILABLE,
    LineRichMenuProviderOutcomeType.TIMEOUT,
}


__all__ = ["LineIdentityRevocationWorker"]
