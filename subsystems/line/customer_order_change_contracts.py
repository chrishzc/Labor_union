"""Typed contracts for customer-facing LINE order-change intake."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from domains.orders.order_change_request import CustomerOrderChangeError, CustomerOrderChangeKind, OrderChangeRequestStatus
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.orders.order_change_requests import OrderChangeRequestStore


@dataclass(frozen=True, slots=True)
class CustomerOrderSnapshot:
    case_no: str
    status: str
    order_version: int
    client_profile_version: int
    values: Mapping[str, str]


class CustomerOrderChangeRepository(OrderChangeRequestStore, Protocol):
    def list_for_client(self, client_id: int) -> tuple[CustomerOrderSnapshot, ...]: ...

    def load_for_client(
        self, client_id: int, case_no: str, *, lock: bool = False
    ) -> CustomerOrderSnapshot | None: ...


@dataclass(frozen=True, slots=True)
class CustomerOrderChangePreview:
    case_no: str
    status: str
    order_version: int
    kind: CustomerOrderChangeKind
    before: Mapping[str, str]
    requested: Mapping[str, str]
    impact_note: str
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class CustomerOrderChangeReceipt:
    request_id: int
    request_status: OrderChangeRequestStatus
    case_no: str
    kind: CustomerOrderChangeKind
    idempotency_key: str
    replayed: bool


__all__ = [
    "CustomerOrderChangeError",
    "CustomerOrderChangeKind",
    "CustomerOrderChangePreview",
    "CustomerOrderChangeReceipt",
    "CustomerOrderChangeRepository",
    "CustomerOrderSnapshot",
]
