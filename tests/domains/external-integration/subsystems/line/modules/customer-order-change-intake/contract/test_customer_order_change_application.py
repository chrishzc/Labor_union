"""Contract tests for verified LIFF customer order-change intake."""

from types import SimpleNamespace

import pytest

from domains.customer_service.ticket import CustomerServiceStatus
from shared_kernel.identities import IdempotencyKey
from subsystems.client_profile.contracts import ClientBindingEvidence
from subsystems.line.customer_order_change_application import CustomerOrderChangeApplication
from subsystems.line.customer_order_change_contracts import (
    CustomerOrderChangeError,
    CustomerOrderSnapshot,
)


def _snapshot(*, status="訂單成立", version=7):
    return CustomerOrderSnapshot(
        "CASE-001",
        status,
        version,
        3,
        {
            "service_city": "新竹市",
            "service_address": "新竹市東區原地址",
            "residence_type": "電梯大樓",
            "requires_cooking": "不需要",
            "start_date": "2026-10-01",
            "end_date": "2026-10-20",
            "service_days": "20",
            "service_start_time": "08:00:00",
            "service_end_time": "17:00:00",
            "service_end_day_offset": "0",
        },
    )


class _Orders:
    def __init__(self):
        self.items = [_snapshot(), _snapshot(status="訂單完成")]
        self.load_calls = []

    def list_for_client(self, client_id):
        assert client_id == 21
        return tuple(self.items)

    def load_for_client(self, client_id, case_no, *, lock=False):
        self.load_calls.append((client_id, case_no, lock))
        return self.items[0] if client_id == 21 and case_no == "CASE-001" else None


class _Bindings:
    def __init__(self):
        self.calls = []

    def read_current(self, identity, *, client_id, lock=False):
        self.calls.append((identity, client_id, lock))
        return ClientBindingEvidence(identity, client_id, 5, ("customer",), True, False)


class _CustomerService:
    def __init__(self):
        self.messages = []
        self.events = {}
        self.ticket = SimpleNamespace(
            ticket_id=31,
            status=CustomerServiceStatus.WAITING,
        )

    def event_message(self, event_key):
        return self.events.get(event_key)

    def create_or_append(self, command):
        self.messages.append(command)
        self.events[command.event_key] = command.message
        return self.ticket

    def get_by_event_key(self, event_key):
        return self.ticket if event_key in self.events else None


class _Audit:
    def __init__(self):
        self.intents = []

    def append(self, intent):
        self.intents.append(intent)


class _UnitOfWork:
    def __init__(self, orders, bindings, customer_service, audit):
        self.customer_order_changes = orders
        self.customer_order_change_bindings = bindings
        self.customer_service = customer_service
        self.audit = audit
        self.commit_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.commit_count += 1


def _fixture():
    orders = _Orders()
    bindings = _Bindings()
    customer_service = _CustomerService()
    audit = _Audit()
    opened = []

    def factory():
        unit_of_work = _UnitOfWork(orders, bindings, customer_service, audit)
        opened.append(unit_of_work)
        return unit_of_work

    return CustomerOrderChangeApplication(factory), orders, bindings, customer_service, audit, opened


def test_query_returns_only_current_customer_orders_without_writing() -> None:
    application, _, bindings, customer_service, audit, opened = _fixture()

    result = application.query("U-CUSTOMER", 21)

    assert [item.case_no for item in result] == ["CASE-001"]
    assert bindings.calls == [("U-CUSTOMER", 21, False)]
    assert customer_service.messages == []
    assert audit.intents == []
    assert opened[0].commit_count == 0


def test_preview_projects_before_after_and_has_zero_writes() -> None:
    application, _, _, customer_service, audit, opened = _fixture()

    preview = application.preview(
        "U-CUSTOMER",
        21,
        "CASE-001",
        7,
        "service_address",
        {
            "service_city": "新竹市",
            "service_address": "新竹市北區新地址",
            "residence_type": "透天",
        },
    )

    assert preview.before == {
        "service_city": "新竹市",
        "service_address": "新竹市東區原地址",
        "residence_type": "電梯大樓",
    }
    assert preview.requested == {
        "residence_type": "透天",
        "service_address": "新竹市北區新地址",
        "service_city": "新竹市",
    }
    assert "月嫂接案意願" in preview.impact_note
    assert customer_service.messages == []
    assert audit.intents == []
    assert opened[0].commit_count == 0


def test_apply_fresh_locks_and_creates_only_a_manual_ticket_request() -> None:
    application, orders, bindings, customer_service, audit, opened = _fixture()
    preview = application.preview(
        "U-CUSTOMER", 21, "CASE-001", 7, "service_days",
        {"start_date": "2026-10-03", "end_date": "2026-10-24", "service_days": "22"},
    )

    receipt = application.apply(
        "U-CUSTOMER",
        21,
        "CASE-001",
        7,
        "service_days",
        preview.requested,
        preview.preview_fingerprint,
        IdempotencyKey("order-change-browser-session-1"),
    )

    command = customer_service.messages[0]
    assert command.client_id == 21
    assert command.case_no == "CASE-001"
    assert "尚未修改正式訂單" in command.message
    assert receipt.ticket_id == 31
    assert receipt.ticket_status == "waiting"
    assert receipt.replayed is False
    assert bindings.calls[-1] == ("U-CUSTOMER", 21, True)
    assert orders.load_calls[-1] == (21, "CASE-001", True)
    assert len(audit.intents) == 1
    assert opened[-1].commit_count == 1


def test_exact_replay_returns_same_ticket_and_different_payload_fails_closed() -> None:
    application, _, _, customer_service, _, _ = _fixture()
    first = application.preview(
        "U-CUSTOMER", 21, "CASE-001", 7, "other", {"details": "想增加其他服務"}
    )
    key = IdempotencyKey("order-change-browser-session-2")

    application.apply(
        "U-CUSTOMER", 21, "CASE-001", 7, "other", first.requested,
        first.preview_fingerprint, key,
    )
    replay = application.apply(
        "U-CUSTOMER", 21, "CASE-001", 7, "other", first.requested,
        first.preview_fingerprint, key,
    )

    assert replay.ticket_id == 31
    assert replay.replayed is True
    assert len(customer_service.messages) == 1

    changed = application.preview(
        "U-CUSTOMER", 21, "CASE-001", 7, "other", {"details": "改成另一項需求"}
    )
    with pytest.raises(CustomerOrderChangeError) as raised:
        application.apply(
            "U-CUSTOMER", 21, "CASE-001", 7, "other", changed.requested,
            changed.preview_fingerprint, key,
        )
    assert raised.value.code == "order_change_idempotency_key_reused_with_different_payload"


def test_stale_order_or_preview_fingerprint_fails_before_ticket_write() -> None:
    application, _, _, customer_service, _, _ = _fixture()

    with pytest.raises(CustomerOrderChangeError) as stale:
        application.preview(
            "U-CUSTOMER", 21, "CASE-001", 6, "service_address",
            {
                "service_city": "新竹市",
                "service_address": "新竹市北區新地址",
                "residence_type": "透天",
            },
        )

    assert stale.value.code == "order_change_order_version_stale"
    assert customer_service.messages == []
