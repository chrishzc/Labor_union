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
from subsystems.line.identity_management_contracts import LineIdentityRevocationStatus
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
            line_user_id = LineUserId(payload["line_user_id"])
            if str(request_id) != item.aggregate_identity:
                raise ValueError("LINE menu reset request mismatch")
        except (KeyError, TypeError, ValueError):
            with self._unit_of_work_factory() as unit_of_work:
                if unit_of_work.outbox.lock_menu_lease(item, self._now()):
                    unit_of_work.outbox.complete(CompleteLineOutboxCommand(
                        item, self._now(), "line_identity_menu_reset_payload_invalid",
                        "圖文選單回復工作資料無效", retryable=False,
                    ))
                    unit_of_work.commit()
            return
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.outbox.lock_menu_user(line_user_id)
            if not unit_of_work.outbox.lock_menu_lease(item, self._now()):
                return
            request = unit_of_work.identity_management.get_request(request_id, lock=True)
            if request.line_user_id != line_user_id:
                raise RuntimeError("line_identity_menu_reset_user_mismatch")
            command = CompleteLineOutboxCommand(item, self._now())
            if request.status is not LineIdentityRevocationStatus.COMPLETED:
                latest = unit_of_work.outbox.latest_menu_intent_id(line_user_id)
                if (
                    request.status is LineIdentityRevocationStatus.MANUAL_COMPLETED
                    and latest is not None and latest > item.outbox_id
                ):
                    command = CompleteLineOutboxCommand(
                        item, self._now(), "line_identity_menu_reset_superseded",
                        "已有較新的圖文選單切換工作", retryable=False,
                    )
                    self._record_failure(unit_of_work, request, command, terminal=True)
                else:
                    command = self._restore(
                        unit_of_work, item, request,
                        schedule_successor=latest is None or latest <= item.outbox_id,
                    )
            unit_of_work.outbox.complete(command)
            unit_of_work.commit()

    def _restore(self, unit_of_work, item, request, *, schedule_successor) -> CompleteLineOutboxCommand:
        outcome = self._provider.restore_default_for_user(request.line_user_id)
        if outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS:
            self._application.finalize_in_unit_of_work(
                unit_of_work, request, schedule_successor=schedule_successor,
            )
            return CompleteLineOutboxCommand(item, self._now())
        retryable = outcome.outcome_type in _RETRYABLE_OUTCOMES
        code = str(outcome.error_code or "line_identity_menu_reset_failed")
        message = str(outcome.error_message or "Rich Menu reset failed")[:1000]
        terminal = not retryable or item.attempt_count + 1 >= item.maximum_attempts
        command = CompleteLineOutboxCommand(item, self._now(), code, message, retryable=retryable)
        self._record_failure(unit_of_work, request, command, terminal=terminal)
        return command

    def _record_failure(self, unit_of_work, request, command, *, terminal):
        if request.status is LineIdentityRevocationStatus.MANUAL_COMPLETED:
            unit_of_work.identity_management.mark_manual_menu_repair_failure(
                request.request_id, command.error_code, command.error_message,
            )
        else:
            unit_of_work.identity_management.mark_failure(
                request.request_id, command.error_code, command.error_message, terminal=terminal,
            )


_RETRYABLE_OUTCOMES = {
    LineRichMenuProviderOutcomeType.RATE_LIMITED,
    LineRichMenuProviderOutcomeType.UNAVAILABLE,
    LineRichMenuProviderOutcomeType.TIMEOUT,
}


__all__ = ["LineIdentityRevocationWorker"]
