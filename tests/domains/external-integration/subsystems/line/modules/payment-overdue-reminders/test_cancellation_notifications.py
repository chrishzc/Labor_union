from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.routes import line_payment_receipt_notifications as route
from api.routes.line_payment_overdue_reminders import router
from domains.line.delivery import LineRecipientType
from shared_kernel.identities import ActorContext
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_finance.case_accounting_query import ClientAccountingItem, ClientCancellationAccounting
from subsystems.line.cancellation_notifications import (
    CancellationNoticeConflict, CancellationNoticeDelivery, CancellationNoticeSource,
    CancellationNotificationApplication, cancellation_notice_delivery_is_current,
)
from subsystems.line.capabilities import LineCapability
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.message_preview import LineMessagePreviewApplication


ACTOR = ActorContext("admin:1", (LineCapability.TASK_SEND.value,))
SOURCE = CancellationNoticeSource(
    "115000001", 13,
    ClientCancellationAccounting(date(2026, 11, 6), 6000, 5000, 7000, 3000, 0, 4000, "notice-charge"),
    ClientAccountingItem("notice-charge", "receivable", "", "", 4000, 2000, True, "3:2:0", "2026-11-20"),
    "99781699115001",
)


class Unit:
    def __init__(self):
        self.payment_receipt_notifications = self.delivery_tasks = self.audit = self
        self.source = SOURCE
        self.recipient = "U" + "1" * 32
        self.requests = {}
        self.commits = 0
        self.events = []
        self.cancellations = []
        self.task = None
        self.deliveries = {}

    def cancellation_source(self, case_no, *, lock=False):
        return self.source if self.source and case_no == self.source.case_no else None

    def cancellation_recipient(self, case_no, *, lock=False):
        return self.recipient

    def cancellation_delivery(self, reference, *, lock=False):
        return self.deliveries.get(reference)

    def enqueue(self, request):
        assert request.idempotency_key not in self.requests
        self.requests[request.idempotency_key] = request
        task_id = len(self.requests)
        self.deliveries[request.source_aggregate_identity] = CancellationNoticeDelivery(task_id, "pending")
        return SimpleNamespace(task_id=SimpleNamespace(value=task_id), status=SimpleNamespace(value="pending"))

    def append(self, event):
        self.events.append(event)

    def commit(self):
        self.commits += 1

    def cancel(self, command):
        self.cancellations.append(command)

    def get(self, task_id, *, lock=False):
        assert lock
        return self.task


@pytest.fixture
def service():
    unit = Unit()
    return unit, CancellationNotificationApplication(lambda: nullcontext(unit), lambda: datetime.now(UTC))


def test_partial_collection_preview_and_one_immutable_private_task(service):
    unit, app = service
    preview, = app.previews(SOURCE.case_no, ACTOR)
    assert all(value in preview.text for value in ("NT$ 4,000", "剩餘待收：NT$ 2,000", SOURCE.collection_account, "2026-11-20"))
    assert not unit.requests and not unit.events and unit.commits == 0

    assert app.send(SOURCE.case_no, preview.kind, preview.fingerprint, ACTOR) == (1, "pending")
    assert app.send(SOURCE.case_no, preview.kind, preview.fingerprint, ACTOR) == (1, "pending")
    assert len(unit.requests) == len(unit.events) == unit.commits == 1
    request, = unit.requests.values()
    assert request.recipient.recipient_type == LineRecipientType.USER
    assert request.recipient.identity.value == unit.recipient
    assert json.loads(request.payload_json)["text"] == preview.text
    observed, = app.previews(SOURCE.case_no, ACTOR)
    assert observed.delivery_status == "pending" and observed.fingerprint is None


def test_cancelled_before_provider_requires_fresh_preview_and_queues_only_one_replacement(service):
    unit, app = service
    old, = app.previews(SOURCE.case_no, ACTOR)
    assert app.send(SOURCE.case_no, old.kind, old.fingerprint, ACTOR) == (1, "pending")
    unit.deliveries[SOURCE.reference(old.kind)] = CancellationNoticeDelivery(1, "cancelled", can_replace=True)
    with pytest.raises(CancellationNoticeConflict):
        app.send(SOURCE.case_no, old.kind, old.fingerprint, ACTOR)
    updated, = app.previews(SOURCE.case_no, ACTOR)
    assert updated.fingerprint and updated.fingerprint != old.fingerprint
    assert app.send(SOURCE.case_no, updated.kind, updated.fingerprint, ACTOR) == (2, "pending")
    assert app.send(SOURCE.case_no, updated.kind, updated.fingerprint, ACTOR) == (2, "pending")
    unit.deliveries[SOURCE.reference(old.kind)] = CancellationNoticeDelivery(2, "uncertain")
    uncertain, = app.previews(SOURCE.case_no, ACTOR)
    assert uncertain.fingerprint is None and uncertain.delivery_status == "uncertain"
    assert len(unit.requests) == 2


@pytest.mark.parametrize("change", ["account", "balance", "recipient", "copy", "reopened", "new_cancellation"])
def test_changed_facts_or_copy_require_a_new_preview(service, change, monkeypatch):
    unit, app = service
    preview, = app.previews(SOURCE.case_no, ACTOR)
    if change == "account":
        unit.source = replace(SOURCE, collection_account=None)
    elif change == "balance":
        unit.source = replace(SOURCE, item=replace(SOURCE.item, actual_ntd=2200))
    elif change == "recipient":
        unit.recipient = "U" + "2" * 32
    elif change == "copy":
        monkeypatch.setattr("subsystems.line.cancellation_notifications.configured_payload",
                            lambda *_: {"text": "更新後的開頭"})
    elif change == "reopened":
        unit.source = None
    else:
        unit.source = replace(SOURCE, event_id=SOURCE.event_id + 1)
    with pytest.raises(CancellationNoticeConflict):
        app.send(SOURCE.case_no, preview.kind, preview.fingerprint, ACTOR)
    assert unit.commits == 0 and not unit.requests


def test_full_collection_and_refund_show_distinct_completion_notices(service):
    unit, app = service
    unit.source = replace(SOURCE, item=replace(SOURCE.item, settled=True, actual_ntd=4000))
    settlement, collection = app.previews(SOURCE.case_no, ACTOR)
    assert "剩餘待收：NT$ 0" in settlement.text and SOURCE.collection_account not in settlement.text
    assert collection.kind == "collection" and "本案補收已核銷：NT$ 4,000" in collection.text
    refund = replace(SOURCE.accounting, additional_charge_due_ntd=0, refund_due_ntd=4000,
                     bank_refunded_ntd=3950, transfer_fee_ntd=50)
    unit.source = replace(unit.source, accounting=refund, item=replace(unit.source.item, direction="payable"))
    _, completion = app.previews(SOURCE.case_no, ACTOR)
    assert completion.kind == "refund"
    assert "銀行實退金額：NT$ 3,950" in completion.text and "匯款手續費：NT$ 50" in completion.text
    unit.source = replace(unit.source, accounting=replace(refund, bank_refunded_ntd=None))
    assert [notice.kind for notice in app.previews(SOURCE.case_no, ACTOR)] == ["settlement"]


def test_missing_payment_information_or_binding_blocks_send(service):
    unit, app = service
    unit.source = replace(SOURCE, collection_account=None)
    (notice,) = app.previews(SOURCE.case_no, ACTOR)
    assert notice.fingerprint is None and "虛擬帳號" in notice.unavailable_reason
    unit.source = SOURCE
    unit.recipient = None
    (notice,) = app.previews(SOURCE.case_no, ACTOR)
    assert notice.fingerprint is None and "LINE 綁定" in notice.unavailable_reason
    assert unit.commits == 0 and not unit.requests


def test_worker_stops_stale_recipient_without_provider(service):
    unit, app = service
    preview, = app.previews(SOURCE.case_no, ACTOR)
    app.send(SOURCE.case_no, preview.kind, preview.fingerprint, ACTOR)
    request, = unit.requests.values()
    now = datetime.now(UTC)
    lease = SimpleNamespace(owner="test", acquired_at=now, expires_at=now + timedelta(seconds=30))
    task = SimpleNamespace(request=request, task_id=SimpleNamespace(value=1), lease=lease,
                           status=SimpleNamespace(value="processing"))
    unit.task = task
    assert cancellation_notice_delivery_is_current(unit, task)
    unit.recipient = None
    worker = LineDeliveryWorker(lambda: nullcontext(unit), None, "test", lambda: now)
    assert not worker._still_sendable(task)
    assert len(unit.cancellations) == 1


def test_closed_command_rejects_client_text_or_recipient_and_read_only_actor(service):
    unit, application = service
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(1, "synthetic", "測試", "system_admin")
    app.dependency_overrides[route.cancellation_application] = lambda: application
    path = f"/api/v1/line/payment-overdue-reminders/cancellation-notices/{SOURCE.case_no}"
    with TestClient(app) as client:
        preview, = client.get(path).json()["data"]
        assert unit.commits == 0
        body = {"kind": preview["kind"], "fingerprint": preview["fingerprint"]}
        for extra in ("text", "recipient"):
            assert client.post(path + "/send", json={**body, extra: "forged"}).status_code == 422
        assert client.post(path + "/send", json={**body, "fingerprint": "0" * 64}).status_code == 409
        assert unit.commits == 0
        assert client.post(path + "/send", json=body).json()["data"]["status"] == "pending"
        app.dependency_overrides[require_admin] = lambda: AdminPrincipal(2, "reader", "唯讀", "read_only")
        assert client.post(path + "/send", json=body).status_code == 403


def test_configuration_previews_render_edited_copy_with_fixed_accounting_details():
    configuration = SimpleNamespace(get=lambda *_: SimpleNamespace(
        definition_json='{"templates":[]}', revision=SimpleNamespace(value=1)))
    app = LineMessagePreviewApplication(configuration, lambda: pytest.fail("samples must not read customer facts"))
    actor = ActorContext("admin:1", (LineCapability.CONFIG_READ.value,))
    ids = {item.id for item in app.catalog(actor)}
    for kind, detail in (("settlement", "虛擬帳號"), ("refund", "銀行實退"), ("collection", "剩餘待收：NT$ 0")):
        key = "cancellation-notice-" + kind
        assert key in ids
        preview = app.render(key, "公會範本測試", None, None, actor, sample=True)
        assert preview.status == "ready" and preview.text.startswith("公會範本測試")
        assert detail in preview.text
