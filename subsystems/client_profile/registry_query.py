"""Case-centered client registry read composition contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol


ClientRegistrySortBy = Literal["case_no", "customer_name", "service_days", "expected_start_date"]
ClientRegistrySortOrder = Literal["asc", "desc"]


class ClientRegistryNotFound(LookupError):
    pass


class ClientRegistryContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ClientRegistrySummary:
    client_id: int
    case_no: str
    name: str | None
    phone: str | None
    city: str | None
    baby_info: str | None
    service_days: int | None
    requires_cooking: bool | None
    planned_start_date: object | None
    order_status: str | None


@dataclass(frozen=True, slots=True)
class ClientRegistryPage:
    items: tuple[ClientRegistrySummary, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class ClientRegistryClientProfile:
    client_id: int
    version: int
    values: Mapping[str, str | None]


@dataclass(frozen=True, slots=True)
class ClientRegistryBeClass:
    status: str
    record_id: int | None
    version: int | None
    values: Mapping[str, str | None] | None


@dataclass(frozen=True, slots=True)
class ClientRegistryDetail:
    case_no: str
    client: ClientRegistryClientProfile
    beclass: ClientRegistryBeClass


class ClientRegistryRepository(Protocol):
    def list_page(
        self,
        *,
        query: str | None,
        has_baby_info: bool | None,
        service_days: int | None,
        requires_cooking: bool | None,
        sort_by: ClientRegistrySortBy | None,
        sort_order: ClientRegistrySortOrder | None,
        limit: int,
        after: str | None,
    ) -> tuple[tuple[Mapping[str, Any], ...], str | None]: ...
    def load_detail(self, case_no: str) -> Mapping[str, Any] | None: ...


class ClientRegistryQueryApplication:
    def __init__(self, repository: ClientRegistryRepository) -> None:
        self._repository = repository

    def list(
        self,
        *,
        query: str | None,
        has_baby_info: bool | None = None,
        service_days: int | None = None,
        requires_cooking: bool | None = None,
        sort_by: ClientRegistrySortBy | None = None,
        sort_order: ClientRegistrySortOrder | None = None,
        limit: int,
        after: str | None,
    ) -> ClientRegistryPage:
        if limit < 1 or limit > 100:
            raise ValueError("client_registry_limit_invalid")
        normalized_query = _optional_text(query, 100)
        normalized_after = _optional_text(after, 50)
        normalized_has_baby_info = _optional_bool(has_baby_info, "client_registry_has_baby_info_invalid")
        normalized_service_days = _optional_positive_int(service_days, "client_registry_service_days_invalid")
        normalized_requires_cooking = _optional_bool(requires_cooking, "client_registry_requires_cooking_invalid")
        normalized_sort_by, normalized_sort_order = _normalize_sort(sort_by, sort_order)
        cursor_supported = (normalized_sort_by is None or normalized_sort_by == "case_no") and normalized_sort_order in {None, "asc"}
        if normalized_after is not None and not cursor_supported:
            raise ValueError("client_registry_cursor_sort_unsupported")
        rows, next_cursor = self._repository.list_page(
            query=normalized_query,
            has_baby_info=normalized_has_baby_info,
            service_days=normalized_service_days,
            requires_cooking=normalized_requires_cooking,
            sort_by=normalized_sort_by,
            sort_order=normalized_sort_order,
            limit=limit,
            after=normalized_after,
        )
        items = tuple(_summary(row) for row in rows)
        if cursor_supported and next_cursor is not None and (not items or next_cursor != items[-1].case_no):
            raise ClientRegistryContractError("client_registry_cursor_invalid")
        return ClientRegistryPage(items, next_cursor if cursor_supported else None)

    def query(self, case_no: str) -> ClientRegistryDetail:
        identity = _required_text(case_no, 50, "client_registry_case_no_invalid")
        row = self._repository.load_detail(identity)
        if row is None:
            raise ClientRegistryNotFound("client_registry_not_found")
        if str(row.get("case_no")) != identity:
            raise ClientRegistryContractError("client_registry_identity_mismatch")
        client_values = row.get("client_values")
        if not isinstance(client_values, Mapping):
            raise ClientRegistryContractError("client_registry_profile_invalid")
        beclass_status = str(row.get("beclass_status") or "")
        if beclass_status not in {"ready", "unbound", "duplicate_binding"}:
            raise ClientRegistryContractError("client_registry_beclass_status_invalid")
        beclass_values = row.get("beclass_values")
        if beclass_status == "ready" and not isinstance(beclass_values, Mapping):
            raise ClientRegistryContractError("client_registry_beclass_invalid")
        return ClientRegistryDetail(
            identity,
            ClientRegistryClientProfile(
                int(row["client_id"]),
                int(row.get("client_profile_version") or 0),
                {str(key): _nullable_text(value) for key, value in client_values.items()},
            ),
            ClientRegistryBeClass(
                beclass_status,
                int(row["beclass_record_id"]) if row.get("beclass_record_id") is not None else None,
                int(row.get("beclass_version") or 0) if beclass_status == "ready" else None,
                ({str(key): _nullable_text(value) for key, value in beclass_values.items()}
                 if isinstance(beclass_values, Mapping) else None),
            ),
        )


def _summary(row: Mapping[str, Any]) -> ClientRegistrySummary:
    client_id = row.get("client_id")
    if isinstance(client_id, bool) or not isinstance(client_id, int) or client_id <= 0:
        raise ClientRegistryContractError("client_registry_client_id_invalid")
    return ClientRegistrySummary(
        client_id,
        _required_text(row.get("case_no"), 50, "client_registry_case_no_invalid"),
        _nullable_text(row.get("name")),
        _nullable_text(row.get("phone")),
        _nullable_text(row.get("city")),
        _nullable_text(row.get("baby_info")),
        _nullable_positive_int(row.get("service_days"), "client_registry_summary_service_days_invalid"),
        _nullable_bool(row.get("requires_cooking"), "client_registry_summary_requires_cooking_invalid"),
        row.get("planned_start_date"),
        _nullable_text(row.get("order_status")),
    )


def _optional_text(value: object, maximum: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > maximum:
        raise ValueError("client_registry_query_invalid")
    return text


def _required_text(value: object, maximum: int, code: str) -> str:
    text = _optional_text(value, maximum)
    if text is None:
        raise ClientRegistryContractError(code)
    return text


def _nullable_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: object, code: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(code)


def _nullable_bool(value: object, code: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    raise ClientRegistryContractError(code)


def _optional_positive_int(value: object, code: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(code)
    return value


def _nullable_positive_int(value: object, code: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ClientRegistryContractError(code)
    return value


def _normalize_sort(
    sort_by: object,
    sort_order: object,
) -> tuple[ClientRegistrySortBy | None, ClientRegistrySortOrder | None]:
    if sort_by is None:
        if sort_order is not None:
            raise ValueError("client_registry_sort_order_without_field")
        return None, None
    if sort_by not in {"case_no", "customer_name", "service_days", "expected_start_date"}:
        raise ValueError("client_registry_sort_by_invalid")
    if sort_order is None:
        return sort_by, "asc"
    if sort_order not in {"asc", "desc"}:
        raise ValueError("client_registry_sort_order_invalid")
    return sort_by, sort_order


__all__ = [
    "ClientRegistryContractError",
    "ClientRegistryDetail",
    "ClientRegistryNotFound",
    "ClientRegistryPage",
    "ClientRegistryQueryApplication",
]
