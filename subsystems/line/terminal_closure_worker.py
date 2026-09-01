"""Consume Orders terminal-closure handoffs in the canonical LINE worker."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from subsystems.line.terminal_closure_application import consume_terminal_closure


class LineTerminalClosureWorker:
    """Bridge the read-only Orders outbox to the LINE Identity consumer.

    Orders remains the source owner and is never acknowledged or mutated here.
    A successful/no-op decision is durably deduplicated by the LINE receipt
    written by ``consume_terminal_closure``; the source row therefore remains
    readable for reconciliation and safe replay.
    """

    def __init__(
        self,
        unit_of_work_factory: Callable[[], object],
        worker_identity: str,
        now: Callable[[], datetime],
        *,
        batch_size: int = 25,
    ) -> None:
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= 100:
            raise ValueError("terminal closure worker batch size is invalid")
        self._unit_of_work_factory = unit_of_work_factory
        self._worker_identity = worker_identity
        self._now = now
        self._batch_size = batch_size

    def run_once(self) -> int:
        """Consume one bounded batch of committed Orders handoffs."""

        with self._unit_of_work_factory() as unit_of_work:
            source = getattr(unit_of_work, "orders_terminal_closure_source", None)
            if source is None:
                return 0
            pending = source.list_pending(limit=self._batch_size)

        processed = 0
        for _source_row_id, event in pending:
            consume_terminal_closure(self._unit_of_work_factory, event)
            processed += 1
        return processed


__all__ = ["LineTerminalClosureWorker"]
