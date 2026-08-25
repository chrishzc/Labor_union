"""File: test_line_identity_management_first_release.py
Description: 驗證 LINE 身分管理與管理員綁定的資料庫契約。
"""

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from domains.line.identities import LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
    transition_binding_status,
)
from api.schemas.base import BaseResponse
from api.schemas.line_identity_management import LineIdentityRevocationRequestView
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.migration_release import load_migration_release_manifest
from infrastructure.mysql.line_identity_management_repository import (
    MySqlLineIdentityManagementRepository,
    _REQUEST_INSERT_SQL,
    _REQUEST_SELECT_SQL,
)
from infrastructure.mysql.line_identity_owner_adapters import MySqlAdminIdentityOwnerAdapter
from subsystems.line.capabilities import LineCapability
from subsystems.line.identity_management_application import (
    IDENTITY_MENU_RESET_INTENT,
    LineIdentityManagementApplication,
)
from subsystems.line.identity_management_contracts import (
    LineIdentityRevocationRequest,
    LineIdentityRevocationStatus,
    RequestLineIdentityRevocationCommand,
)
from subsystems.line.identity_revocation_worker import LineIdentityRevocationWorker
from subsystems.line.outbox_contracts import LineOutboxWorkItem


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


class Recorder:
    def __init__(self) -> None:
        self.items = []

    def append(self, item) -> None:
        self.items.append(item)


class IdentityRepository:
    def __init__(self, calls) -> None:
        self.calls = calls

    def request_revocation(self, *arguments):
        self.calls.append("binding_pending")
        return _binding_snapshot(LineIdentityBindingStatus.REVOCATION_PENDING, 3)

    def complete_revocation(self, *arguments):
        self.calls.append("binding_revoked")
        return _binding_snapshot(LineIdentityBindingStatus.REVOKED, 4)


class IdentityManagementRepository:
    def __init__(self, calls) -> None:
        self.calls = calls
        self.request = _revocation_request()

    def get_request_by_key(self, _key):
        return None

    def default_menu_publication(self):
        return {"id": 91, "line_rich_menu_id": "richmenu-default"}

    def create_request(self, _command, _pending, _publication):
        self.calls.append("request_created")
        return self.request

    def get_request(self, _request_id, *, lock=False):
        self.calls.append("request_locked" if lock else "request_read")
        return self.request

    def complete(self, _request, completed_version, _actor_id, **_keywords):
        self.calls.append("request_completed")
        self.request = replace(
            self.request,
            status=LineIdentityRevocationStatus.COMPLETED,
            pending_binding_version=completed_version,
        )


class StaffOwner:
    def __init__(self, calls) -> None:
        self.calls = calls

    def clear_staff(self, _subject_reference, _line_user_id):
        self.calls.append("owner_cleared")


class UnitOfWork:
    def __init__(self) -> None:
        self.calls = []
        self.identities = IdentityRepository(self.calls)
        self.identity_management = IdentityManagementRepository(self.calls)
        self.staff = StaffOwner(self.calls)
        self.customers = SimpleNamespace()
        self.admins = SimpleNamespace()
        self.outbox = Recorder()
        self.audit = Recorder()

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        return False

    def commit(self):
        self.calls.append("committed")


def _binding_snapshot(status, version):
    return LineIdentityBindingSnapshot(
        LineUserId("U-identity-1"),
        status,
        ExpectedVersion(version),
        LineBindingSubjectType.STAFF,
        "42",
    )


def _revocation_request():
    return LineIdentityRevocationRequest(
        70,
        LineUserId("U-identity-1"),
        LineBindingSubjectType.STAFF,
        "42",
        LineIdentityRevocationStatus.PENDING_MENU_RESET,
        ExpectedVersion(2),
        ExpectedVersion(3),
        91,
        "richmenu-default",
        "admin:8",
        "月嫂已退休",
        "identity-revoke:test-1",
        "identity-revoke:test-1",
        0,
        None,
        None,
    )


def _manager_actor():
    return ActorContext(
        "admin:8",
        (LineCapability.IDENTITY_BINDING_MANAGE.value,),
    )


def test_binding_state_machine_supports_menu_first_revocation() -> None:
    pending = transition_binding_status(
        LineIdentityBindingStatus.BOUND,
        LineIdentityBindingStatus.REVOCATION_PENDING,
    )
    assert pending is LineIdentityBindingStatus.REVOCATION_PENDING
    assert transition_binding_status(
        pending,
        LineIdentityBindingStatus.REVOKED,
    ) is LineIdentityBindingStatus.REVOKED


def test_revocation_request_disables_binding_and_enqueues_default_menu_atomically() -> None:
    unit_of_work = UnitOfWork()
    application = LineIdentityManagementApplication(lambda: unit_of_work, lambda: NOW)
    command = RequestLineIdentityRevocationCommand(
        LineUserId("U-identity-1"),
        ExpectedVersion(2),
        _manager_actor(),
        "月嫂已退休",
        IdempotencyKey("identity-revoke:test-1"),
        CorrelationId("identity-revoke:test-1"),
    )

    result = application.request_revocation(command)

    assert result.request_id == 70
    assert unit_of_work.calls == ["binding_pending", "request_created", "committed"]
    assert unit_of_work.outbox.items[0].intent_type == IDENTITY_MENU_RESET_INTENT
    assert json.loads(unit_of_work.outbox.items[0].payload_json)["provider_menu_id"] == "richmenu-default"


def test_finalize_clears_owner_only_after_binding_completion_boundary() -> None:
    unit_of_work = UnitOfWork()
    application = LineIdentityManagementApplication(lambda: unit_of_work, lambda: NOW)

    result = application.finalize(70)

    assert result.status is LineIdentityRevocationStatus.COMPLETED
    assert unit_of_work.calls == [
        "request_locked",
        "binding_revoked",
        "owner_cleared",
        "request_completed",
        "request_read",
        "committed",
    ]


def test_revocation_idempotency_rejects_same_key_with_different_expected_version() -> None:
    unit_of_work = UnitOfWork()
    unit_of_work.identity_management.get_request_by_key = lambda _key: _revocation_request()
    application = LineIdentityManagementApplication(lambda: unit_of_work, lambda: NOW)
    command = RequestLineIdentityRevocationCommand(
        LineUserId("U-identity-1"),
        ExpectedVersion(1),
        _manager_actor(),
        "月嫂已退休",
        IdempotencyKey("identity-revoke:test-1"),
        CorrelationId("identity-revoke:test-1"),
    )

    with pytest.raises(RuntimeError, match="idempotency_conflict"):
        application.request_revocation(command)


def test_worker_keeps_retryable_failure_pending_until_attempts_are_exhausted() -> None:
    unit_of_work = _worker_unit_of_work()
    worker = LineIdentityRevocationWorker(
        lambda: unit_of_work,
        SimpleNamespace(),
        "worker:test",
        lambda: NOW,
    )
    item = _work_item(attempt_count=0, maximum_attempts=3)

    worker._record_failure(item, 70, "timeout", "LINE timeout", True)

    assert unit_of_work.identity_management.failures[-1][-1] is False
    terminal_item = _work_item(attempt_count=2, maximum_attempts=3)
    worker._record_failure(terminal_item, 70, "timeout", "LINE timeout", True)
    assert unit_of_work.identity_management.failures[-1][-1] is True


def test_api_view_unwraps_domain_value_objects_at_the_boundary() -> None:
    response = BaseResponse[LineIdentityRevocationRequestView](
        data=_revocation_request()
    )

    assert response.data is not None
    assert response.data.line_user_id == "U-identity-1"
    assert response.data.pending_binding_version == 3


def _worker_unit_of_work():
    repository = SimpleNamespace(failures=[])

    def mark_failure(request_id, code, message, *, terminal):
        repository.failures.append((request_id, code, message, terminal))

    repository.mark_failure = mark_failure
    unit_of_work = UnitOfWork()
    unit_of_work.identity_management = repository
    unit_of_work.outbox = SimpleNamespace(completions=[], complete=lambda item: unit_of_work.outbox.completions.append(item))
    return unit_of_work


def _work_item(attempt_count, maximum_attempts):
    return LineOutboxWorkItem(
        18,
        "line_identity_revocation",
        "70",
        IDENTITY_MENU_RESET_INTENT,
        '{"line_user_id":"U-identity-1","provider_menu_id":"richmenu-default","request_id":70}',
        attempt_count,
        maximum_attempts,
        "worker:test",
        NOW,
    )


def test_stage12_schema_preserves_history_and_requires_menu_first_saga() -> None:
    schema = (PROJECT_ROOT / "db/schema_parts/186_line_identity_management.sql").read_text(encoding="utf-8")
    assert "revocation_pending" in schema
    assert "line_identity_revocation_requests" in schema
    assert "completed_at_utc" in schema
    assert "ON DELETE RESTRICT" in schema


class _DefaultMenuCursor:
    def __init__(self) -> None:
        self.statement = ""

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        return False

    def execute(self, statement, _parameters=None):
        self.statement = statement

    def fetchone(self):
        return {"id": 5, "line_rich_menu_id": "richmenu-canonical-default"}


class _DefaultMenuConnection:
    def __init__(self) -> None:
        self.cursor_instance = _DefaultMenuCursor()

    def cursor(self):
        return self.cursor_instance


class _LinkedAdminCursor:
    def __init__(self) -> None:
        self.statement = ""
        self.parameters = None

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        return False

    def execute(self, statement, parameters=None):
        self.statement = statement
        self.parameters = parameters

    def fetchone(self):
        return {"id": 7, "display_name": "管理員", "role": "line_manager"}


class _LinkedAdminConnection:
    def __init__(self) -> None:
        self.cursor_instance = _LinkedAdminCursor()

    def cursor(self):
        return self.cursor_instance


def test_revocation_repository_selects_canonical_published_default_menu() -> None:
    connection = _DefaultMenuConnection()
    repository = MySqlLineIdentityManagementRepository(connection)

    publication = repository.default_menu_publication()

    assert publication == {
        "id": 5,
        "line_rich_menu_id": "richmenu-canonical-default",
    }
    assert "FROM line_rich_menu_publication_tasks" in connection.cursor_instance.statement
    assert "menu_definition_id='default_menu'" in connection.cursor_instance.statement
    assert "publication_status='published'" in connection.cursor_instance.statement
    assert "line_rich_menu_publications" not in connection.cursor_instance.statement


def test_linked_admin_query_normalizes_all_utf8mb4_comparisons() -> None:
    connection = _LinkedAdminConnection()
    adapter = MySqlAdminIdentityOwnerAdapter(connection)

    linked_admin = adapter.get_linked_admin(LineUserId("U-admin-1"))

    assert linked_admin is not None
    statement = connection.cursor_instance.statement
    assert statement.count("COLLATE utf8mb4_unicode_ci") == 6
    assert "CONVERT(b.line_user_id USING utf8mb4)" in statement
    assert "CONVERT(b.subject_reference USING utf8mb4)" in statement
    assert "CONVERT(%s USING utf8mb4)" in statement
    assert connection.cursor_instance.parameters == ("U-admin-1",)


def test_stage13_schema_preserves_legacy_requests_and_owns_new_canonical_fk() -> None:
    schema = (
        PROJECT_ROOT
        / "db/schema_parts/179_line_identity_canonical_menu_publication.sql"
    ).read_text(encoding="utf-8")

    assert "MODIFY COLUMN default_menu_publication_id BIGINT NULL" in schema
    assert "canonical_default_menu_publication_id BIGINT UNSIGNED NULL" in schema
    assert "REFERENCES line_rich_menu_publication_tasks(id)" in schema
    assert "chk_line_identity_revocation_publication_source" in schema
    assert "canonical_default_menu_publication_id" in _REQUEST_INSERT_SQL
    assert "COALESCE(canonical_default_menu_publication_id" in _REQUEST_SELECT_SQL


def test_stage12_manifest_hashes_and_loads_all_owned_objects() -> None:
    path = PROJECT_ROOT / "db/migration_releases/labor_union_2026_08_11_line_stage12_v1.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    for artifact in [*raw["artifacts"], raw["descriptor_artifact"]]:
        content = (PROJECT_ROOT / artifact["relative_path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == artifact["sha256"]
    manifest = load_migration_release_manifest(path, PROJECT_ROOT)
    assert [item.artifact.name for item in manifest.schema_artifacts] == [
        "186_line_identity_management.sql"
    ]


def test_stage13_manifest_hashes_and_loads_canonical_publication_fk() -> None:
    path = (
        PROJECT_ROOT
        / "db/migration_releases/labor_union_2026_08_12_line_stage13_v1.json"
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    for artifact in [*raw["artifacts"], raw["descriptor_artifact"]]:
        content = (PROJECT_ROOT / artifact["relative_path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == artifact["sha256"]
    manifest = load_migration_release_manifest(path, PROJECT_ROOT)
    assert [item.artifact.name for item in manifest.schema_artifacts] == [
        "179_line_identity_canonical_menu_publication.sql"
    ]


def test_management_defaults_use_merge_copy_and_explicit_product_names() -> None:
    menu = json.loads((PROJECT_ROOT / "config/line_menu.json").read_text(encoding="utf-8"))
    default_labels = [item["label"] for item in menu["menus"][0]["buttons"]]
    page = (PROJECT_ROOT / "ui/pages/07_line_management.py").read_text(encoding="utf-8")
    assert default_labels == ["服務登記", "修改登記資料", "服務說明", "專人客服諮詢"]
    assert '"Rich Menu"' in page
    assert '"LIFF 表單"' in page
    assert '"身分管理"' in page


def test_owner_clear_downgrades_legacy_role_to_prevent_future_staff_relink() -> None:
    source = (PROJECT_ROOT / "infrastructure/mysql/line_identity_owner_adapters.py").read_text(encoding="utf-8")
    assert '_upsert_legacy_role(cursor, line_user_id, "customer")' in source
