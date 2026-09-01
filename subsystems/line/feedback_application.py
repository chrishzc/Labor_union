"""M2 feedback owner orchestration over the existing LINE outer UoW."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Protocol

from domains.customer_service.ticket import CustomerServiceCategory
from shared_kernel.identities import IdempotencyReceipt
from subsystems.customer_service.contracts import CreateCustomerServiceMessage
from subsystems.line.feedback_contracts import (
    FeedbackAggregate,
    FeedbackOutcome,
    FeedbackPreview,
    FeedbackReceipt,
    FeedbackReadback,
    FeedbackRoot,
    LineFeedbackRepository,
    RecordLineFeedback,
)


class FeedbackConflictError(ValueError):
    """The same actor/source already has a different terminal outcome."""


class FeedbackUnitOfWork(Protocol):
    feedback: LineFeedbackRepository
    receipts: object
    customer_service: object

    def __enter__(self): ...
    def __exit__(self, exception_type, exception, traceback): ...
    def commit(self) -> None: ...


class LineFeedbackApplication:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], FeedbackUnitOfWork],
        now: Callable[[], datetime],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now

    def preview(self, command: RecordLineFeedback) -> FeedbackPreview:
        return FeedbackPreview(
            command.source_response_id,
            command.outcome,
            command.command_fingerprint,
        )

    def apply(self, command: RecordLineFeedback) -> FeedbackReadback:
        fingerprint = command.command_fingerprint
        with self._unit_of_work_factory() as unit_of_work:
            existing_receipt = unit_of_work.receipts.get(command.idempotency_key)
            if existing_receipt is not None and existing_receipt.payload_fingerprint != fingerprint:
                raise FeedbackConflictError("feedback_idempotency_conflict")
            existing = unit_of_work.feedback.get(command.actor_id, command.source_response_id)
            if existing is not None:
                if existing.command_fingerprint != fingerprint or existing.outcome is not command.outcome:
                    raise FeedbackConflictError("feedback_terminal_decision_conflict")
                if existing_receipt is None:
                    unit_of_work.receipts.append(
                        IdempotencyReceipt(
                            command.idempotency_key,
                            fingerprint,
                            _receipt_reference(existing),
                        )
                    )
                    unit_of_work.commit()
                return _readback(existing, replayed=True)

            ticket_id = None
            if command.outcome is FeedbackOutcome.UNRESOLVED:
                ticket = unit_of_work.customer_service.create_or_append(
                    CreateCustomerServiceMessage(
                        line_user_id=command.actor_id,
                        category=CustomerServiceCategory.OTHER,
                        message="LINE 回覆未解決，請客服協助。",
                        event_key=f"line-feedback-ticket:{command.source_response_id}",
                    )
                )
                ticket_id = int(ticket.ticket_id)
            root = FeedbackRoot(
                actor_id=command.actor_id,
                source_response_id=command.source_response_id,
                outcome=command.outcome,
                binding_version=command.binding_version,
                response_revision=command.response_revision,
                catalog_revision=command.catalog_revision,
                rule_revision=command.rule_revision,
                command_fingerprint=fingerprint,
                ticket_id=ticket_id,
                idempotency_key=command.idempotency_key,
                correlation_id=command.correlation_id,
                occurred_at=self._now(),
            )
            unit_of_work.feedback.append(root)
            unit_of_work.receipts.append(
                IdempotencyReceipt(command.idempotency_key, fingerprint, _receipt_reference(root))
            )
            unit_of_work.commit()
        return _readback(root, replayed=False)

    def query(self, actor_id: str, source_response_id: str) -> FeedbackReadback | None:
        """Return the actor-scoped immutable root and its receipt readback."""
        with self._unit_of_work_factory() as unit_of_work:
            root = unit_of_work.feedback.get(actor_id, source_response_id)
        if root is None:
            return None
        return _readback(root, replayed=True)

    def aggregate(
        self, catalog_revision: int, window_start: datetime, window_end: datetime
    ) -> FeedbackAggregate:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.feedback.aggregate(catalog_revision, window_start, window_end)


def _receipt_reference(root: FeedbackRoot) -> str:
    return f"line-feedback:{root.actor_id}:{root.source_response_id}"


def _readback(root: FeedbackRoot, *, replayed: bool) -> FeedbackReadback:
    return FeedbackReadback(
        root,
        FeedbackReceipt(
            root.source_response_id,
            root.outcome,
            root.command_fingerprint,
            root.ticket_id,
            replayed,
        ),
    )


__all__ = ["FeedbackConflictError", "LineFeedbackApplication"]
