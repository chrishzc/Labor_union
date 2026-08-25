"""
File: test_customer_service_reply_preview_apply.py
Description: 驗證客服回覆 Preview／Apply、冪等 receipt、delivery queued 與退役 direct 路由。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.routes.customer_service import retired_reply, router as customer_service_router
from api.routes.line_mobile_admin import (
    retired_customer_service_reply,
    router as mobile_admin_router,
)
from api.schemas.customer_service import (
    CustomerServiceReplyApplyRequest,
    CustomerServiceReplyPreviewRequest,
    CustomerServiceReplyPreviewView,
)
from domains.customer_service.ticket import (
    CustomerServiceCategory,
    CustomerServiceStatus,
    CustomerServiceTicket,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.customer_service.application import (
    CustomerServiceApplication,
    CustomerServiceIdempotencyMismatchError,
    CustomerServicePreviewFingerprintConflictError,
    CustomerServiceVersionConflictError,
)
from subsystems.customer_service.contracts import (
    ApplyCustomerServiceTicketReply,
    PreviewCustomerServiceTicketReply,
)


def _ticket(*, version: int = 3) -> CustomerServiceTicket:
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    return CustomerServiceTicket(
        ticket_id=51,
        line_user_id="U-test-only-51",
        category=CustomerServiceCategory.CONTACT_UNION,
        status=CustomerServiceStatus.WAITING,
        version=version,
        created_at=now,
        updated_at=now,
    )


class _Repository:
    def __init__(self) -> None:
        self.ticket = _ticket()
        self.get_locks: list[bool] = []
        self.replies: list[tuple] = []
        self.updates: list[tuple] = []

    def get(self, ticket_id: int, *, lock: bool = False):
        assert ticket_id == self.ticket.ticket_id
        self.get_locks.append(lock)
        return self.ticket

    def append_agent_reply(self, *values) -> None:
        self.replies.append(values)

    def update(self, ticket_id, current_version, status, note, admin_user_id):
        self.updates.append((ticket_id, current_version, status, note, admin_user_id))
        self.ticket = replace(
            self.ticket,
            status=status,
            version=self.ticket.version + 1,
            internal_note=note,
            assigned_admin_user_id=admin_user_id,
        )
        return self.ticket

    def detail(self, ticket_id: int):
        assert ticket_id == self.ticket.ticket_id
        return {
            "ticket": {
                "ticket_id": ticket_id,
                "line_user_id_masked": "U-te…y-51",
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


class _Sink:
    def __init__(self) -> None:
        self.items = []

    def append(self, item) -> None:
        self.items.append(item)


class _Receipts:
    def __init__(self) -> None:
        self.items = {}

    def get(self, key):
        return self.items.get(key.value)

    def append(self, receipt) -> None:
        self.items[receipt.key.value] = receipt


class _DeliveryTasks:
    def __init__(self) -> None:
        self.requests = []

    def enqueue(self, request) -> None:
        self.requests.append(request)


class _UnitOfWork:
    def __init__(self, fixture) -> None:
        self.customer_service = fixture.repository
        self.receipts = fixture.receipts
        self.audit = fixture.audit
        self.delivery_tasks = fixture.delivery_tasks
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
    def __init__(self) -> None:
        self.repository = _Repository()
        self.receipts = _Receipts()
        self.audit = _Sink()
        self.delivery_tasks = _DeliveryTasks()
        self.units = []
        self.application = CustomerServiceApplication(
            self.unit_of_work,
            now=lambda: datetime(2026, 8, 24, tzinfo=timezone.utc),
        )

    def unit_of_work(self):
        unit = _UnitOfWork(self)
        self.units.append(unit)
        return unit


def _preview_command(reply_text: str = "  已收到，我們會處理。  "):
    return PreviewCustomerServiceTicketReply(
        51,
        reply_text,
        False,
        "  人工回覆  ",
        ExpectedVersion(3),
        CorrelationId("customer-reply-preview-51"),
    )


def _apply_command(fingerprint: PreviewFingerprint, *, key: str = "reply-apply-51"):
    return ApplyCustomerServiceTicketReply(
        51,
        "  已收到，我們會處理。  ",
        False,
        "  人工回覆  ",
        ExpectedVersion(3),
        fingerprint,
        "admin:7",
        7,
        IdempotencyKey(key),
        CorrelationId("customer-reply-apply-51"),
    )


def test_reply_preview_is_zero_write_and_has_the_frozen_strict_shape():
    fixture = _Fixture()

    preview = fixture.application.preview_reply(_preview_command())

    assert preview.before_status is CustomerServiceStatus.WAITING
    assert preview.after_status is CustomerServiceStatus.HANDLING
    assert preview.current_version == 3
    assert preview.expected_version == 3
    assert preview.reply_character_count == len("已收到，我們會處理。")
    assert preview.will_enqueue_delivery is True
    assert preview.apply_ready is True
    assert preview.preview_fingerprint == fingerprint_payload(
        {
            "ticket_id": 51,
            "reply_text": "已收到，我們會處理。",
            "resolve": False,
            "normalized_internal_note": "人工回覆",
            "current_status": "waiting",
            "target_status": "handling",
            "current_version": 3,
        }
    )
    assert fixture.repository.get_locks == [False]
    assert fixture.repository.replies == []
    assert fixture.repository.updates == []
    assert fixture.receipts.items == {}
    assert fixture.delivery_tasks.requests == []
    assert fixture.units[-1].rolled_back is True

    view = CustomerServiceReplyPreviewView(
        ticket_id=preview.ticket_id,
        before_status=preview.before_status,
        after_status=preview.after_status,
        current_version=preview.current_version,
        expected_version=preview.expected_version,
        reply_character_count=preview.reply_character_count,
        will_enqueue_delivery=preview.will_enqueue_delivery,
        preview_fingerprint=preview.preview_fingerprint.value,
        apply_ready=preview.apply_ready,
    )
    assert set(view.model_dump()) == {
        "ticket_id",
        "before_status",
        "after_status",
        "current_version",
        "expected_version",
        "reply_character_count",
        "will_enqueue_delivery",
        "preview_fingerprint",
        "apply_ready",
    }


def test_reply_apply_fresh_locks_and_commits_receipt_readback_and_delivery_task():
    fixture = _Fixture()
    preview = fixture.application.preview_reply(_preview_command())

    result = fixture.application.apply_reply(_apply_command(preview.preview_fingerprint))

    assert fixture.repository.get_locks[-1] is True
    assert len(fixture.repository.replies) == 1
    assert fixture.repository.updates == [
        (51, 3, CustomerServiceStatus.HANDLING, "人工回覆", 7)
    ]
    assert len(fixture.delivery_tasks.requests) == 1
    assert fixture.receipts.items["reply-apply-51"].payload_fingerprint == preview.preview_fingerprint
    assert fixture.units[-1].committed is True
    assert result.ticket_id == 51
    assert result.resulting_status is CustomerServiceStatus.HANDLING
    assert result.resulting_version == 4
    assert result.delivery_enqueued is True
    assert result.delivery_delivered is False
    assert result.replayed is False
    assert result.readback["ticket"]["version"] == 4


def test_reply_apply_replay_does_not_duplicate_event_or_delivery():
    fixture = _Fixture()
    preview = fixture.application.preview_reply(_preview_command())
    command = _apply_command(preview.preview_fingerprint)
    fixture.application.apply_reply(command)

    replay = fixture.application.apply_reply(command)

    assert len(fixture.repository.replies) == 1
    assert len(fixture.delivery_tasks.requests) == 1
    assert replay.replayed is True
    assert replay.delivery_enqueued is True
    assert replay.delivery_delivered is False


def test_reply_apply_stale_fingerprint_fails_before_any_write():
    fixture = _Fixture()

    with pytest.raises(CustomerServicePreviewFingerprintConflictError):
        fixture.application.apply_reply(_apply_command(PreviewFingerprint("0" * 64)))

    assert fixture.repository.replies == []
    assert fixture.repository.updates == []
    assert fixture.receipts.items == {}
    assert fixture.delivery_tasks.requests == []
    assert fixture.units[-1].rolled_back is True


def test_reply_apply_rechecks_fresh_version_before_any_write():
    fixture = _Fixture()
    preview = fixture.application.preview_reply(_preview_command())
    fixture.repository.ticket = replace(fixture.repository.ticket, version=4)

    with pytest.raises(CustomerServiceVersionConflictError):
        fixture.application.apply_reply(_apply_command(preview.preview_fingerprint))

    assert fixture.repository.get_locks[-1] is True
    assert fixture.repository.replies == []
    assert fixture.repository.updates == []
    assert fixture.receipts.items == {}
    assert fixture.delivery_tasks.requests == []


def test_reply_replay_rejects_changed_payload_without_duplicate_delivery():
    fixture = _Fixture()
    preview = fixture.application.preview_reply(_preview_command())
    fixture.application.apply_reply(_apply_command(preview.preview_fingerprint))
    changed = ApplyCustomerServiceTicketReply(
        51,
        "不同回覆",
        False,
        "人工回覆",
        ExpectedVersion(3),
        preview.preview_fingerprint,
        "admin:7",
        7,
        IdempotencyKey("reply-apply-51"),
        CorrelationId("customer-reply-apply-51"),
    )

    with pytest.raises(CustomerServiceIdempotencyMismatchError):
        fixture.application.apply_reply(changed)

    assert len(fixture.repository.replies) == 1
    assert len(fixture.delivery_tasks.requests) == 1


def test_reply_http_requests_are_strict_and_apply_adds_receipt_fields():
    preview = {
        "reply_text": "已收到",
        "resolve": False,
        "internal_note": None,
        "expected_version": 3,
    }
    assert CustomerServiceReplyPreviewRequest(**preview).reply_text == "已收到"
    assert CustomerServiceReplyApplyRequest(
        **preview,
        idempotency_key="reply-51",
        preview_fingerprint="a" * 64,
    ).idempotency_key == "reply-51"
    with pytest.raises(ValidationError):
        CustomerServiceReplyPreviewRequest(**preview, unexpected=True)
    with pytest.raises(ValidationError):
        CustomerServiceReplyApplyRequest(**preview, preview_fingerprint="A" * 64)


def test_canonical_and_mobile_routes_expose_preview_apply_and_retire_direct_reply():
    canonical = {
        (route.path, method)
        for route in customer_service_router.routes
        for method in route.methods
    }
    mobile = {
        (route.path, method)
        for route in mobile_admin_router.routes
        for method in route.methods
    }
    assert ("/api/v1/customer-service/tickets/{ticket_id}/reply/preview", "POST") in canonical
    assert ("/api/v1/customer-service/tickets/{ticket_id}/reply/apply", "POST") in canonical
    assert ("/api/v1/customer-service/tickets/{ticket_id}/reply", "POST") in canonical
    assert ("/api/v1/line/mobile-admin/customer-service/tickets/{ticket_id}/reply/preview", "POST") in mobile
    assert ("/api/v1/line/mobile-admin/customer-service/tickets/{ticket_id}/reply/apply", "POST") in mobile
    assert ("/api/v1/line/mobile-admin/customer-service/tickets/{ticket_id}/reply", "POST") in mobile

    with pytest.raises(HTTPException) as canonical_retired:
        retired_reply(51, object())
    with pytest.raises(HTTPException) as mobile_retired:
        retired_customer_service_reply(51)
    assert canonical_retired.value.status_code == 410
    assert mobile_retired.value.status_code == 410
