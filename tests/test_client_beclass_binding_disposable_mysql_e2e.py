"""
File: test_client_beclass_binding_disposable_mysql_e2e.py
Description: 以 disposable MySQL 驗證 Client BeClass 來源流水號與案件綁定分離。
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from infrastructure.mysql.client_beclass_workbook_import_repository import (
    ClientBeClassWorkbookImportRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from domains.case_import.client_beclass_binding import ClientCaseBindingStatus
from subsystems.case_import.client_beclass_workbook_import import (
    ClientBeClassWorkbookConflict,
    ClientBeClassWorkbookImportService,
)


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_unique_client_case_binding_preserves_source_query_number():
    case_no = f"BIND-{uuid4().hex[:14]}"
    source_query_no = f"SOURCE-{uuid4().hex[:12]}"
    client_name = f"綁定測試客戶-{case_no}"
    client_phone = f"09{uuid4().int % 100000000:08d}"
    connection = get_connection()
    try:
        client_id = _create_case(connection, case_no, client_name, client_phone)
        repository = ClientBeClassWorkbookImportRepository(connection)

        candidate = repository.resolve_unique_client_case(client_name, client_phone)
        source_id = repository.create_bound_source_if_absent(
            _source_payload(source_query_no, client_name, client_phone), candidate,
        )
        connection.commit()

        assert candidate == {"id": client_id, "case_no": case_no}
        assert source_id is not None
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT query_no,client_id,bound_case_no FROM beclass_records WHERE id=%s",
                (source_id,),
            )
            assert cursor.fetchone() == {
                "query_no": source_query_no,
                "client_id": client_id,
                "bound_case_no": case_no,
            }
    finally:
        connection.close()


def test_binding_resolution_distinguishes_no_client_multiple_clients_and_no_case():
    unique = uuid4().hex[:12]
    connection = get_connection()
    try:
        repository = ClientBeClassWorkbookImportRepository(connection)
        no_client = repository.resolve_client_case_binding(
            f"未命中-{unique}", "0900000000"
        )

        duplicate_name = f"重複客戶-{unique}"
        duplicate_phone = f"09{uuid4().int % 100000000:08d}"
        with connection.cursor() as cursor:
            for suffix in ("A", "B"):
                cursor.execute(
                    "INSERT INTO clients (case_no,name,phone) VALUES (%s,%s,%s)",
                    (f"MULTI-{unique}-{suffix}", duplicate_name, duplicate_phone),
                )
        connection.commit()
        multiple_clients = repository.resolve_client_case_binding(
            duplicate_name, duplicate_phone
        )

        case_name = f"多案件-{unique}"
        case_phone = f"09{uuid4().int % 100000000:08d}"
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO clients (case_no,name,phone) VALUES (%s,%s,%s)",
                (f"CLIENT-{unique}", case_name, case_phone),
            )
        connection.commit()
        no_case = repository.resolve_client_case_binding(case_name, case_phone)

        assert no_client.status is ClientCaseBindingStatus.NO_CLIENT
        assert no_client.client_candidate_count == no_client.case_candidate_count == 0
        assert multiple_clients.status is ClientCaseBindingStatus.MULTIPLE_CLIENTS
        assert multiple_clients.client_candidate_count == 2
        assert multiple_clients.case_candidate_count == 0
        assert no_case.status is ClientCaseBindingStatus.CASE_NOT_UNIQUE
        assert no_case.client_candidate_count == 1
        assert no_case.case_candidate_count == 0
    finally:
        connection.close()


def test_typed_workbook_apply_isolates_dirty_rows_replays_and_conflicts(tmp_path):
    case_no = f"BIND-{uuid4().hex[:14]}"
    client_name = f"綁定測試客戶-{case_no}"
    client_phone = f"09{uuid4().int % 100000000:08d}"
    valid_query = f"SOURCE-{uuid4().hex[:12]}"
    command_key = f"client-disposable-{uuid4().hex}"
    connection = get_connection()
    try:
        _create_case(connection, case_no, client_name, client_phone)
        service = ClientBeClassWorkbookImportService(
            ClientBeClassWorkbookImportRepository(connection),
        )
        workbook = _write_workbook(
            tmp_path / "client-beclass.xlsx",
            _workbook_row(valid_query, client_name, client_phone),
            _workbook_row(f"DIRTY-{uuid4().hex[:12]}", "缺手機客戶", ""),
            _workbook_row(f"UNBOUND-{uuid4().hex[:12]}", "無案件客戶", "0911222333"),
        )
        preview = service.preview(str(workbook))

        first = service.apply(
            str(workbook), command_key, preview.preview_fingerprint,
            "wp83-test", "client-disposable-correlation",
        )
        replay = service.apply(
            str(workbook), command_key, preview.preview_fingerprint,
            "wp83-test", "client-disposable-correlation",
        )
        changed = _write_workbook(
            tmp_path / "client-beclass-changed.xlsx",
            _workbook_row(valid_query, client_name, "0999999999"),
        )

        assert preview.source_row_count == 3
        assert preview.create_count == 1
        assert preview.review_required_count == 1
        assert preview.existing_conflict_count == 1
        assert first.created_count == 1
        assert first.review_required_count == 1
        assert first.existing_conflict_count == 1
        assert replay.replayed_workbook is True
        from subsystems.anomalies.beclass_import_outbox_consumer import (
            consume_beclass_import_review_events,
        )

        projected = consume_beclass_import_review_events(connection)
        assert projected.failed_count == 0
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT occurrence.logical_code "
                "FROM import_warning_occurrences occurrence "
                "JOIN beclass_import_review_rows review "
                "ON review.source_event_identity=occurrence.source_event_identity "
                "WHERE review.source_event_identity LIKE %s",
                (f"beclass-workbook:{first.source_content_digest}:%",),
            )
            assert {row["logical_code"] for row in cursor.fetchall()} == {
                "CLIENT-BECLASS-SOURCE-001",
                "CLIENT-BECLASS-BIND-001",
            }
        with pytest.raises(
            ClientBeClassWorkbookConflict,
            match="client_beclass_workbook_idempotency_conflict",
        ):
            service.apply(
                str(changed), command_key,
                service.preview(str(changed)).preview_fingerprint,
                "wp83-test", "client-disposable-correlation",
            )
    finally:
        connection.close()


def _create_case(connection, case_no: str, client_name: str, client_phone: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO clients (case_no,name,phone) VALUES (%s,%s,%s)",
            (case_no, client_name, client_phone),
        )
        client_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO orders (case_no,client_id,status,lifecycle_version) VALUES (%s,%s,'洽談中',0)",
            (case_no, client_id),
        )
    connection.commit()
    return client_id


def _source_payload(source_query_no: str, client_name: str, client_phone: str) -> dict[str, object]:
    return {
        "query_no": source_query_no,
        "created_at": "2026-08-14 09:00:00",
        "name": client_name,
        "email": None,
        "phone": client_phone,
        "tel": None,
        "ext": None,
        "city": None,
        "zip_code": None,
        "address": None,
        "refund_bank_code": None,
        "refund_account_no": None,
        "admin_notes": None,
        "birth_date": None,
        "survey_details": "{}",
    }


def _write_workbook(path: Path, *rows: dict[str, object]) -> Path:
    pd.DataFrame(rows).to_excel(path, sheet_name="Client", index=False)
    return path


def _workbook_row(query_no: str, name: str, phone: str) -> dict[str, object]:
    return {
        "查詢序號": query_no,
        "報名時間": "2026-08-14",
        "姓名": name,
        "Email": "client@example.test",
        "出生年": 1990,
        "月": 1,
        "日": 2,
        "行動電話": phone,
        "補助款退款:銀行代號+分行代號": "",
        "銀行帳號": "",
    }
