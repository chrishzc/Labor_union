"""Pure customer-service ticket categories and transitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CustomerServiceCategory(StrEnum):
    SERVICE_FLOW = "service_flow"
    PAYMENT_SUBSIDY = "payment_subsidy"
    SERVICE_PROGRESS = "service_progress"
    PROFILE_UPDATE = "profile_update"
    CONTACT_UNION = "contact_union"
    OTHER = "other"


class CustomerServiceStatus(StrEnum):
    WAITING = "waiting"
    HANDLING = "handling"
    RESOLVED = "resolved"


_ALLOWED_TRANSITIONS = {
    CustomerServiceStatus.WAITING: {CustomerServiceStatus.HANDLING, CustomerServiceStatus.RESOLVED},
    CustomerServiceStatus.HANDLING: {CustomerServiceStatus.RESOLVED},
    CustomerServiceStatus.RESOLVED: {CustomerServiceStatus.HANDLING},
}


class CustomerServiceTransitionError(ValueError):
    """Raised when a ticket status transition violates the state machine."""


class CustomerServiceTicketNotFoundError(LookupError):
    """Raised when a requested customer-service ticket does not exist."""


class CustomerServiceVersionConflictError(RuntimeError):
    """Raised when a ticket mutation observes a stale version."""


@dataclass(frozen=True, slots=True)
class CustomerServiceTicket:
    ticket_id: int
    line_user_id: str
    category: CustomerServiceCategory
    status: CustomerServiceStatus
    version: int
    client_id: int | None = None
    case_no: str | None = None
    client_name: str | None = None
    client_phone: str | None = None
    assigned_admin_user_id: int | None = None
    internal_note: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def transition_ticket(
    current: CustomerServiceStatus,
    target: CustomerServiceStatus,
) -> CustomerServiceStatus:
    if current == target:
        return current
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise CustomerServiceTransitionError(
            f"cannot transition customer-service ticket from {current.value} to {target.value}"
        )
    return target


__all__ = [
    "CustomerServiceCategory",
    "CustomerServiceStatus",
    "CustomerServiceTicket",
    "CustomerServiceTicketNotFoundError",
    "CustomerServiceTransitionError",
    "CustomerServiceVersionConflictError",
    "transition_ticket",
]
