"""
File: test_line_delivery_public_query_route.py
Description: 驗證 LINE Delivery 公開查詢 route 的 typed response 與零副作用。
"""

from argparse import Namespace
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
import re
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies.admin_auth import require_line_task_reader
from api.routes import line_tasks
from api.schemas.line_tasks import LineDeliveryPublicSourceType
from domains.line.delivery import LineDeliveryStatus
from domains.line.identities import LineDeliveryTaskId
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.delivery_admin_contracts import (
    LineDeliveryAdminPage,
    LineDeliveryAdminRecord,
    LineDeliveryAttemptRecord,
)

G7_DATABASE = "lu_test_line_delivery_public_query_" + uuid4().hex[:16]
_DISPOSABLE_SCHEMA_PATTERN = re.compile(r"^lu_test_[a-z0-9_]+$")


def _principal() -> AdminPrincipal:
    return AdminPrincipal(1, "admin", "管理員", "system_admin")


def _record() -> LineDeliveryAdminRecord:
    return LineDeliveryAdminRecord(
        task_id=LineDeliveryTaskId(7),
        recipient_type="user",
        recipient_identity="U-secret",
        message_kind="text",
        payload_json='{"text":"secret"}',
        status=LineDeliveryStatus.SENT,
        scheduled_at=datetime(2026, 8, 20, 1, tzinfo=timezone.utc),
        source_aggregate_type="customer_service_ticket",
        source_aggregate_identity="CASE-secret",
        completed_attempts=1,
        maximum_attempts=3,
        next_attempt_at=None,
        provider_message_id="provider-secret",
        error_code="provider-secret-error",
        error_message="provider raw error",
        sent_at=datetime(2026, 8, 20, 1, tzinfo=timezone.utc),
        failed_at=None,
        created_at=datetime(2026, 8, 20, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 20, 1, tzinfo=timezone.utc),
    )


class _Application:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def summary(self, _actor):
        self.calls.append("summary")
        return {"total": 1, "pending": 0, "processing": 0, "sent": 1,
                "retryable_failed": 0, "failed": 0, "cancelled": 0,
                "overdue": 0, "sent_today": 1, "next_run_at": None}

    def list(self, _query, _actor):
        self.calls.append("list")
        return LineDeliveryAdminPage((_record(),), 1, 1, 25)

    def get(self, _task_id, _actor):
        self.calls.append("get")
        return _record(), (LineDeliveryAttemptRecord(
            1, "success", "success", "provider-secret", "error", "raw provider error",
            None, datetime(2026, 8, 20, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 20, 1, tzinfo=timezone.utc), "correlation-secret",
        ),)


def _client(monkeypatch, application: _Application) -> TestClient:
    app = FastAPI()
    app.include_router(line_tasks.router)
    app.dependency_overrides[require_line_task_reader] = _principal
    monkeypatch.setattr(line_tasks, "get_line_delivery_task_admin_application", lambda: application)
    monkeypatch.setattr(line_tasks, "_worker_health", lambda: {"running": True, "status": "healthy"})
    return TestClient(app)


def test_delivery_query_is_server_masked_and_zero_side_effect(monkeypatch) -> None:
    application = _Application()
    client = _client(monkeypatch, application)

    summary = client.get("/api/v1/line/tasks/summary")
    listing = client.get("/api/v1/line/tasks", params={"page": 1, "page_size": 25})
    detail = client.get("/api/v1/line/tasks/7")

    assert summary.status_code == 200
    assert listing.status_code == 200
    assert detail.status_code == 200
    assert set(listing.json()["data"]["items"][0]) == {
        "id", "task_id", "task_type", "source_type", "status", "scheduled_at",
        "completed_attempts", "max_attempts", "next_retry_at", "sent_at", "failed_at",
        "created_at", "updated_at",
    }
    assert set(detail.json()["data"]["attempts"][0]) == {
        "attempt_number", "outcome", "retry_after_seconds", "started_at", "completed_at",
    }
    for response in (summary, listing, detail):
        body = response.text
        for denied in ("U-secret", "CASE-secret", "secret", "provider-secret", "correlation-secret"):
            assert denied not in body
        for key in ("recipient_identity", "payload_json", "provider_message_id", "correlation_id", "error_message"):
            assert key not in body
    assert application.calls == ["summary", "list", "get"]


def test_delivery_query_rejects_identity_and_arbitrary_source_filters(monkeypatch) -> None:
    application = _Application()
    client = _client(monkeypatch, application)

    identity = client.get("/api/v1/line/tasks", params={"user_id": "U-secret"})
    source = client.get("/api/v1/line/tasks", params={"source_type": "not-safe"})

    assert identity.status_code == 422
    assert source.status_code == 422
    assert application.calls == []


def test_delivery_source_groups_are_safe_and_bounded() -> None:
    general_push = line_tasks._source_aggregate_types(
        LineDeliveryPublicSourceType.GENERAL_PUSH
    )
    rich_menu_link = line_tasks._source_aggregate_types(
        LineDeliveryPublicSourceType.RICH_MENU_LINK
    )

    assert "line_push" in general_push
    assert "customer_service_ticket" in general_push
    assert "contract_external_signing_session" in general_push
    assert "rich_menu_link" not in general_push
    assert rich_menu_link == ("rich_menu_link",)

    contract = line_tasks._source_aggregate_types(
        LineDeliveryPublicSourceType.CONTRACT
    )
    assert contract == (
        "contract_document_version",
        "contract_external_signing_session",
    )
    assert line_tasks._public_source_type(
        "contract_external_signing_session"
    ) is LineDeliveryPublicSourceType.CONTRACT


@pytest.mark.parametrize(
    "source_aggregate_type,expected_type",
    [(name, kind) for kind, names in {
        'matching': ('matching_schedule_recipient', 'matching_schedule_snapshot', 'candidate_contact_question',
                     'candidate_contact_answer', 'candidate_weekly_service_information', 'service_start_inquiry'),
        'finance': ('client_deposit_reminder', 'client_deposit_settled', 'manual_payment_overdue_reminder',
                    'client_second_payment_reminder','client_second_payment_settled'),
        'order': ('order_service_start_day','order_service_start_day_response','order_service_completion'),
        'assignment': ('manual_service_day_log_reminder', 'service_start_schedule'),
        'group_invitation': ('service_start_invitation',),
    }.items() for name in names],
)
def test_matching_schedule_sources_project_to_bounded_matching_label(
    monkeypatch,
    source_aggregate_type: str,
    expected_type: str,
) -> None:
    class _MatchingApplication(_Application):
        def list(self, _query, _actor):
            record = replace(_record(), source_aggregate_type=source_aggregate_type)
            return LineDeliveryAdminPage((record,), 1, 1, 25)
        def get(self, _task_id, _actor):
            record, attempts=super().get(_task_id,_actor)
            return replace(record,source_aggregate_type=source_aggregate_type),attempts

    client = _client(monkeypatch, _MatchingApplication())
    response = client.get("/api/v1/line/tasks")

    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["source_type"] == expected_type
    assert item["task_type"] == expected_type
    assert "U-secret" not in response.text
    assert "CASE-secret" not in response.text
    assert "provider-secret" not in response.text
    detail=client.get('/api/v1/line/tasks/7')
    assert detail.status_code==200 and detail.json()['data']['task']['source_type']==expected_type


@pytest.mark.parametrize('category,required,excluded',[
    ('review','contract_document_version','client_second_payment_reminder'),
    ('reminder','client_second_payment_reminder','customer_service_ticket'),
    ('support','customer_service_ticket','order_service_completion'),
])
def test_public_category_filters_the_original_owner_before_counting_and_pagination(monkeypatch,category,required,excluded):
    queries=[]
    class Reader(_Application):
        def list(self,query,actor):
            queries.append(query);return LineDeliveryAdminPage((),41,2,6)
    response=_client(monkeypatch,Reader()).get('/api/v1/line/tasks',params={'category':category,'page':2,'page_size':6})
    assert response.status_code==200 and response.json()['data']['total']==41
    assert required in queries[0].source_aggregate_types and excluded not in queries[0].source_aggregate_types
    assert queries[0].page==2 and queries[0].page_size==6


def test_incompatible_category_and_source_returns_zero_without_an_unfiltered_read(monkeypatch):
    application=_Application();client=_client(monkeypatch,application)
    response=client.get('/api/v1/line/tasks',params={'category':'review','source_type':'finance'})
    assert response.status_code==200 and response.json()['data']['total']==0 and application.calls==[]
    assert client.get('/api/v1/line/tasks',params={'category':'not-a-category'}).status_code==422


def test_scheduling_leave_notification_projects_to_bounded_assignment_label(
    monkeypatch,
) -> None:
    class _LeaveNotificationApplication(_Application):
        def list(self, _query, _actor):
            record = replace(
                _record(), source_aggregate_type="scheduling_staff_leave_request"
            )
            return LineDeliveryAdminPage((record,), 1, 1, 25)

    client = _client(monkeypatch, _LeaveNotificationApplication())
    response = client.get("/api/v1/line/tasks")

    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["source_type"] == "assignment"
    assert item["task_type"] == "assignment"
    assert "U-secret" not in response.text
    assert "CASE-secret" not in response.text


def test_provisional_registration_projects_to_bounded_identity_label(
    monkeypatch,
) -> None:
    class _ProvisionalRegistrationApplication(_Application):
        def list(self, _query, _actor):
            record = replace(
                _record(), source_aggregate_type="provisional_registration"
            )
            return LineDeliveryAdminPage((record,), 1, 1, 25)

    client = _client(monkeypatch, _ProvisionalRegistrationApplication())
    response = client.get("/api/v1/line/tasks")

    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["source_type"] == "identity"
    assert item["task_type"] == "identity"
    assert "U-secret" not in response.text
    assert "CASE-secret" not in response.text


def test_delivery_query_malformed_public_record_fails_closed(monkeypatch) -> None:
    class _MalformedApplication(_Application):
        def list(self, _query, _actor):
            record = replace(_record(), source_aggregate_type="unregistered_source")
            return LineDeliveryAdminPage((record,), 1, 1, 25)

    client = _client(monkeypatch, _MalformedApplication())
    response = client.get("/api/v1/line/tasks")

    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "line_delivery_query_invalid_result"
    assert response.json()["detail"]["error"]["retryable"] is False
    assert "unregistered_source" not in response.text
    assert "provider-secret" not in response.text


def test_delivery_public_query_openapi_declares_typed_error_responses(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(line_tasks.router)
    openapi = app.openapi()

    for path in ("/api/v1/line/tasks/summary", "/api/v1/line/tasks"):
        responses = openapi["paths"][path]["get"]["responses"]
        assert {"401", "403", "422", "503"} <= set(responses)
        assert responses["503"]["content"]["application/json"]["schema"]["$ref"].endswith(
            "/GlobalTypedErrorResponseView"
        )

    detail_responses = openapi["paths"]["/api/v1/line/tasks/{task_id}"]["get"]["responses"]
    assert {"401", "403", "404", "422", "503"} <= set(detail_responses)


class _TrackedConnection:
    def __init__(self, connection, counters: dict[str, int]) -> None:
        self._connection = connection
        self._counters = counters

    def __getattr__(self, name):
        return getattr(self._connection, name)

    @contextmanager
    def cursor(self, *args, **kwargs):
        with self._connection.cursor(*args, **kwargs) as cursor:
            yield _ReadOnlyTrackedCursor(cursor, self._counters)

    def commit(self):
        self._counters["commit"] += 1
        return self._connection.commit()

    def rollback(self):
        self._counters["rollback"] += 1
        return self._connection.rollback()


class _ReadOnlyTrackedCursor:
    def __init__(self, cursor, counters):
        self._cursor = cursor
        self._counters = counters

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def execute(self, sql, args=None):
        self._counters["queries"] += 1
        if not sql.lstrip().upper().startswith(("SELECT ", "SHOW ")):
            self._counters["writes"] += 1
            raise AssertionError("delivery query attempted a database write")
        return self._cursor.execute(sql, args)

    def executemany(self, *args, **kwargs):
        self._counters["writes"] += 1
        raise AssertionError("delivery query attempted a batch write")


def _assert_disposable_schema_name(name: str) -> None:
    if name.lower() == "union_db":
        raise ValueError("production schema is not an allowed disposable target")
    if _DISPOSABLE_SCHEMA_PATTERN.fullmatch(name) is None:
        raise ValueError("schema name must match the lu_test_* disposable guard")


class _DisposableSchemaLease:
    """Track one explicitly created schema and clean it up without masking failures."""

    def __init__(self, admin, name: str) -> None:
        self._admin = admin
        self._name = name
        self._created = False

    def __enter__(self):
        _assert_disposable_schema_name(self._name)
        if self._admin.schema_exists(self._name):
            raise RuntimeError("disposable schema already exists; refusing to drop it")
        self._admin.create_schema(self._name)
        self._created = True
        return self._name

    def __exit__(self, exc_type, exc_value, traceback):
        if not self._created:
            return False
        try:
            self._admin.drop_schema(self._name)
        except BaseException as cleanup_error:
            if exc_value is not None:
                raise ExceptionGroup(
                    "disposable schema cleanup failed after test failure",
                    [exc_value, cleanup_error],
                )
            raise
        return False


class _MySqlDisposableSchemaAdmin:
    """Perform guarded, parameterized existence checks and identifier-safe DDL."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def _connection(self):
        import pymysql

        return pymysql.connect(
            host=self._values["LABOR_UNION_TEST_MYSQL_HOST"],
            port=int(self._values["LABOR_UNION_TEST_MYSQL_PORT"]),
            user=self._values["LABOR_UNION_TEST_MYSQL_USER"],
            password=self._values["LABOR_UNION_TEST_MYSQL_PASSWORD"],
            charset="utf8mb4",
        )

    @staticmethod
    def _quoted_name(name: str) -> str:
        _assert_disposable_schema_name(name)
        return f"`{name}`"

    def schema_exists(self, name: str) -> bool:
        _assert_disposable_schema_name(name)
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name=%s",
                    (name,),
                )
                return cursor.fetchone() is not None
        finally:
            connection.close()

    def create_schema(self, name: str) -> None:
        from scripts.bootstrap_disposable_mysql_schema import bootstrap

        _assert_disposable_schema_name(name)
        bootstrap(Namespace(
            host=self._values["LABOR_UNION_TEST_MYSQL_HOST"],
            port=int(self._values["LABOR_UNION_TEST_MYSQL_PORT"]),
            user=self._values["LABOR_UNION_TEST_MYSQL_USER"],
            password=self._values["LABOR_UNION_TEST_MYSQL_PASSWORD"],
            database=name,
            confirm_database=name,
        ))

    def drop_schema(self, name: str) -> None:
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE {self._quoted_name(name)}")
            connection.commit()
        finally:
            connection.close()


def _g7_database_values() -> dict[str, str]:
    names = (
        "LABOR_UNION_TEST_MYSQL_HOST",
        "LABOR_UNION_TEST_MYSQL_PORT",
        "LABOR_UNION_TEST_MYSQL_USER",
        "LABOR_UNION_TEST_MYSQL_PASSWORD",
        "LABOR_UNION_TEST_MYSQL_DATABASE",
    )
    values = {name: os.getenv(name, "").strip() for name in names}
    if any(not value for value in values.values()):
        pytest.skip("BLOCKED_ENGINE_EVIDENCE: disposable MySQL environment is incomplete")
    if values["LABOR_UNION_TEST_MYSQL_DATABASE"].lower() == "union_db":
        pytest.skip("BLOCKED_ENGINE_EVIDENCE: union_db is prohibited as a disposable source")
    db_names = {
        "DB_HOST": "LABOR_UNION_TEST_MYSQL_HOST",
        "DB_PORT": "LABOR_UNION_TEST_MYSQL_PORT",
        "DB_USER": "LABOR_UNION_TEST_MYSQL_USER",
        "DB_PASSWORD": "LABOR_UNION_TEST_MYSQL_PASSWORD",
        "DB_DATABASE": "LABOR_UNION_TEST_MYSQL_DATABASE",
    }
    for db_name, source_name in db_names.items():
        existing = os.getenv(db_name, "").strip()
        if existing and existing != values[source_name]:
            pytest.skip(f"BLOCKED_ENGINE_EVIDENCE: {db_name} conflicts with disposable test env")
    _assert_disposable_schema_name(values["LABOR_UNION_TEST_MYSQL_DATABASE"])
    return values


@contextmanager
def _managed_g7_database(monkeypatch):
    values = _g7_database_values()
    admin = _MySqlDisposableSchemaAdmin(values)
    with _DisposableSchemaLease(admin, G7_DATABASE):
        monkeypatch.setenv("DB_HOST", values["LABOR_UNION_TEST_MYSQL_HOST"])
        monkeypatch.setenv("DB_PORT", values["LABOR_UNION_TEST_MYSQL_PORT"])
        monkeypatch.setenv("DB_USER", values["LABOR_UNION_TEST_MYSQL_USER"])
        monkeypatch.setenv("DB_PASSWORD", values["LABOR_UNION_TEST_MYSQL_PASSWORD"])
        monkeypatch.setenv("DB_DATABASE", G7_DATABASE)
        yield values


class _FakeSchemaAdmin:
    def __init__(self, existing=(), *, fail_drop=False) -> None:
        self.existing = set(existing)
        self.created: list[str] = []
        self.dropped: list[str] = []
        self.fail_drop = fail_drop

    def schema_exists(self, name: str) -> bool:
        return name in self.existing

    def create_schema(self, name: str) -> None:
        self.created.append(name)

    def drop_schema(self, name: str) -> None:
        if self.fail_drop:
            raise RuntimeError("cleanup unavailable")
        self.dropped.append(name)


def test_disposable_schema_preexisting_fails_closed_without_drop() -> None:
    admin = _FakeSchemaAdmin(existing=(G7_DATABASE,))

    with pytest.raises(RuntimeError, match="already exists"):
        with _DisposableSchemaLease(admin, G7_DATABASE):
            pytest.fail("pre-existing schema must not enter the body")

    assert admin.created == []
    assert admin.dropped == []


def test_disposable_schema_created_success_is_dropped() -> None:
    admin = _FakeSchemaAdmin()

    with _DisposableSchemaLease(admin, G7_DATABASE):
        pass

    assert admin.created == [G7_DATABASE]
    assert admin.dropped == [G7_DATABASE]


def test_disposable_schema_test_failure_still_drops() -> None:
    admin = _FakeSchemaAdmin()

    with pytest.raises(ValueError, match="test failed"):
        with _DisposableSchemaLease(admin, G7_DATABASE):
            raise ValueError("test failed")

    assert admin.dropped == [G7_DATABASE]


def test_disposable_schema_cleanup_failure_preserves_primary_failure() -> None:
    admin = _FakeSchemaAdmin(fail_drop=True)

    with pytest.raises(ExceptionGroup) as raised:
        with _DisposableSchemaLease(admin, G7_DATABASE):
            raise ValueError("primary failure")

    errors = raised.value.exceptions
    assert isinstance(errors[0], ValueError)
    assert str(errors[0]) == "primary failure"
    assert isinstance(errors[1], RuntimeError)
    assert str(errors[1]) == "cleanup unavailable"


def test_disposable_schema_rejects_union_db_before_admin_calls() -> None:
    admin = _FakeSchemaAdmin()

    with pytest.raises(ValueError, match="production schema"):
        with _DisposableSchemaLease(admin, "union_db"):
            pass

    assert admin.created == []
    assert admin.dropped == []


def test_g7_explicit_local_root_configuration_is_allowed(monkeypatch):
    # Current migration contract section 9.1 permits development credentials,
    # including root; the explicit disposable target remains mandatory.
    values = {"HOST": "127.0.0.1", "PORT": "3306", "USER": "root",
              "PASSWORD": "synthetic-only", "DATABASE": G7_DATABASE}
    for name, value in values.items():
        monkeypatch.setenv("LABOR_UNION_TEST_MYSQL_" + name, value)
        monkeypatch.setenv("DB_" + name, value)
    assert _g7_database_values()["LABOR_UNION_TEST_MYSQL_USER"] == "root"


def _with_g7_database(test_function):
    def wrapped(monkeypatch):
        from infrastructure.mysql import mysql_adapter

        original_db_config = dict(mysql_adapter.DB_CONFIG)
        try:
            with _managed_g7_database(monkeypatch) as values:
                # Set the adapter before importing the production composition,
                # so imports and lifespan can only see this leased database.
                mysql_adapter.DB_CONFIG.update(
                    host=values["LABOR_UNION_TEST_MYSQL_HOST"],
                    port=int(values["LABOR_UNION_TEST_MYSQL_PORT"]),
                    user=values["LABOR_UNION_TEST_MYSQL_USER"],
                    password=values["LABOR_UNION_TEST_MYSQL_PASSWORD"],
                    database=G7_DATABASE,
                )
                monkeypatch.setenv("APP_ENV", "test")
                monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "")
                monkeypatch.setenv("REDIS_URL", "")
                return test_function(monkeypatch, values)
        finally:
            mysql_adapter.DB_CONFIG.clear()
            mysql_adapter.DB_CONFIG.update(original_db_config)

    wrapped.__name__ = test_function.__name__
    wrapped.__doc__ = test_function.__doc__
    return wrapped


@pytest.mark.integration
@_with_g7_database
def test_delivery_query_g7_uses_production_app_and_real_repository(monkeypatch, values) -> None:
    from api.dependencies import line_runtime
    from api.main import app as production_app
    from domains.line.canonical_payload import canonical_line_payload_json
    from domains.line.delivery import (
        LineDeliveryRequest,
        LineMessageKind,
        LineRecipient,
        LineRecipientType,
    )
    from domains.line.identities import LineUserId
    from infrastructure.mysql import line_unit_of_work, mysql_adapter
    from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
    from shared_kernel.identities import CorrelationId, IdempotencyKey

    original_db_config = dict(mysql_adapter.DB_CONFIG)
    mysql_adapter.DB_CONFIG.update(
        host=values["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(values["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=values["LABOR_UNION_TEST_MYSQL_USER"],
        password=values["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=G7_DATABASE,
    )
    # Use real owner persistence for all five current sources plus enough
    # review/support rows to prove category filtering happens before paging.
    kinds = (
        ("order_service_start_day", "order", "reminder"),
        ("order_service_start_day_response", "order", "reminder"),
        ("order_service_completion", "order", "reminder"),
        ("client_second_payment_reminder", "finance", "reminder"),
        ("client_second_payment_settled", "finance", "reminder"),
        *(("contract_document_version", "contract", "review"),) * 3,
        *(("customer_service_ticket", "customer_service", "support"),) * 5,
    )
    expected = {}
    now = datetime.now(timezone.utc)
    seed_connection = mysql_adapter.get_connection()
    try:
        repository = MySqlLineDeliveryTaskRepository(seed_connection)
        for index, (source, public_type, category) in enumerate(kinds):
            result = repository.enqueue(LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, LineUserId("U-g7-safe")),
                LineMessageKind.TEXT,
                canonical_line_payload_json({"type": "text", "text": "g7-safe"}),
                now + timedelta(days=1, minutes=index),
                IdempotencyKey(f"g7-line-delivery-query-{index}"),
                CorrelationId("g7-private-correlation"), source, "CASE-G7-SAFE",
            ))
            expected[result.task_id.value] = (public_type, category)
        task_id = result.task_id.value
        # Synthetic failed attempt exercises masking of actual stored provider
        # details without calling a transport or running a delivery worker.
        with seed_connection.cursor() as cursor:
            cursor.execute(
                "UPDATE line_delivery_tasks SET processing_status='failed',"
                "completed_attempts=1,failed_at_utc=%s,provider_message_id=%s,"
                "error_code=%s,error_message=%s WHERE id=%s",
                (now, "g7-private-provider", "g7-private-error", "g7-private-message", task_id),
            )
            cursor.execute(
                "INSERT INTO line_delivery_attempt_events "
                "(task_id,attempt_number,outcome,provider_outcome_type,provider_message_id,"
                "error_code,error_message,retry_after_seconds,started_at_utc,completed_at_utc,"
                "idempotency_key,correlation_id) VALUES (%s,1,'terminal_failure',"
                "'rejected',%s,%s,%s,NULL,%s,%s,%s,%s)",
                (task_id, "g7-private-provider", "g7-private-error", "g7-private-message",
                 now, now, "g7-private-attempt", "g7-private-correlation"),
            )
        seed_connection.commit()
    finally:
        seed_connection.close()

    counters = {"commit": 0, "rollback": 0, "queries": 0, "writes": 0, "wakeup": 0}
    original_get_connection = mysql_adapter.get_connection

    def tracked_connection():
        assert mysql_adapter.DB_CONFIG["database"] == G7_DATABASE
        return _TrackedConnection(original_get_connection(), counters)

    def fail_wakeup(*args, **kwargs):
        # A publisher error can be swallowed by best-effort wrappers. Count the
        # invocation as well, so swallowing cannot make this assertion pass.
        counters["wakeup"] += 1
        raise AssertionError("query invoked wakeup")

    def snapshot():
        connection = original_get_connection()
        try:
            with connection.cursor() as cursor:
                result = {}
                for table in ("line_delivery_tasks", "line_delivery_attempt_events",
                              "line_domain_outbox", "line_domain_audit_events",
                              "line_command_receipts", "line_rich_menu_publication_tasks"):
                    cursor.execute(f"SELECT * FROM `{table}`")
                    result[table] = tuple(sorted(
                        json.dumps(row, sort_keys=True, default=str) for row in cursor.fetchall()
                    ))
                return result
        finally:
            connection.close()

    line_runtime.get_line_delivery_task_admin_application.cache_clear()
    monkeypatch.setenv("LINE_WEBHOOK_RUNTIME_MODE", "canonical")
    monkeypatch.setenv("LINE_WORKER_RUNTIME_MODE", "canonical")
    production_app.dependency_overrides[require_line_task_reader] = _principal
    responses = []
    try:
        with TestClient(production_app) as client:
            # Keep the real lifespan. Measure after startup and never reset
            # counters during queries; bootstrap/fixture writes are separate.
            before = snapshot()
            with monkeypatch.context() as query_patch:
                query_patch.setattr(mysql_adapter, "get_connection", tracked_connection)
                query_patch.setattr(line_unit_of_work, "get_connection", tracked_connection)
                query_patch.setattr(line_tasks, "get_connection", tracked_connection)
                query_patch.setattr(line_tasks, "get_line_wakeup_publisher", fail_wakeup)
                query_patch.setattr(line_runtime, "publish_line_wakeup_best_effort", fail_wakeup)

                def get(path="", **params):
                    response = client.get("/api/v1/line/tasks" + path, params=params)
                    assert response.status_code == 200, response.text
                    responses.append(response)
                    return response.json()["data"]

                summary = get("/summary")
                assert summary["total"] == len(expected)
                assert summary["pending"] == len(expected) - 1 and summary["failed"] == 1
                listing = get(page=1, page_size=100)
                assert listing["total"] == len(expected)
                assert {item["id"] for item in listing["items"]} == set(expected)
                assert {item["source_type"] for item in get(page=1, page_size=2)["items"]} == {"customer_service"}

                # Every seeded source, including the five formerly missing
                # mappings, must open through the real public detail endpoint.
                for identity, (public_type, _) in expected.items():
                    detail = get("/" + str(identity))
                    assert detail["task"]["id"] == identity
                    assert detail["task"]["source_type"] == public_type
                assert get("/" + str(task_id))["attempts"][0]["outcome"] == "terminal_failure"

                for category, total in (("review", 3), ("reminder", 5), ("support", 5)):
                    seen = []
                    for page in range(1, (total + 1) // 2 + 1):
                        data = get(category=category, page=page, page_size=2)
                        assert data["total"] == total and data["total_pages"] == (total + 1) // 2
                        assert len(data["items"]) == min(2, total - (page - 1) * 2)
                        assert all(expected[item["id"]][1] == category for item in data["items"])
                        seen.extend(item["id"] for item in data["items"])
                    assert len(set(seen)) == total
                    assert set(seen) == {identity for identity, (_, group) in expected.items() if group == category}
                    assert get(category=category, page=10, page_size=2)["items"] == []
                combined = get(category="reminder", source_type="finance", page=1, page_size=1)
                assert combined["total"] == 2 and combined["items"][0]["source_type"] == "finance"
                assert get(category="review", source_type="finance")["total"] == 0
                assert get(source_type="general_push", page_size=100)["total"] == 8
                assert counters["queries"] > 0 and counters["rollback"] > 0
                assert counters["commit"] == counters["writes"] == counters["wakeup"] == 0
            assert snapshot() == before
    finally:
        production_app.dependency_overrides.pop(require_line_task_reader, None)
        line_runtime.get_line_delivery_task_admin_application.cache_clear()
        mysql_adapter.DB_CONFIG.clear()
        mysql_adapter.DB_CONFIG.update(original_db_config)

    for response in responses:
        body = response.text
        for value in ("U-g7-safe", "CASE-G7-SAFE", "g7-safe", "g7-private"):
            assert value not in body
        for field in ("recipient_identity", "payload_json", "payload_snapshot", "source_aggregate_identity",
                      "provider_message_id", "provider_outcome_type", "correlation_id", "error_code", "error_message"):
            assert field not in body
