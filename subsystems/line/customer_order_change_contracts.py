"""Typed contracts for customer-facing LINE order-change intake."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Protocol

from shared_kernel.fingerprints import PreviewFingerprint


class CustomerOrderChangeKind(StrEnum):
    SERVICE_ADDRESS = "service_address"
    COOKING_REQUIREMENT = "cooking_requirement"
    SERVICE_DAYS = "service_days"
    DAILY_SERVICE_WINDOW = "daily_service_window"
    OTHER = "other"


class CustomerOrderChangeError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CustomerOrderSnapshot:
    case_no: str
    status: str
    order_version: int
    client_profile_version: int
    values: Mapping[str, str]


class CustomerOrderChangeRepository(Protocol):
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
    ticket_id: int
    ticket_status: str
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
