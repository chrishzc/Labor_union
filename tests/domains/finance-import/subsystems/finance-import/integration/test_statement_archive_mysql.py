"""Archive retirement and preserved references on explicitly isolated synthetic MySQL."""
from io import BytesIO
import json
import os
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
import pytest

from api.dependencies.admin_auth import require_admin
from api.dependencies.finance_import import get_statement_archive_application
from api.routes.finance_statement_workspace import router
from infrastructure.mysql.case_manual_supplement_repository import MySqlCaseManualSupplementRepository
from infrastructure.mysql.finance_statement_archive_repository import MySqlStatementArchiveRepository
from subsystems.finance_import.case_manual_supplement import CaseManualSupplementService
from subsystems.finance_import.statement_archive import StatementArchiveApplication
from .test_case_manual_supplement_mysql import connection, seed, command

pytestmark = pytest.mark.skipif(os.getenv("STATEMENT_ARCHIVE_MYSQL") != "1", reason="explicit isolated MySQL archive acceptance")


def client_for(connection):
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_statement_archive_application] = lambda: StatementArchiveApplication(MySqlStatementArchiveRepository(connection))
    return TestClient(app)


@pytest.mark.parametrize("bank", ["sinopac", "taishin"])
@pytest.mark.parametrize("direction", ["client_receipt", "staff_salary", "client_refund"])
def test_only_formal_owner_evidence_enters_success_export_and_supplements_still_work(connection, bank, direction):
    case, target = seed(connection, direction)
    repository = MySqlStatementArchiveRepository(connection)
    before = {row.identity for row in repository.export_rows()}
    fields = {"交易日":"2026-10-20", "存入":88, "備註":"synthetic existing reference"}
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO finance_manual_statements(fields,actor) VALUES (%s,'synthetic-existing')", (json.dumps(fields),))
        # Neither a classification nor a mutable success flag is owner posting evidence.
        cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,credit,direction,bank_references,warnings,raw_payload,classification_type,reconciliation_status) VALUES (%s,%s,'2026-10-20',88,'incoming','{}','[]','{}','client_receipt','reconciled')", (uuid4().hex+uuid4().hex, bank))
        unposted = f"bank:{cursor.lastrowid}"
    connection.commit()
    assert {row.identity for row in repository.export_rows()} == before
    request = command(case, target, direction, bank=bank)
    service = CaseManualSupplementService(MySqlCaseManualSupplementRepository(connection))
    receipt = service.execute(**request); connection.commit()
    assert service.execute(**request) == receipt; connection.commit()
    rows = repository.export_rows()
    assert {row.identity for row in rows} == before | {f"bank:{receipt.row_id}"}
    assert unposted not in {row.identity for row in rows}
    assert all(row.source == "reconciled" and row.cases for row in rows)
    with client_for(connection) as client:
        response = client.get("/statements/export")
    assert response.status_code == 200
    assert int(response.headers["X-Statement-Count"]) == len(rows)
    workbook = load_workbook(BytesIO(response.content), data_only=False)
    assert "歷史人工備查" not in workbook.sheetnames and "人工新增" not in workbook.sheetnames


def snapshot(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id,fields,actor,created_at FROM finance_manual_statements ORDER BY id")
        references = cursor.fetchall()
        cursor.execute("SELECT * FROM finance_statement_commands ORDER BY idempotency_key")
        commands = cursor.fetchall()
        cursor.execute("SELECT version FROM finance_statement_archive_state WHERE id=1")
        version = cursor.fetchone()
        counts = {}
        for table in ("finance_import_rows", "client_ledger_entries", "staff_payout_events", "finance_statement_exclusions"):
            cursor.execute(f"SELECT COUNT(*) n FROM {table}"); counts[table] = cursor.fetchone()["n"]
    return references, commands, version, counts


def test_retired_write_cannot_replay_old_success_and_reference_download_is_readonly(connection):
    key = "synthetic-old-key:" + uuid4().hex
    marker = "synthetic-reference:" + uuid4().hex
    fields = {"交易日":"2025-01-02", "存入":12000, "備註":"=1+1", "銷帳編號":"000001", "原備查欄":marker}
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO finance_manual_statements(fields,actor) VALUES (%s,'synthetic-existing')", (json.dumps(fields, ensure_ascii=False),))
        identity = f"manual:{cursor.lastrowid}"
        cursor.execute("INSERT INTO finance_statement_commands(idempotency_key,command_digest,result_identity,saved_count,excluded_count,actor) VALUES (%s,%s,%s,1,0,'synthetic-existing')", (key, "a"*64, identity))
    connection.commit()
    before = snapshot(connection)
    with client_for(connection) as client:
        for payload, operation in (({"fields":fields},key), ({"fields":fields},uuid4().hex), ({"fields":{},"duplicate_of":identity},uuid4().hex)):
            rejected = client.post("/statements/manual", json=payload, headers={"Idempotency-Key":operation})
            assert rejected.status_code == 410 and "legacy_manual_statement_retired" in rejected.text
        response = client.get("/statements/manual/export")
        assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
        workbook = load_workbook(BytesIO(response.content), data_only=False)
        assert workbook.sheetnames == ["歷史人工備查"]
        sheet = workbook.active; headers = [cell.value for cell in sheet[1]]
        row = next(row for row in sheet.iter_rows(min_row=2) if any(cell.value == marker for cell in row))
        assert row[headers.index("銷帳編號")].value == "000001"
        assert row[headers.index("備註")].value == "=1+1" and row[headers.index("備註")].data_type == "s"
        assert row[headers.index("資料來源")].value == "歷史人工備查（不代表已核銷）"
    assert snapshot(connection) == before
    assert identity not in {row.identity for row in MySqlStatementArchiveRepository(connection).export_rows()}
