"""Verified LIFF Query/Preview/Apply for manual customer order changes."""

from __future__ import annotations

from datetime import date, time
import hashlib
import json
from typing import Callable, Mapping, Protocol

from domains.customer_service.ticket import CustomerServiceCategory
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from shared_kernel.validation import require_canonical_text
from subsystems.customer_service.contracts import CreateCustomerServiceMessage
from subsystems.client_profile.contracts import ClientProfileBindingError
from subsystems.line.customer_order_change_contracts import (
    CustomerOrderChangeError,
    CustomerOrderChangeKind,
    CustomerOrderChangePreview,
    CustomerOrderChangeReceipt,
    CustomerOrderSnapshot,
)
from subsystems.line.ports import LineAuditIntent


class _CustomerOrderChangeUnitOfWork(Protocol):
    customer_order_changes: object
    customer_order_change_bindings: object
    customer_service: object
    audit: object

    def __enter__(self): ...
    def __exit__(self, exception_type, exception, traceback): ...
    def commit(self) -> None: ...


_ACTIVE_STATUSES = frozenset(
    {"待補件", "洽談中", "訂單成立", "服務中", "歷史訂單－未服務", "歷史訂單－服務中"}
)
_IMPACT_NOTES = {
    CustomerOrderChangeKind.SERVICE_ADDRESS: "服務地址可能影響交通、樓層費與月嫂接案意願。",
    CustomerOrderChangeKind.COOKING_REQUIREMENT: "下廚需求會改變服務內容，需由工會與月嫂確認。",
    CustomerOrderChangeKind.SERVICE_DAYS: "服務日期或天數可能影響費用、排班與月嫂檔期。",
    CustomerOrderChangeKind.DAILY_SERVICE_WINDOW: "每日服務時段需確認月嫂是否能配合。",
    CustomerOrderChangeKind.OTHER: "工會將依申請內容判定影響範圍並與您確認。",
}
_BEFORE_FIELDS = {
    CustomerOrderChangeKind.SERVICE_ADDRESS: (
        "service_city",
        "service_address",
        "residence_type",
    ),
    CustomerOrderChangeKind.COOKING_REQUIREMENT: ("requires_cooking",),
    CustomerOrderChangeKind.SERVICE_DAYS: ("start_date", "end_date", "service_days"),
    CustomerOrderChangeKind.DAILY_SERVICE_WINDOW: (
        "service_start_time",
        "service_end_time",
        "service_end_day_offset",
    ),
    CustomerOrderChangeKind.OTHER: (),
}


class CustomerOrderChangeApplication:
    def __init__(self, unit_of_work_factory: Callable[[], _CustomerOrderChangeUnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, applicant_identity: str, client_id: int) -> tuple[CustomerOrderSnapshot, ...]:
        with self._unit_of_work_factory() as unit_of_work:
            _read_binding(unit_of_work, applicant_identity, client_id)
            return tuple(
                item
                for item in unit_of_work.customer_order_changes.list_for_client(client_id)
                if item.status in _ACTIVE_STATUSES
            )

    def preview(
        self,
        applicant_identity: str,
        client_id: int,
        case_no: str,
        expected_order_version: int,
        kind: CustomerOrderChangeKind | str,
        requested: Mapping[str, object],
    ) -> CustomerOrderChangePreview:
        with self._unit_of_work_factory() as unit_of_work:
            _read_binding(unit_of_work, applicant_identity, client_id)
            snapshot = _require_snapshot(
                unit_of_work.customer_order_changes.load_for_client(client_id, case_no)
            )
        return _build_preview(
            applicant_identity,
            client_id,
            snapshot,
            expected_order_version,
            kind,
            requested,
        )

    def apply(
        self,
        applicant_identity: str,
        client_id: int,
        case_no: str,
        expected_order_version: int,
        kind: CustomerOrderChangeKind | str,
        requested: Mapping[str, object],
        preview_fingerprint: PreviewFingerprint,
        idempotency_key: IdempotencyKey,
    ) -> CustomerOrderChangeReceipt:
        event_key = _event_key(idempotency_key)
        with self._unit_of_work_factory() as unit_of_work:
            _read_binding(unit_of_work, applicant_identity, client_id, lock=True)
            snapshot = _require_snapshot(
                unit_of_work.customer_order_changes.load_for_client(
                    client_id, case_no, lock=True
                )
            )
            preview = _build_preview(
                applicant_identity,
                client_id,
                snapshot,
                expected_order_version,
                kind,
                requested,
            )
            if preview.preview_fingerprint != preview_fingerprint:
                raise CustomerOrderChangeError("order_change_preview_fingerprint_mismatch")
            message = _ticket_message(preview)
            existing_message = unit_of_work.customer_service.event_message(event_key)
            if existing_message is not None:
                if existing_message != message:
                    raise CustomerOrderChangeError(
                        "order_change_idempotency_key_reused_with_different_payload"
                    )
                ticket = unit_of_work.customer_service.get_by_event_key(event_key)
                if ticket is None:
                    raise CustomerOrderChangeError("order_change_replay_readback_missing")
                return _receipt(ticket, preview, idempotency_key, replayed=True)
            ticket = unit_of_work.customer_service.create_or_append(
                CreateCustomerServiceMessage(
                    applicant_identity,
                    CustomerServiceCategory.OTHER,
                    message,
                    event_key,
                    client_id=client_id,
                    case_no=preview.case_no,
                )
            )
            unit_of_work.audit.append(
                LineAuditIntent(
                    "customer_service.order_change.requested",
                    f"line:{applicant_identity}",
                    "order",
                    preview.case_no,
                )
            )
            unit_of_work.commit()
            return _receipt(ticket, preview, idempotency_key, replayed=False)


def _read_binding(unit_of_work, applicant_identity: str, client_id: int, *, lock: bool = False) -> None:
    try:
        evidence = unit_of_work.customer_order_change_bindings.read_current(
            applicant_identity, client_id=client_id, lock=lock
        )
    except ClientProfileBindingError as error:
        raise CustomerOrderChangeError(str(error)) from error
    if not evidence.complete or evidence.client_id != client_id:
        raise CustomerOrderChangeError("order_change_binding_evidence_incomplete")
    if {"customer", "staff"}.issubset(evidence.roles) and not evidence.legal_customer_staff_dual_role:
        raise CustomerOrderChangeError("order_change_binding_dual_role_not_legal")


def _require_snapshot(snapshot: CustomerOrderSnapshot | None) -> CustomerOrderSnapshot:
    if snapshot is None:
        raise CustomerOrderChangeError("order_change_order_not_found")
    if snapshot.status not in _ACTIVE_STATUSES:
        raise CustomerOrderChangeError("order_change_order_not_active")
    return snapshot


def _build_preview(
    applicant_identity: str,
    client_id: int,
    snapshot: CustomerOrderSnapshot,
    expected_order_version: int,
    kind: CustomerOrderChangeKind | str,
    requested: Mapping[str, object],
) -> CustomerOrderChangePreview:
    try:
        selected_kind = CustomerOrderChangeKind(kind)
    except (TypeError, ValueError) as error:
        raise CustomerOrderChangeError("order_change_kind_not_allowed") from error
    if snapshot.order_version != expected_order_version:
        raise CustomerOrderChangeError("order_change_order_version_stale")
    normalized = _normalize_requested(selected_kind, requested)
    before = {
        field: str(snapshot.values.get(field) or "未設定")
        for field in _BEFORE_FIELDS[selected_kind]
    }
    fingerprint = fingerprint_payload(
        {
            "family": "customer_order_change/v1",
            "applicant_identity": applicant_identity,
            "client_id": client_id,
            "case_no": snapshot.case_no,
            "order_version": snapshot.order_version,
            "client_profile_version": snapshot.client_profile_version,
            "kind": selected_kind.value,
            "before": before,
            "requested": normalized,
        }
    )
    return CustomerOrderChangePreview(
        snapshot.case_no,
        snapshot.status,
        snapshot.order_version,
        selected_kind,
        before,
        normalized,
        _IMPACT_NOTES[selected_kind],
        fingerprint,
    )


def _normalize_requested(
    kind: CustomerOrderChangeKind, requested: Mapping[str, object]
) -> dict[str, str]:
    if not isinstance(requested, Mapping):
        raise CustomerOrderChangeError("order_change_requested_invalid")
    allowlists = {
        CustomerOrderChangeKind.SERVICE_ADDRESS: {
            "service_city",
            "service_address",
            "residence_type",
            "floor_elevator_notes",
        },
        CustomerOrderChangeKind.COOKING_REQUIREMENT: {"requires_cooking", "cooking_notes"},
        CustomerOrderChangeKind.SERVICE_DAYS: {"start_date", "end_date", "service_days"},
        CustomerOrderChangeKind.DAILY_SERVICE_WINDOW: {
            "service_start_time",
            "service_end_time",
            "service_end_day_offset",
        },
        CustomerOrderChangeKind.OTHER: {"details"},
    }
    required = {
        CustomerOrderChangeKind.SERVICE_ADDRESS: {
            "service_city",
            "service_address",
            "residence_type",
        },
        CustomerOrderChangeKind.COOKING_REQUIREMENT: {"requires_cooking"},
        CustomerOrderChangeKind.SERVICE_DAYS: {"start_date", "end_date", "service_days"},
        CustomerOrderChangeKind.DAILY_SERVICE_WINDOW: {
            "service_start_time",
            "service_end_time",
            "service_end_day_offset",
        },
        CustomerOrderChangeKind.OTHER: {"details"},
    }
    keys = set(requested)
    if not required[kind].issubset(keys) or not keys.issubset(allowlists[kind]):
        raise CustomerOrderChangeError("order_change_requested_fields_invalid")
    result: dict[str, str] = {}
    for field, value in requested.items():
        if not isinstance(field, str) or not isinstance(value, str):
            raise CustomerOrderChangeError("order_change_requested_value_invalid")
        canonical = require_canonical_text(value, field, 1000)
        result[field] = canonical
    if kind is CustomerOrderChangeKind.SERVICE_ADDRESS:
        if len(result["service_city"]) > 20 or len(result["service_address"]) > 255:
            raise CustomerOrderChangeError("order_change_service_address_too_long")
        if len(result.get("floor_elevator_notes", "")) > 500:
            raise CustomerOrderChangeError("order_change_service_address_notes_too_long")
    if kind is CustomerOrderChangeKind.COOKING_REQUIREMENT:
        if result["requires_cooking"] not in {"需要", "不需要"}:
            raise CustomerOrderChangeError("order_change_cooking_requirement_invalid")
        if len(result.get("cooking_notes", "")) > 500:
            raise CustomerOrderChangeError("order_change_cooking_notes_too_long")
    if kind is CustomerOrderChangeKind.SERVICE_DAYS:
        try:
            start = date.fromisoformat(result["start_date"])
            end = date.fromisoformat(result["end_date"])
            days = int(result["service_days"])
        except (TypeError, ValueError) as error:
            raise CustomerOrderChangeError("order_change_service_days_invalid") from error
        if end < start or days <= 0:
            raise CustomerOrderChangeError("order_change_service_days_invalid")
        result["service_days"] = str(days)
    if kind is CustomerOrderChangeKind.DAILY_SERVICE_WINDOW:
        try:
            time.fromisoformat(result["service_start_time"])
            time.fromisoformat(result["service_end_time"])
        except ValueError as error:
            raise CustomerOrderChangeError("order_change_service_window_invalid") from error
        if result["service_end_day_offset"] not in {"0", "1"}:
            raise CustomerOrderChangeError("order_change_service_window_invalid")
    return {key: result[key] for key in sorted(result)}


def _ticket_message(preview: CustomerOrderChangePreview) -> str:
    labels = {
        CustomerOrderChangeKind.SERVICE_ADDRESS: "服務地址",
        CustomerOrderChangeKind.COOKING_REQUIREMENT: "下廚需求",
        CustomerOrderChangeKind.SERVICE_DAYS: "服務日期／天數",
        CustomerOrderChangeKind.DAILY_SERVICE_WINDOW: "每日服務時段",
        CustomerOrderChangeKind.OTHER: "其他訂單內容",
    }
    detail = json.dumps(dict(preview.requested), ensure_ascii=False, sort_keys=True)
    before = json.dumps(dict(preview.before), ensure_ascii=False, sort_keys=True)
    return (
        f"[訂單異動申請]\n案件：{preview.case_no}\n項目：{labels[preview.kind]}\n"
        f"目前內容：{before}\n申請內容：{detail}\n"
        "狀態：待工會確認；尚未修改正式訂單。"
    )


def _event_key(idempotency_key: IdempotencyKey) -> str:
    digest = hashlib.sha256(idempotency_key.value.encode("utf-8")).hexdigest()
    return f"line-order-change:{digest}"


def _receipt(ticket, preview, idempotency_key, *, replayed):
    return CustomerOrderChangeReceipt(
        int(ticket.ticket_id),
        ticket.status.value,
        preview.case_no,
        preview.kind,
        idempotency_key.value,
        replayed,
    )


__all__ = ["CustomerOrderChangeApplication"]
