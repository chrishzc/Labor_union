"""Orders application for manual tracking and completion of change requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal, Protocol

from domains.orders.order_change_request import (
    CustomerOrderChangeError,
    NewOrderChangeRequest,
    OrderChangeRequest,
)
from shared_kernel.validation import require_canonical_text


class OrderChangeRequestStore(Protocol):
    def find_submission(self, client_id: int, idempotency_digest: str) -> OrderChangeRequest | None: ...
    def create_request(self, command: NewOrderChangeRequest) -> OrderChangeRequest: ...
    def list_requests(
        self, *, case_no: str | None, pending_only: bool, before_id: int | None, limit: int
    ) -> tuple[OrderChangeRequest, ...]: ...
    def load_request(self, request_id: int, *, lock: bool = False) -> OrderChangeRequest | None: ...
    def complete_request(
        self, request_id: int, *, result: str, actor_id: int, actor_name: str
    ) -> OrderChangeRequest: ...
    def list_legacy_requests(
        self, case_no: str, *, before_event_id: int | None, limit: int
    ) -> tuple[LegacyOrderChangeReference, ...]: ...


class _UnitOfWork(Protocol):
    customer_order_changes: OrderChangeRequestStore

    def __enter__(self): ...
    def __exit__(self, exception_type, exception, traceback): ...
    def commit(self) -> None: ...


@dataclass(frozen=True, slots=True)
class OrderChangeRequestPage:
    items: tuple[OrderChangeRequest, ...]
    next_before_id: int | None


@dataclass(frozen=True, slots=True)
class LegacyOrderChangeReference:
    event_id: int
    ticket_id: int
    ticket_status: Literal["waiting", "handling", "resolved"]
    submitted_at: datetime


def prior_submission(
    store: OrderChangeRequestStore,
    client_id: int,
    idempotency_digest: str,
    command_fingerprint: str,
) -> OrderChangeRequest | None:
    existing = store.find_submission(client_id, idempotency_digest)
    if existing is not None and existing.command_fingerprint != command_fingerprint:
        raise CustomerOrderChangeError("order_change_idempotency_key_reused_with_different_payload")
    return existing


def record_order_change_request(
    store: OrderChangeRequestStore, command: NewOrderChangeRequest
) -> OrderChangeRequest:
    observed = store.create_request(command)
    if (
        observed.case_no != command.case_no
        or observed.kind is not command.kind
        or observed.command_fingerprint != command.command_fingerprint
        or observed.completion is not None
    ):
        raise CustomerOrderChangeError("order_change_write_readback_mismatch")
    return observed


class OrderChangeRequestsApplication:
    def __init__(self, unit_of_work_factory: Callable[[], _UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def list(
        self, *, case_no: str | None, before_id: int | None, page_size: int
    ) -> OrderChangeRequestPage:
        with self._unit_of_work_factory() as unit:
            items = unit.customer_order_changes.list_requests(
                case_no=case_no, pending_only=case_no is None, before_id=before_id, limit=page_size + 1
            )
        next_before_id = items[page_size - 1].request_id if len(items) > page_size else None
        return OrderChangeRequestPage(items[:page_size], next_before_id)

    def complete(
        self, request_id: int, expected_version: int, result: str, actor_id: int, actor_name: str
    ) -> OrderChangeRequest:
        canonical_result = require_canonical_text(result, "result", 1000)
        if not canonical_result:
            raise CustomerOrderChangeError("order_change_result_required")
        with self._unit_of_work_factory() as unit:
            store = unit.customer_order_changes
            current = store.load_request(request_id, lock=True)
            if current is None:
                raise CustomerOrderChangeError("order_change_request_not_found")
            if not current.check_completion(expected_version, canonical_result, actor_id):
                return current
            observed = store.complete_request(
                request_id, result=canonical_result, actor_id=actor_id, actor_name=actor_name
            )
            completion = observed.completion
            if (
                observed.request_id != request_id
                or completion is None
                or completion.result != canonical_result
                or completion.actor_id != actor_id
            ):
                raise CustomerOrderChangeError("order_change_write_readback_mismatch")
            unit.commit()
            return observed

    def legacy_references(
        self, case_no: str, before_event_id: int | None, page_size: int
    ) -> tuple[tuple[LegacyOrderChangeReference, ...], int | None]:
        with self._unit_of_work_factory() as unit:
            items = unit.customer_order_changes.list_legacy_requests(
                case_no, before_event_id=before_event_id, limit=page_size + 1
            )
        next_before_id = items[page_size - 1].event_id if len(items) > page_size else None
        return items[:page_size], next_before_id
