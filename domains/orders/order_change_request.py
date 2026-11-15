"""Orders-owned application state for a customer-requested change."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping


class CustomerOrderChangeKind(StrEnum):
    SERVICE_ADDRESS = "service_address"
    COOKING_REQUIREMENT = "cooking_requirement"
    SERVICE_DAYS = "service_days"
    DAILY_SERVICE_WINDOW = "daily_service_window"
    OTHER = "other"


class OrderChangeRequestStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


class CustomerOrderChangeError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class NewOrderChangeRequest:
    client_id: int
    case_no: str
    kind: CustomerOrderChangeKind
    before: Mapping[str, str]
    requested: Mapping[str, str]
    idempotency_digest: str
    command_fingerprint: str


@dataclass(frozen=True, slots=True)
class OrderChangeCompletion:
    result: str
    actor_id: int
    actor_name: str
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class OrderChangeRequest:
    request_id: int
    case_no: str
    kind: CustomerOrderChangeKind
    before: Mapping[str, str]
    requested: Mapping[str, str]
    submitted_at: datetime
    command_fingerprint: str
    completion: OrderChangeCompletion | None

    @property
    def status(self) -> OrderChangeRequestStatus:
        return OrderChangeRequestStatus.COMPLETED if self.completion else OrderChangeRequestStatus.PENDING

    @property
    def version(self) -> int:
        return int(self.completion is not None)

    def check_completion(self, version: int, result: str, actor_id: int) -> bool:
        """Return false for an exact replay, and reject stale competing decisions."""
        if self.completion and version == 0:
            if self.completion.result == result and self.completion.actor_id == actor_id:
                return False
        if version != self.version:
            raise CustomerOrderChangeError("order_change_request_version_stale")
        if self.completion is not None:
            raise CustomerOrderChangeError("order_change_request_already_completed")
        return True
