from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from domains.customer_service.ticket import (
    CustomerServiceCategory,
    CustomerServiceStatus,
    CustomerServiceTransitionError,
    transition_ticket,
)
from domains.line.identities import LineUserId
from shared_kernel.migration_release import load_migration_release_manifest
from subsystems.line.service_help_application import LineServiceHelpApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DeliveryTasks:
    def __init__(self):
        self.requests = []

    def enqueue(self, request):
        self.requests.append(request)


class CustomerServiceRepository:
    def __init__(self):
        self.messages = []

    def create_or_append(self, command):
        self.messages.append(command)
        return SimpleNamespace(ticket_id=31)

    def latest_client_case(self, _line_user_id):
        return None


class Audit:
    def __init__(self):
        self.intents = []

    def append(self, intent):
        self.intents.append(intent)


def _inbox(event_id="event-1"):
    return SimpleNamespace(event=SimpleNamespace(event_id=SimpleNamespace(value=event_id)))


def _unit_of_work():
    return SimpleNamespace(
        delivery_tasks=DeliveryTasks(),
        customer_service=CustomerServiceRepository(),
        audit=Audit(),
    )


def test_customer_service_ticket_state_machine_rejects_backwards_transition():
    assert transition_ticket(CustomerServiceStatus.WAITING, CustomerServiceStatus.HANDLING) is CustomerServiceStatus.HANDLING
    assert transition_ticket(CustomerServiceStatus.RESOLVED, CustomerServiceStatus.HANDLING) is CustomerServiceStatus.HANDLING
    with pytest.raises(CustomerServiceTransitionError):
        transition_ticket(CustomerServiceStatus.HANDLING, CustomerServiceStatus.WAITING)


def test_service_help_menu_is_a_canonical_flex_delivery():
    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 11, tzinfo=timezone.utc))

    handled = application.handle(_inbox(), unit_of_work, LineUserId("U123456789"), "服務說明")

    assert handled is True
    assert len(unit_of_work.delivery_tasks.requests) == 1
    request = unit_of_work.delivery_tasks.requests[0]
    assert request.message_kind.value == "flex"
    assert request.idempotency_key.value == "service-help:menu:event-1"
    assert "聯絡工會人員" in request.payload_json


def test_contact_union_creates_ticket_audit_and_delivery_in_one_uow_boundary():
    unit_of_work = _unit_of_work()
    application = LineServiceHelpApplication(lambda: datetime(2026, 8, 11, tzinfo=timezone.utc))

    handled = application.handle(_inbox("event-2"), unit_of_work, LineUserId("U123456789"), "聯絡工會人員")

    assert handled is True
    assert unit_of_work.customer_service.messages[0].category is CustomerServiceCategory.CONTACT_UNION
    assert unit_of_work.customer_service.messages[0].event_key == "line-service-help:contact_union:event-2"
    assert len(unit_of_work.audit.intents) == 1
    assert len(unit_of_work.delivery_tasks.requests) == 1


def test_first_release_schema_has_versioned_ticket_and_append_only_events():
    schema = (PROJECT_ROOT / "db/schema_parts/166_customer_service_runtime.sql").read_text(encoding="utf-8")
    assert "version BIGINT NOT NULL" in schema
    assert "customer_service_ticket_events" in schema
    assert "UNIQUE KEY uq_customer_service_event_key" in schema
    assert "active_marker" in schema


def test_stage11_migration_manifest_hashes_customer_service_artifacts():
    path = PROJECT_ROOT / "db/migration_releases/labor_union_2026_08_11_line_stage11_v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    artifacts = [*manifest["artifacts"], manifest["descriptor_artifact"]]
    for artifact in artifacts:
        content = (PROJECT_ROOT / artifact["relative_path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == artifact["sha256"]


def test_stage11_manifest_is_accepted_by_the_canonical_loader():
    path = (
        PROJECT_ROOT
        / "db/migration_releases/labor_union_2026_08_11_line_stage11_v1.json"
    )
    manifest = load_migration_release_manifest(path, PROJECT_ROOT)
    artifact_names = [item.artifact.name for item in manifest.schema_artifacts]
    assert artifact_names == ["166_customer_service_runtime.sql"]


def test_customer_context_uses_canonical_identity_binding_ssot():
    repository = (
        PROJECT_ROOT / "infrastructure/mysql/customer_service_repository.py"
    ).read_text(encoding="utf-8")
    assert "FROM line_identity_bindings b" in repository
    assert "WHERE c.line_user_id=%s" not in repository


def test_merge_menu_copy_uses_canonical_entry_and_verified_staff_liff_targets():
    menu = (PROJECT_ROOT / "config/line_menu.json").read_text(encoding="utf-8")
    identity = (PROJECT_ROOT / "line/static/identity.html").read_text(encoding="utf-8")
    staff_orders = (PROJECT_ROOT / "line/static/staff_order_search.html").read_text(encoding="utf-8")
    assert '"text": "服務登記"' in menu
    assert '"text": "服務說明"' in menu
    assert "?target=staff_order_search" in menu
    assert "?target=staff_schedule" in menu
    assert "flow_id=${encodeURIComponent(flowId)}" in identity
    assert "development_line_user_id" not in staff_orders
    assert "userId" not in staff_orders


def test_deferred_history_records_legacy_paths_that_must_not_return():
    history = (PROJECT_ROOT / "document/架構重整/03_追蹤清單與證據/LINE_merge功能未移植_history_20260811.md").read_text(encoding="utf-8")
    assert "query string `userId`" in history
    assert "人工 Preview／Apply" in history
    assert "直接 UPDATE clients" in history
