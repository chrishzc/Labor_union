"""Contract tests for verified LIFF customer order-change intake."""

from datetime import datetime, timezone

import pytest

from domains.orders.order_change_request import OrderChangeRequest
from shared_kernel.fingerprints import PreviewFingerprint
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
        self.requests = []
        self.receipts = {}

    def list_for_client(self, client_id):
        assert client_id == 21
        return tuple(self.items)

    def load_for_client(self, client_id, case_no, *, lock=False):
        self.load_calls.append((client_id, case_no, lock))
        return self.items[0] if client_id == 21 and case_no == "CASE-001" else None

    def find_submission(self, client_id, digest):
        return self.receipts.get((client_id, digest))

    def create_request(self, command):
        self.requests.append(command)
        created = OrderChangeRequest(
            31, command.case_no, command.kind, command.before, command.requested,
            datetime(2026, 11, 15, tzinfo=timezone.utc), command.command_fingerprint, None,
        )
        self.receipts[(command.client_id, command.idempotency_digest)] = created
        return created


class _Bindings:
    def __init__(self):
        self.calls = []

    def read_current(self, identity, *, client_id, lock=False):
        self.calls.append((identity, client_id, lock))
        return ClientBindingEvidence(identity, client_id, 5, ("customer",), True, False)


class _Audit:
    def __init__(self):
        self.intents = []

    def append(self, intent):
        self.intents.append(intent)


class _UnitOfWork:
    def __init__(self, orders, bindings, audit):
        self.customer_order_changes = orders
        self.customer_order_change_bindings = bindings
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
    audit = _Audit()
    opened = []

    def factory():
        unit_of_work = _UnitOfWork(orders, bindings, audit)
        opened.append(unit_of_work)
        return unit_of_work

    return CustomerOrderChangeApplication(factory), orders, bindings, audit, opened


def test_query_returns_only_current_customer_orders_without_writing() -> None:
    application, orders, bindings, audit, opened = _fixture()

    result = application.query("U-CUSTOMER", 21)

    assert [item.case_no for item in result] == ["CASE-001"]
    assert bindings.calls == [("U-CUSTOMER", 21, False)]
    assert orders.requests == []
    assert audit.intents == []
    assert opened[0].commit_count == 0


def test_preview_projects_before_after_and_has_zero_writes() -> None:
    application, orders, _, audit, opened = _fixture()

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
    assert orders.requests == []
    assert audit.intents == []
    assert opened[0].commit_count == 0


def test_apply_fresh_locks_and_creates_only_an_orders_request() -> None:
    application, orders, bindings, audit, opened = _fixture()
    preview = application.preview(
        "U-CUSTOMER", 21, "CASE-001", 7, "other",
        {"details": "希望調整服務內容"},
    )

    receipt = application.apply(
        "U-CUSTOMER",
        21,
        "CASE-001",
        7,
        "other",
        preview.requested,
        preview.preview_fingerprint,
        IdempotencyKey("order-change-browser-session-1"),
    )

    command = orders.requests[0]
    assert command.client_id == 21
    assert command.case_no == "CASE-001"
    assert command.before == {}
    assert command.requested == {"details": "希望調整服務內容"}
    assert receipt.request_id == 31
    assert receipt.request_status == "pending"
    assert receipt.replayed is False
    assert bindings.calls[-1] == ("U-CUSTOMER", 21, True)
    assert orders.load_calls[-1] == (21, "CASE-001", True)
    assert len(audit.intents) == 1
    assert opened[-1].commit_count == 1
    assert orders.items[0] == _snapshot()


def test_exact_replay_survives_order_update_and_different_payload_fails_closed() -> None:
    application, orders, _, _, opened = _fixture()
    first = application.preview(
        "U-CUSTOMER", 21, "CASE-001", 7, "other", {"details": "想增加其他服務"}
    )
    key = IdempotencyKey("order-change-browser-session-2")

    application.apply(
        "U-CUSTOMER", 21, "CASE-001", 7, "other", first.requested,
        first.preview_fingerprint, key,
    )
    orders.items[0] = _snapshot(version=8)
    replay = application.apply(
        "U-CUSTOMER", 21, "CASE-001", 7, "other", first.requested,
        first.preview_fingerprint, key,
    )

    assert replay.request_id == 31
    assert replay.replayed is True
    assert len(orders.requests) == 1
    assert opened[-1].commit_count == 0

    changed = application.preview(
        "U-CUSTOMER", 21, "CASE-001", 8, "other", {"details": "改成另一項需求"}
    )
    with pytest.raises(CustomerOrderChangeError) as raised:
        application.apply(
            "U-CUSTOMER", 21, "CASE-001", 8, "other", changed.requested,
            changed.preview_fingerprint, key,
        )
    assert raised.value.code == "order_change_idempotency_key_reused_with_different_payload"


def test_stale_order_or_preview_fingerprint_fails_before_request_write() -> None:
    application, orders, _, _, opened = _fixture()

    with pytest.raises(CustomerOrderChangeError) as stale:
        application.apply(
            "U-CUSTOMER", 21, "CASE-001", 6, "service_address",
            {
                "service_city": "新竹市",
                "service_address": "新竹市北區新地址",
                "residence_type": "透天",
            },
            PreviewFingerprint("0" * 64),
            IdempotencyKey("stale-version"),
        )

    assert stale.value.code == "order_change_order_version_stale"
    with pytest.raises(CustomerOrderChangeError, match="order_change_preview_fingerprint_mismatch"):
        application.apply("U-CUSTOMER", 21, "CASE-001", 7, "other", {"details": "需求"}, PreviewFingerprint("0" * 64), IdempotencyKey("stale-fingerprint"))
    with pytest.raises(CustomerOrderChangeError, match="order_change_order_not_found"):
        application.apply("U-CUSTOMER", 21, "ANOTHER-CASE", 7, "other", {"details": "需求"}, PreviewFingerprint("0" * 64), IdempotencyKey("another-case"))
    assert orders.requests == []
    assert all(unit.commit_count == 0 for unit in opened)


def test_retired_customer_date_request_cannot_create_request():
    application, orders, _, audit, opened = _fixture()
    with pytest.raises(CustomerOrderChangeError,match='order_change_service_dates_retired'):
        application.preview('U-CUSTOMER',21,'CASE-001',7,'service_days',{'start_date':'2027-01-01'})
    assert not orders.requests and not audit.intents
    assert opened[0].commit_count==0
