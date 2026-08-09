"""Validated inputs and outputs for privacy-safe administrator audit access."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AdminAuditListItem(BaseModel):
    id: int
    admin_user_id: int | None
    actor_display_name: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    request_path: str | None = None
    http_method: str | None = None
    result_status: int | None = None
    ip_address_masked: str | None = None
    created_at: datetime


class AdminAuditDetail(AdminAuditListItem):
    details: dict[str, Any] | list[Any] | str | int | float | bool | None = None


class AdminAuditPage(BaseModel):
    items: list[AdminAuditListItem]
    page: int
    page_size: int
    total: int
    total_pages: int
