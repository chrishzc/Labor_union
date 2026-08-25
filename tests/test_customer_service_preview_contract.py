"""
File: test_customer_service_preview_contract.py
Description: 驗證客服結案 Preview／Apply 的零寫入、fresh lock、fingerprint、冪等、稽核與無 LINE 投遞。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from pymysql.err import OperationalError

from api.routes.customer_service import _call_update_endpoint
from api.schemas.customer_service import (
    CustomerServiceUpdateApplyRequest,
    CustomerServiceUpdatePreviewRequest,
)
from domains.customer_service.ticket import (
    CustomerServiceCategory,
    CustomerServiceStatus,
    CustomerServiceTicket,
)
from infrastructure.mysql.customer_service_repository import (
    CustomerServiceTicketNotFoundError,
    CustomerServiceVersionConflictError,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.customer_service.application import (
    CustomerServiceApplication,
    CustomerServiceIdempotencyMismatchError,
    CustomerServicePreviewFingerprintConflictError,
)
from subsystems.customer_service.contracts import (
    ApplyCustomerServiceTicketUpdate,
    PreviewCustomerServiceTicketUpdate,
)


def _ticket(
    *,
    status: CustomerServiceStatus = CustomerServiceStatus.HANDLING,
    version: int = 3,
) -> CustomerServiceTicket:
    now = datetime(2026, 8, 16, tzinfo=timezone.utc)
    return CustomerServiceTicket(
        ticket_id=41,
        line_user_id="U-test-only-41",
        category=CustomerServiceCategory.CONTACT_UNION,
        status=status,
        version=version,
        created_at=now,
        updated_at=now,
    )


class _CustomerServiceRepository:
    def __init__(self, ticket: CustomerServiceTicket) -> None:
        self.ticket = ticket
        self.get_locks: list[bool] = []
        self.events: list[tuple] = []
        self.updates: list[tuple] = []
        self.update_error: Exception | None = None

    def get(self, ticket_id: int, *, lock: bool = False):
        self.get_locks.append(lock)
        if ticket_id != self.ticket.ticket_id:
            raise CustomerServiceTicketNotFoundError("missing")
        return self.ticket

    def append_management_event(self, *values) -> None:
        self.events.append(values)

    def update(self, ticket_id, current_version, status, note, admin_user_id):
        self.updates.append(
            (ticket_id, current_version, status, note, admin_user_id)
        )
        if self.update_error is not None:
            raise self.update_error
        if current_version != self.ticket.version:
            raise CustomerServiceVersionConflictError("stale")
        self.ticket = replace(
            self.ticket,
            status=status,
            version=self.ticket.version + 1,
            internal_note=note,
            assigned_admin_user_id=admin_user_id,
        )
        return self.ticket

    def detail(self, ticket_id: int):
        if ticket_id != self.ticket.ticket_id:
            raise CustomerServiceTicketNotFoundError("missing")
        return {
            "ticket": {
                "ticket_id": self.ticket.ticket_id,
                "line_user_id_masked": "U-te…y-41",
                "category": self.ticket.category.value,
                "status": self.ticket.status.value,
                "version": self.ticket.version,
                "client_id": None,
                "case_no": None,
                "client_name": None,
                "client_phone": None,
                "assigned_admin_user_id": self.ticket.assigned_admin_user_id,
                "internal_note": self.ticket.internal_note,
                "created_at": self.ticket.created_at,
                "updated_at": self.ticket.updated_at,
            },
            "events": [],
        }


class _Receipts:
    def __init__(self) -> None:
        self.items = {}

    def get(self, key):
        return self.items.get(key.value)

    def append(self, receipt) -> None:
        self.items[receipt.key.value] = receipt


class _Audit:
    def __init__(self) -> None:
        self.items = []

    def append(self, intent) -> None:
        self.items.append(intent)


class _DeliveryTasks:
    def __init__(self) -> None:
        self.requests = []

    def enqueue(self, request) -> None:
        self.requests.append(request)


class _UnitOfWork:
    def __init__(self, repository, receipts, audit, delivery_tasks) -> None:
        self.customer_service = repository
        self.receipts = receipts
        self.audit = audit
        self.delivery_tasks = delivery_tasks
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is not None or not self.committed:
            self.rolled_back = True
        return False

    def commit(self) -> None:
        self.committed = True


class _Fixture:
    def __init__(self, ticket: CustomerServiceTicket | None = None) -> None:
        self.repository = _CustomerServiceRepository(ticket or _ticket())
        self.receipts = _Receipts()
        self.audit = _Audit()
        self.delivery_tasks = _DeliveryTasks()
        self.units: list[_UnitOfWork] = []
        self.application = CustomerServiceApplication(self.unit_of_work)

    def unit_of_work(self):
        unit = _UnitOfWork(
            self.repository,
            self.receipts,
            self.audit,
            self.delivery_tasks,
        )
        self.units.append(unit)
        return unit


def _preview_command(note: str | None = "  已完成  "):
    return PreviewCustomerServiceTicketUpdate(
        41,
        CustomerServiceStatus.RESOLVED,
        note,
        ExpectedVersion(3),
        CorrelationId("customer-preview-41"),
    )


def _apply_command(
    fingerprint: PreviewFingerprint,
    *,
    note: str | None = "  已完成  ",
    key: str = "customer-apply-41",
):
    return ApplyCustomerServiceTicketUpdate(
        41,
        CustomerServiceStatus.RESOLVED,
        note,
        ExpectedVersion(3),
        fingerprint,
        "admin:7",
        IdempotencyKey(key),
        CorrelationId("customer-apply-correlation-41"),
    )


def test_preview_is_zero_write_and_uses_the_frozen_candidate_payload():
    fixture = _Fixture()

    preview = fixture.application.preview_update(_preview_command())

    assert preview.before_status is CustomerServiceStatus.HANDLING
    assert preview.after_status is CustomerServiceStatus.RESOLVED
    assert preview.current_version == 3
    assert preview.expected_version == 3
    assert preview.blockers == ()
    assert preview.apply_ready is True
    assert preview.preview_fingerprint == fingerprint_payload(
        {
            "ticket_id": 41,
            "status": "resolved",
            "normalized_internal_note": "已完成",
            "current_status": "handling",
            "current_version": 3,
        }
    )
    assert fixture.repository.get_locks == [False]
    assert fixture.repository.events == []
    assert fixture.repository.updates == []
    assert fixture.receipts.items == {}
    assert fixture.audit.items == []
    assert fixture.delivery_tasks.requests == []
    assert fixture.units[-1].committed is False
    assert fixture.units[-1].rolled_back is True


def test_apply_fresh_locks_then_commits_event_receipt_and_audit_without_delivery():
    fixture = _Fixture()
    preview = fixture.application.preview_update(_preview_command())

    receipt = fixture.application.apply_update(
        _apply_command(preview.preview_fingerprint)
    )

    assert receipt.resulting_status is CustomerServiceStatus.RESOLVED
    assert receipt.resulting_version == 4
    assert receipt.replayed is False
    assert receipt.readback["ticket"]["status"] == "resolved"
    assert receipt.readback["ticket"]["version"] == 4
    assert fixture.repository.get_locks[-1] is True
    assert len(fixture.repository.events) == 1
    assert fixture.repository.updates == [
        (41, 3, CustomerServiceStatus.RESOLVED, "已完成", 7)
    ]
    receipt = fixture.receipts.items["customer-apply-41"]
    assert receipt.payload_fingerprint == preview.preview_fingerprint
    assert receipt.result_reference == "customer-service-ticket:41:handling:3"
    assert fixture.audit.items[0].action == "customer_service.ticket.update.apply"
    assert fixture.delivery_tasks.requests == []
    assert fixture.units[-1].committed is True
    assert fixture.units[-1].rolled_back is False


def test_apply_replays_same_payload_without_a_second_write():
    fixture = _Fixture()
    preview = fixture.application.preview_update(_preview_command())
    command = _apply_command(preview.preview_fingerprint)
    fixture.application.apply_update(command)
    event_count = len(fixture.repository.events)
    update_count = len(fixture.repository.updates)
    audit_count = len(fixture.audit.items)

    replay = fixture.application.apply_update(command)

    assert replay.resulting_status is CustomerServiceStatus.RESOLVED
    assert replay.resulting_version == 4
    assert replay.replayed is True
    assert replay.readback["ticket"]["version"] == 4
    assert len(fixture.repository.events) == event_count
    assert len(fixture.repository.updates) == update_count
    assert len(fixture.audit.items) == audit_count
    assert fixture.delivery_tasks.requests == []
    assert fixture.units[-1].committed is False
    assert fixture.units[-1].rolled_back is True


def test_same_idempotency_key_with_changed_note_is_rejected_without_writes():
    fixture = _Fixture()
    preview = fixture.application.preview_update(_preview_command())
    fixture.application.apply_update(_apply_command(preview.preview_fingerprint))
    event_count = len(fixture.repository.events)

    with pytest.raises(CustomerServiceIdempotencyMismatchError):
        fixture.application.apply_update(
            _apply_command(preview.preview_fingerprint, note="不同內容")
        )

    assert len(fixture.repository.events) == event_count
    assert fixture.delivery_tasks.requests == []
    assert fixture.units[-1].committed is False
    assert fixture.units[-1].rolled_back is True


def test_stale_version_is_a_zero_write_conflict():
    fixture = _Fixture(_ticket(version=4))
    candidate = fingerprint_payload(
        {
            "ticket_id": 41,
            "status": "resolved",
            "normalized_internal_note": "已完成",
            "current_status": "handling",
            "current_version": 3,
        }
    )

    with pytest.raises(CustomerServiceVersionConflictError):
        fixture.application.apply_update(_apply_command(candidate))

    assert fixture.repository.get_locks == [True]
    assert fixture.repository.events == []
    assert fixture.repository.updates == []
    assert fixture.receipts.items == {}
    assert fixture.audit.items == []
    assert fixture.units[-1].rolled_back is True


def test_preview_fingerprint_mismatch_rolls_back_before_mutation():
    fixture = _Fixture()

    with pytest.raises(CustomerServicePreviewFingerprintConflictError):
        fixture.application.apply_update(
            _apply_command(PreviewFingerprint("0" * 64))
        )

    assert fixture.repository.get_locks == [True]
    assert fixture.repository.events == []
    assert fixture.repository.updates == []
    assert fixture.receipts.items == {}
    assert fixture.audit.items == []
    assert fixture.delivery_tasks.requests == []
    assert fixture.units[-1].committed is False
    assert fixture.units[-1].rolled_back is True


def test_repository_failure_rolls_back_event_and_does_not_append_receipt_or_audit():
    fixture = _Fixture()
    preview = fixture.application.preview_update(_preview_command())
    fixture.repository.update_error = RuntimeError("database write failed")

    with pytest.raises(RuntimeError, match="database write failed"):
        fixture.application.apply_update(
            _apply_command(preview.preview_fingerprint)
        )

    assert len(fixture.repository.events) == 1
    assert len(fixture.repository.updates) == 1
    assert fixture.receipts.items == {}
    assert fixture.audit.items == []
    assert fixture.delivery_tasks.requests == []
    assert fixture.units[-1].committed is False
    assert fixture.units[-1].rolled_back is True


def test_update_requests_are_strict_and_require_nullable_note_explicitly():
    valid = {
        "status": "resolved",
        "internal_note": None,
        "expected_version": 3,
    }

    assert CustomerServiceUpdatePreviewRequest(**valid).internal_note is None
    with pytest.raises(ValidationError):
        CustomerServiceUpdatePreviewRequest(
            status="resolved",
            expected_version=3,
        )
    with pytest.raises(ValidationError):
        CustomerServiceUpdatePreviewRequest(
            **valid,
            unexpected=True,
        )
    assert CustomerServiceUpdatePreviewRequest(
        status="handling",
        internal_note=None,
        expected_version=3,
    ).status is CustomerServiceStatus.HANDLING
    with pytest.raises(ValidationError):
        CustomerServiceUpdatePreviewRequest(
            status="invalid",
            internal_note=None,
            expected_version=3,
        )
    with pytest.raises(ValidationError):
        CustomerServiceUpdateApplyRequest(
            **valid,
            preview_fingerprint="A" * 64,
        )
    with pytest.raises(ValidationError):
        CustomerServiceUpdatePreviewRequest(
            status="resolved",
            internal_note=None,
            expected_version=-1,
        )
    with pytest.raises(ValidationError):
        CustomerServiceUpdatePreviewRequest(
            status="resolved",
            internal_note="x" * 4001,
            expected_version=3,
        )
    with pytest.raises(ValidationError):
        CustomerServiceUpdatePreviewRequest(
            status="resolved",
            internal_note=None,
            expected_version=None,
        )


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_category", "expected_code"),
    [
        (
            CustomerServiceTicketNotFoundError("missing"),
            404,
            "not_found",
            "customer_service_ticket_not_found",
        ),
        (
            CustomerServiceVersionConflictError("stale"),
            409,
            "conflict",
            "customer_service_ticket_version_conflict",
        ),
        (
            CustomerServiceIdempotencyMismatchError("mismatch"),
            409,
            "idempotency_mismatch",
            "customer_service_update_idempotency_mismatch",
        ),
        (
            OperationalError(1213, "deadlock"),
            503,
            "unavailable",
            "customer_service_update_temporarily_unavailable",
        ),
        (
            RuntimeError("private repository detail"),
            500,
            "internal",
            "customer_service_update_internal_error",
        ),
    ],
)
def test_update_route_errors_use_the_typed_global_envelope(
    error, expected_status, expected_category, expected_code
):
    def operation():
        raise error

    with pytest.raises(HTTPException) as captured:
        _call_update_endpoint(
            operation,
            correlation_id=CorrelationId("customer-route-error"),
        )

    assert captured.value.status_code == expected_status
    body = captured.value.detail["error"]
    assert body == {
        "category": expected_category,
        "code": expected_code,
        "message": body["message"],
        "field_errors": [],
        "domain_blockers": [],
        "retryable": expected_category == "unavailable",
        "correlation_id": "customer-route-error",
        "current_version": None,
    }
    assert "private repository detail" not in body["message"]
