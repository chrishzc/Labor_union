"""Bounded, typed query contract for the Staff directory projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from shared_kernel.performance import MAXIMUM_PAGE_SIZE
from shared_kernel.validation import require_positive_integer


class StaffSummaryContractError(ValueError):
    """Raised when the Staff summary source violates its bounded contract."""


@dataclass(frozen=True, slots=True)
class StaffSummaryQueryRequest:
    page_size: int
    after_id: int | None = None
    staff_id: int | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.page_size, "staff summary page_size")
        if self.page_size > MAXIMUM_PAGE_SIZE:
            raise ValueError("staff summary page_size must not exceed 200")
        if self.after_id is not None:
            require_positive_integer(self.after_id, "staff summary after_id")
        if self.staff_id is not None:
            require_positive_integer(self.staff_id, "staff summary staff_id")
        if self.after_id is not None and self.staff_id is not None:
            raise ValueError("staff_id and after_id are mutually exclusive")


@dataclass(frozen=True, slots=True)
class StaffSummary:
    id: int
    name: str | None
    phone: str | None


@dataclass(frozen=True, slots=True)
class StaffSummaryPage:
    items: tuple[StaffSummary, ...]
    next_cursor: int | None


class StaffSummaryRepository(Protocol):
    def fetch_page(
        self,
        *,
        after_id: int | None,
        page_size: int,
        staff_id: int | None,
    ) -> tuple[Mapping[str, object], ...]: ...


class StaffSummaryQueryService:
    """Project the Staff-owned read model into a bounded typed page."""

    def __init__(self, repository: StaffSummaryRepository) -> None:
        self._repository = repository

    def query(self, request: StaffSummaryQueryRequest) -> StaffSummaryPage:
        rows = self._repository.fetch_page(
            after_id=request.after_id,
            page_size=request.page_size,
            staff_id=request.staff_id,
        )
        if not isinstance(rows, tuple):
            raise StaffSummaryContractError("repository page must be a tuple")
        if len(rows) > request.page_size + 1:
            raise StaffSummaryContractError("repository page exceeded page_size + 1")
        items = tuple(_summary_item(row) for row in rows[: request.page_size])
        if len({item.id for item in items}) != len(items):
            raise StaffSummaryContractError("repository page contains duplicate staff ids")
        next_cursor = (
            items[-1].id
            if request.staff_id is None and len(rows) > request.page_size
            else None
        )
        return StaffSummaryPage(items=items, next_cursor=next_cursor)


def _summary_item(row: object) -> StaffSummary:
    fields = {"id", "name", "phone"}
    if not isinstance(row, Mapping) or set(row) != fields:
        raise StaffSummaryContractError("repository row fields are not canonical")
    raw_id = row["id"]
    if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id <= 0:
        raise StaffSummaryContractError("repository row staff id is invalid")
    return StaffSummary(
        id=raw_id,
        name=_optional_text(row["name"], "staff name", 100),
        phone=_optional_text(row["phone"], "staff phone", 50),
    )


def _optional_text(value: object, label: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise StaffSummaryContractError(f"{label} is invalid")
    value = value.strip()
    if len(value) > maximum:
        raise StaffSummaryContractError(f"{label} exceeds maximum length")
    return value


class StaffSummaryQueryApplication:
    """Minimal application facade exposed to the HTTP adapter."""

    def __init__(self, service: StaffSummaryQueryService) -> None:
        self._service = service

    def query(self, request: StaffSummaryQueryRequest) -> StaffSummaryPage:
        return self._service.query(request)


__all__ = [
    "StaffSummary",
    "StaffSummaryContractError",
    "StaffSummaryPage",
    "StaffSummaryQueryApplication",
    "StaffSummaryQueryRequest",
    "StaffSummaryQueryService",
    "StaffSummaryRepository",
]
