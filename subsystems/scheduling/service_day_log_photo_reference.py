"""Scheduling-owned submitted photo references, distinct from provider delivery."""
from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SubmittedServiceDayLogPhoto:
    """An existing immutable owner submission, never a LINE delivery receipt."""

    file_id: str
    version: int
    sha256_digest: str
    size_bytes: int
    mime_type: str
    case_no: str
    attachment_kind: str
    log_id: int
    attachment_id: int
    assignment_id: int
    staff_id: int
    service_date: date

    @property
    def owner_submission_reference(self) -> str:
        return f"scheduling-service-day-log:{self.log_id}"


class SubmittedServiceDayLogPhotoPort(Protocol):
    def get_submitted_photo_reference(self, file_id: str) -> SubmittedServiceDayLogPhoto | None: ...
