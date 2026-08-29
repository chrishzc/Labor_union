"""
File: tests/test_case_import_disposable_mysql_e2e.py
Description: 以 disposable MySQL 驗證 Case Import 正式根事實與待補件帳務隔離。
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
from threading import Barrier
from uuid import uuid4

import pandas as pd
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
from infrastructure.mysql.hcm_workbook_import_repository import HcmWorkbookImportRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from scripts.imports.import_client_hcm import HcmLegacyRowIntake
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.case_import.case_import_workflow import ApplyCaseImport, CaseImportWorkflow
from subsystems.case_import.case_import_workflow import CaseImportStorageError, CaseImportWorkflowError
from subsystems.case_import.hcm_workbook_import import HcmWorkbookImportService


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


def test_partial_case_import_creates_formal_case_without_bootstrap():
    case_no = f"CIPART-{uuid4().hex[:12]}"
    intent = CaseImportIntent(
        case_no,
        tuple(sorted((
            ClientImportAttribute("case_no", case_no),
            ClientImportAttribute("name", "部分資料客戶"),
            ClientImportAttribute("phone", None),
        ), key=lambda attribute: attribute.name)),
        None,
        None,
    )
    connection = get_connection()
    try:
        workflow = CaseImportWorkflow(
            MySqlCaseImportRepository(connection),
            lambda: CaseImportMySqlUnitOfWork(connection),
        )
        preview = workflow.preview(intent, CorrelationId(f"preview-{case_no}"))
        receipt = workflow.apply(_apply_command(intent, preview.fingerprint, case_no))

        assert receipt.bootstrap_event_id is None
        with connection.cursor() as cursor:
            cursor.execute("SELECT name,phone FROM clients WHERE case_no=%s", (case_no,))
            assert cursor.fetchone() == {"name": "部分資料客戶", "phone": None}
            cursor.execute("SELECT status,service_days FROM orders WHERE case_no=%s", (case_no,))
            assert cursor.fetchone() == {"status": "待補件", "service_days": None}
            cursor.execute("SELECT bootstrap_event_id FROM case_import_events WHERE case_no=%s", (case_no,))
            assert cursor.fetchone() == {"bootstrap_event_id": None}
            cursor.execute("SELECT COUNT(*) AS count FROM client_obligations WHERE case_no=%s", (case_no,))
            assert cursor.fetchone() == {"count": 0}
            cursor.execute("SELECT COUNT(*) AS count FROM staff_obligations WHERE case_no=%s", (case_no,))
            assert cursor.fetchone() == {"count": 0}
    finally:
        connection.close()


def test_valid_hcm_workbook_creates_complete_formal_case_and_bootstrap(tmp_path):
    case_no = f"HCM-{uuid4().hex[:16]}"
    workbook_path = tmp_path / "hcm-valid.xlsx"
    pd.DataFrame([_valid_hcm_workbook_row(case_no)]).to_excel(
        workbook_path, sheet_name="任意資料頁", index=False,
    )
    connection = get_connection()
    try:
        service = HcmWorkbookImportService(
            HcmWorkbookImportRepository(connection), HcmLegacyRowIntake(connection),
            lambda: MySqlUnitOfWork(connection),
        )
        frame = service.load_frame(str(workbook_path))
        assert frame is not None
        preview = service.preview(frame, str(workbook_path))
        receipt = service.apply(
            frame, str(workbook_path), preview.preview_fingerprint,
            f"hcm-e2e:{case_no}", "test-runner", f"hcm-e2e:{case_no}",
        )

        assert preview.ready_count == 1
        assert receipt.inserted_count + receipt.inserted_with_warning_count == 1
        with connection.cursor() as cursor:
            cursor.execute("SELECT status FROM orders WHERE case_no=%s", (case_no,))
            assert cursor.fetchone() == {"status": "洽談中"}
            cursor.execute("SELECT bootstrap_event_id FROM case_import_events WHERE case_no=%s", (case_no,))
            assert cursor.fetchone()["bootstrap_event_id"] is not None
    finally:
        connection.close()


def test_dirty_hcm_workbook_writes_parseable_client_fields_and_keeps_invalid_field_null(tmp_path):
    case_no = f"HCM-DIRTY-{uuid4().hex[:16]}"
    workbook_path = tmp_path / "hcm-dirty.xlsx"
    row = _valid_hcm_workbook_row(case_no)
    row["性別"] = "未知"
    pd.DataFrame([row]).to_excel(workbook_path, sheet_name="HCM", index=False)
    connection = get_connection()
    try:
        service = HcmWorkbookImportService(
            HcmWorkbookImportRepository(connection), HcmLegacyRowIntake(connection),
            lambda: MySqlUnitOfWork(connection),
        )
        frame = service.load_frame(str(workbook_path))
        assert frame is not None
        preview = service.preview(frame, str(workbook_path))
        receipt = service.apply(
            frame, str(workbook_path), preview.preview_fingerprint,
            f"hcm-dirty:{case_no}", "test-runner", f"hcm-dirty:{case_no}",
        )

        assert preview.ready_with_warning_count == 1
        assert receipt.inserted_with_warning_count == 1
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name,gender,phone,city,identity_status,service_days,service_type "
                "FROM clients WHERE case_no=%s", (case_no,),
            )
            assert cursor.fetchone() == {
                "name": "合成 HCM 客戶", "gender": None, "phone": "0912345678",
                "city": "新竹市", "identity_status": "一般市民", "service_days": 5,
                "service_type": "週休2日",
            }
            cursor.execute("SELECT status,service_days FROM orders WHERE case_no=%s", (case_no,))
            assert cursor.fetchone() == {"status": "待補件", "service_days": None}
            cursor.execute(
                "SELECT issue_codes FROM case_import_hcm_review_rows "
                "ORDER BY id DESC LIMIT 1",
            )
            review = cursor.fetchone()
            assert review is not None
            assert "hcm_field_invalid:性別" in review["issue_codes"]
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
            False,
        ),
        CaseArchitectureBootstrapIntent(case_no, terms, "approved-rates-v1"),
        provisional_registration_id,
    )


def _valid_hcm_workbook_row(case_no: str) -> dict[str, object]:
    return {
        "案件狀態": "洽談中",
        "查詢序號(案件編號)": case_no,
        "報名時間(建檔)": "2026/08/14",
        "IP位址": "192.0.2.40",
        "姓名": "合成 HCM 客戶",
        "性別": "女",
        "行動電話": "0912345678",
        "縣市": "新竹市",
        "身分資格": "一般市民",
        "服務時間": "8 小時 09:00 17:00",
        "預產期/預計服務開始月份": "2026/09/01",
        "預計服務日期": "2026/09/10",
        "希望服務天數": 5,
        "居住型態": "大樓",
        "生產方式": "自然產",
        "服務方式": "週休2日",
        "寶寶資訊": "合成資料",
    }


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
