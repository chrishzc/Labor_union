"""Registry-based dispatch for claimed canonical LINE webhook events."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

from domains.line.webhook import LineWebhookInboxSnapshot
from subsystems.line.ports import LineUnitOfWorkPort


class LineEventDispatchStatus(StrEnum):
    PROCESSED = "processed"
    IGNORED = "ignored"


@dataclass(frozen=True, slots=True)
class LineEventDispatchResult:
    status: LineEventDispatchStatus


LineEventHandler = Callable[
    [LineWebhookInboxSnapshot, LineUnitOfWorkPort],
    None,
]


class LineEventDispatcher:
    def __init__(self, handlers: dict[str, LineEventHandler] | None = None) -> None:
        self._handlers = dict(handlers or {})

    def dispatch(
        self,
        event: LineWebhookInboxSnapshot,
        unit_of_work: LineUnitOfWorkPort,
    ) -> LineEventDispatchResult:
        handler = self._handlers.get(event.event.event_type)
        if handler is None:
            return LineEventDispatchResult(LineEventDispatchStatus.IGNORED)
        handler(event, unit_of_work)
        return LineEventDispatchResult(LineEventDispatchStatus.PROCESSED)


__all__ = [
    "LineEventDispatchResult",
    "LineEventDispatchStatus",
    "LineEventDispatcher",
    "LineEventHandler",
]
