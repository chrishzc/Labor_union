"""Typed bounded client for the Customer Service domain."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError


class CustomerServiceTicketView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: int
    line_user_id_masked: str
    category: str
    status: str
    version: int
    client_id: int | None = None
    case_no: str | None = None
    client_name: str | None = None
    client_phone: str | None = None
    assigned_admin_user_id: int | None = None
    internal_note: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CustomerServiceEventView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    event_type: str
    message_text: str | None = None
    actor_id: str
    created_at: datetime


class CustomerServiceDetailView(BaseModel):
    ticket: CustomerServiceTicketView
    events: list[CustomerServiceEventView]


class CustomerServicePageView(BaseModel):
    items: list[CustomerServiceTicketView]
    total: int
    page: int
    page_size: int


class CustomerServiceSummaryView(BaseModel):
    waiting: int
    handling: int
    resolved_today: int


class CustomerServiceApiClient:
    def __init__(self, transport: LineAdminApiClient) -> None:
        self._transport = transport

    def summary(self, token: str | None) -> CustomerServiceSummaryView:
        return self._parse(CustomerServiceSummaryView, self._get(token, "/api/v1/customer-service/tickets/summary"))

    def tickets(self, token: str | None, filters: dict[str, Any]) -> CustomerServicePageView:
        params = {key: value for key, value in filters.items() if value not in {None, ""}}
        return self._parse(CustomerServicePageView, self._get(token, "/api/v1/customer-service/tickets", params))

    def detail(self, token: str | None, ticket_id: int) -> CustomerServiceDetailView:
        return self._parse(CustomerServiceDetailView, self._get(token, f"/api/v1/customer-service/tickets/{ticket_id}"))

    def update(self, token: str | None, ticket_id: int, payload: dict[str, Any]) -> CustomerServiceDetailView:
        data = self._transport.request("PATCH", f"/api/v1/customer-service/tickets/{ticket_id}", token=token, json=payload)
        return self._parse(CustomerServiceDetailView, data)

    def reply(self, token: str | None, ticket_id: int, payload: dict[str, Any]) -> CustomerServiceDetailView:
        data = self._transport.request("POST", f"/api/v1/customer-service/tickets/{ticket_id}/reply", token=token, json=payload)
        return self._parse(CustomerServiceDetailView, data)

    def _get(self, token, path, params=None):
        return self._transport.request("GET", path, token=token, params=params)

    @staticmethod
    def _parse(model_type, payload):
        try:
            return model_type.model_validate(payload)
        except ValidationError as error:
            raise LineAdminApiError("客服 API 回傳格式不符合契約", category="schema", code="customer_service_response_invalid") from error


__all__ = ["CustomerServiceApiClient", "CustomerServiceDetailView", "CustomerServicePageView", "CustomerServiceSummaryView", "CustomerServiceTicketView"]
