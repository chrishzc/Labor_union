"""Root-payload Case Import proof against the disposable MySQL schema."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
from threading import Barrier
from uuid import uuid4

import pytest

from domains.bootstrap.case_architecture import (
    CaseArchitectureBootstrapIntent,
    ClientPaymentTermsRootFacts,
)
from domains.case_import.case_import import (
    CaseImportIntent,
    ClientImportAttribute,
    ImportedOrderRootFacts,
)
from infrastructure.mysql.case_import_repository import (
    CaseImportMySqlUnitOfWork,
    MySqlCaseImportRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.case_import.case_import_workflow import ApplyCaseImport, CaseImportWorkflow
from subsystems.case_import.case_import_workflow import CaseImportStorageError, CaseImportWorkflowError


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_case_import_creates_canonical_roots_and_replays_one_receipt():
    case_no = f"CI-{uuid4().hex[:16]}"
    intent = _import_intent(case_no)
    connection = get_connection()
    try:
        workflow = CaseImportWorkflow(
            MySqlCaseImportRepository(connection),
            lambda: CaseImportMySqlUnitOfWork(connection),
        )
        preview = workflow.preview(intent, CorrelationId(f"preview-{case_no}"))
        command = _apply_command(intent, preview.fingerprint, case_no)

        first = workflow.apply(command)
        second = workflow.apply(command)

        assert second == first
        assert first.case_no == case_no
        _assert_canonical_root_graph(connection, case_no, first.client_id)
    finally:
        connection.close()


def test_case_import_consumes_provisional_registration_once():
    case_no = f"CIP-{uuid4().hex[:15]}"
    line_user_id = f"U-{uuid4().hex}"
    connection = get_connection()
    try:
        registration_id, client_id, beclass_record_id = _create_provisional_roots(
            connection, line_user_id
        )
        intent = _import_intent(
            case_no, line_user_id=line_user_id, provisional_registration_id=registration_id
        )
        workflow = CaseImportWorkflow(
            MySqlCaseImportRepository(connection),
            lambda: CaseImportMySqlUnitOfWork(connection),
        )
        preview = workflow.preview(intent, CorrelationId(f"preview-{case_no}"))
        command = _apply_command(intent, preview.fingerprint, case_no)

        first = workflow.apply(command)
        second = workflow.apply(command)

        assert second == first
        assert first.client_id == client_id
        assert first.provisional_registration_id == registration_id
        assert first.provisional_case_issue_event_id is not None
        _assert_provisional_issue_graph(
            connection, case_no, registration_id, client_id, beclass_record_id
        )
    finally:
        connection.close()


def test_provisional_consume_failure_rolls_back_case_import(monkeypatch):
    case_no = f"CIR-{uuid4().hex[:15]}"
    line_user_id = f"U-{uuid4().hex}"
    connection = get_connection()
    try:
        registration_id, client_id, beclass_record_id = _create_provisional_roots(
            connection, line_user_id
        )
        intent = _import_intent(
            case_no, line_user_id=line_user_id, provisional_registration_id=registration_id
        )
        repository = MySqlCaseImportRepository(connection)
        workflow = CaseImportWorkflow(repository, lambda: CaseImportMySqlUnitOfWork(connection))
        preview = workflow.preview(intent, CorrelationId(f"preview-{case_no}"))
        monkeypatch.setattr(
            repository,
            "consume_provisional_registration",
            lambda *_: (_ for _ in ()).throw(CaseImportStorageError("injected", retryable=False)),
        )

        with pytest.raises(CaseImportWorkflowError, match="transaction_failed"):
            workflow.apply(_apply_command(intent, preview.fingerprint, case_no))

        _assert_provisional_rollback(connection, case_no, registration_id, client_id, beclass_record_id, line_user_id)
    finally:
        connection.close()


def test_competing_case_imports_consume_one_provisional_registration():
    case_no = f"CIC-{uuid4().hex[:15]}"
    line_user_id = f"U-{uuid4().hex}"
    setup_connection = get_connection()
    try:
        registration_id, client_id, beclass_record_id = _create_provisional_roots(
            setup_connection, line_user_id
        )
        intent = _import_intent(
            case_no, line_user_id=line_user_id, provisional_registration_id=registration_id
        )
        preview = CaseImportWorkflow(
            MySqlCaseImportRepository(setup_connection),
            lambda: CaseImportMySqlUnitOfWork(setup_connection),
        ).preview(intent, CorrelationId(f"preview-{case_no}"))
    finally:
        setup_connection.close()

    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(
            lambda suffix: _concurrent_apply(intent, preview.fingerprint, case_no, suffix, barrier),
            ("first", "second"),
        ))

    assert outcomes.count("success") == 1
    assert outcomes.count("conflict") == 1
    verification_connection = get_connection()
    try:
        _assert_provisional_issue_graph(
            verification_connection, case_no, registration_id, client_id, beclass_record_id
        )
    finally:
        verification_connection.close()


def _import_intent(
    case_no: str, *, line_user_id: str | None = None, provisional_registration_id: int | None = None
) -> CaseImportIntent:
    start_date = date(2026, 8, 1)
    terms = ClientPaymentTermsRootFacts(
        "client-policy-v1",
        MoneyNTD(400),
        5,
        date(2026, 7, 20),
        start_date,
    )
    return CaseImportIntent(
        case_no,
        _client_attributes(case_no, line_user_id),
        ImportedOrderRootFacts(
            case_no,
            5,
            8,
            start_date,
            date(2026, 8, 5),
            time(9),
            time(17),
            0,
        ),
        CaseArchitectureBootstrapIntent(case_no, terms, "approved-rates-v1"),
        provisional_registration_id,
    )


def _client_attributes(case_no: str, line_user_id: str | None) -> tuple[ClientImportAttribute, ...]:
    attributes = [
        ClientImportAttribute("case_no", case_no),
        ClientImportAttribute("created_at", datetime(2026, 7, 1, 9, 0)),
        ClientImportAttribute("identity_status", "一般市民"),
        ClientImportAttribute("name", "驗證案件客戶"),
        ClientImportAttribute("service_time", "09:00-17:00"),
    ]
    if line_user_id is not None:
        attributes.append(ClientImportAttribute("line_id", line_user_id))
    return tuple(sorted(attributes, key=lambda attribute: attribute.name))


def _apply_command(intent, preview_fingerprint, case_no: str, suffix: str = "") -> ApplyCaseImport:
    identity = f"case-import-{case_no}-{suffix}".rstrip("-")
    return ApplyCaseImport(
        intent,
        ExpectedVersion(0),
        preview_fingerprint,
        IdempotencyKey(identity),
        ActorContext("validation-case-import"),
        "import verified root payload",
        CorrelationId(identity),
    )


def _concurrent_apply(intent, preview_fingerprint, case_no, suffix, barrier):
    connection = get_connection()
    try:
        workflow = CaseImportWorkflow(
            MySqlCaseImportRepository(connection),
            lambda: CaseImportMySqlUnitOfWork(connection),
        )
        barrier.wait()
        workflow.apply(_apply_command(intent, preview_fingerprint, case_no, suffix))
        return "success"
    except CaseImportWorkflowError:
        return "conflict"
    finally:
        connection.close()


def _assert_canonical_root_graph(connection, case_no: str, client_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,case_no FROM clients WHERE case_no=%s",
            (case_no,),
        )
        assert cursor.fetchone() == {"id": client_id, "case_no": case_no}
        cursor.execute(
            "SELECT status,lifecycle_version,service_days FROM orders WHERE case_no=%s",
            (case_no,),
        )
        assert cursor.fetchone() == {
            "status": "洽談中",
            "lifecycle_version": 0,
            "service_days": 5,
        }
        for table_name in (
            "case_architecture_bootstrap_events",
            "case_import_events",
            "case_import_receipts",
        ):
            cursor.execute(f"SELECT COUNT(*) AS count FROM {table_name} WHERE case_no=%s", (case_no,))
            assert cursor.fetchone() == {"count": 1}


def _create_provisional_roots(connection, line_user_id: str) -> tuple[int, int, int]:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO clients (name,line_user_id) VALUES (%s,%s)",
            ("暫存驗證客戶", line_user_id),
        )
        client_id = int(cursor.lastrowid)
        cursor.execute("INSERT INTO beclass_records (name) VALUES (%s)", ("暫存驗證客戶",))
        beclass_record_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO provisional_client_registrations "
            "(line_user_id,active_line_user_id,payload_fingerprint,status,client_id,beclass_record_id) "
            "VALUES (%s,%s,%s,'submitted',%s,%s)",
            (line_user_id, line_user_id, "a" * 64, client_id, beclass_record_id),
        )
        registration_id = int(cursor.lastrowid)
    connection.commit()
    return registration_id, client_id, beclass_record_id


def _assert_provisional_issue_graph(connection, case_no, registration_id, client_id, beclass_record_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id,status,active_line_user_id FROM provisional_client_registrations WHERE id=%s", (registration_id,))
        assert cursor.fetchone() == {"id": registration_id, "status": "case_issued", "active_line_user_id": None}
        cursor.execute("SELECT query_no FROM beclass_records WHERE id=%s", (beclass_record_id,))
        assert cursor.fetchone() == {"query_no": case_no}
        cursor.execute("SELECT COUNT(*) AS count FROM clients WHERE id=%s AND case_no=%s", (client_id, case_no))
        assert cursor.fetchone() == {"count": 1}
        cursor.execute("SELECT COUNT(*) AS count FROM provisional_registration_case_issue_events WHERE registration_id=%s", (registration_id,))
        assert cursor.fetchone() == {"count": 1}


def _assert_provisional_rollback(connection, case_no, registration_id, client_id, beclass_record_id, line_user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT case_no FROM clients WHERE id=%s", (client_id,))
        assert cursor.fetchone() == {"case_no": None}
        cursor.execute("SELECT COUNT(*) AS count FROM orders WHERE case_no=%s", (case_no,))
        assert cursor.fetchone() == {"count": 0}
        cursor.execute("SELECT query_no FROM beclass_records WHERE id=%s", (beclass_record_id,))
        assert cursor.fetchone() == {"query_no": None}
        cursor.execute("SELECT status,active_line_user_id FROM provisional_client_registrations WHERE id=%s", (registration_id,))
        assert cursor.fetchone() == {"status": "submitted", "active_line_user_id": line_user_id}
        cursor.execute("SELECT COUNT(*) AS count FROM provisional_registration_case_issue_events WHERE registration_id=%s", (registration_id,))
        assert cursor.fetchone() == {"count": 0}
