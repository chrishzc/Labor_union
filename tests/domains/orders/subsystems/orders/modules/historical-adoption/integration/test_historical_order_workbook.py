"""
File: tests/integration/test_historical_order_workbook.py
Description: 在 disposable MySQL 驗證歷史訂單配對、rollback 與 Orders review outbox acknowledgement。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
import pytest
from api.dependencies import historical_order_adoption as historical_dependencies
from api.dependencies.durable_job_handlers import historical_service_completion_handler
from api.routes import historical_order_adoption as historical_routes
from api.routes import historical_service_accounting as historical_accounting_routes

from domains.orders.historical_adoption import HistoricalOrderSourceStatus
from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.historical_order_adoption_repository import MySqlHistoricalOrderAdoptionRepository
from infrastructure.mysql.historical_assignment_writer import MySqlHistoricalAssignmentWriter
from infrastructure.mysql.historical_order_workbook_import_repository import HistoricalOrderWorkbookImportRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import FixedBusinessClock
from subsystems.access.authentication_session import AdminPrincipal
from .historical_accounting_fixture import seed_accounting_basis
from infrastructure.mysql.historical_pending_deposit_matching_repository import MySqlHistoricalPendingDepositMatchingRepository
from subsystems.orders.historical_order_adoption_outbox_consumer import (
    consume_historical_order_adoption_review_events,
)
from subsystems.orders.historical_adoption_workflow import HistoricalOrderAdoptionRequest, HistoricalOrderAdoptionWorkflow
from subsystems.orders.historical_order_workbook import (
    HistoricalCaregiverSource,
    HistoricalOrderWorkbookRow,
    load_historical_order_workbook,
)
from subsystems.orders.historical_order_workbook_import import (
    HistoricalOrderWorkbookConflict,
    HistoricalOrderWorkbookImportService,
)
from subsystems.scheduling import staff_monthly_calendar_query


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


class _OutboxRuntime:
    def failure_unit_of_work(self, connection):
        return MySqlUnitOfWork(connection)


def test_corrected_historical_workbook_writes_both_same_day_shifts_to_mysql(monkeypatch):
    token = uuid4().hex
    connection = get_connection()
    try:
        morning_case, staff_name = _seed_case(connection, token, "am")
        afternoon_case, _ = _seed_case(connection, token, "pm")
        for case_no in (morning_case, afternoon_case):
            _seed_original_partial_payment(connection, case_no)
        original_accounting = {
            case_no: _accounting_snapshot(connection, case_no)
            for case_no in (morning_case, afternoon_case)
        }
    finally:
        connection.close()

    clock = FixedBusinessClock(datetime(2026, 11, 5, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(historical_dependencies, "SystemBusinessClock", lambda: clock)
    monkeypatch.setattr("subsystems.orders.historical_adoption_workflow.SystemBusinessClock", lambda: clock)
    app = FastAPI()
    app.include_router(historical_routes.router)
    app.dependency_overrides[historical_routes.require_admin] = lambda: AdminPrincipal(
        1, "historical-e2e", "測試工會人員", "system_admin",
    )
    path = "/api/v1/orders/historical-adoption/workbooks"

    def workbook_bytes(morning, afternoon, afternoon_start=date(2026, 10, 19), *, standard=False):
        book = Workbook()
        sheet = book.active
        sheet.append(["client_name", "case_no", "start_date", "end_date", "status", "staff_name"] + ([] if standard else ["服務時間"]))
        sheet.append([_client_name(morning_case), morning_case, date(2026, 9, 15), date(2026, 10, 30), 1, staff_name] + ([] if standard else [morning]))
        sheet.append([_client_name(afternoon_case), afternoon_case, afternoon_start, date(2026, 11, 9), 1, staff_name] + ([] if standard else [afternoon]))
        output = BytesIO()
        book.save(output)
        book.close()
        return output.getvalue()

    def apply_workbook(client, workbook):
        files = {"workbook": ("history.xlsx", workbook)}
        preview_response = client.post(f"{path}/preview", files=files)
        assert preview_response.status_code == 200, preview_response.text
        preview = preview_response.json()["data"]
        response = client.post(
            f"{path}/apply", files=files,
            data={"preview_fingerprint": preview["preview_fingerprint"]},
            headers={"Idempotency-Key": f"ui-import-historical-orders-authoritative-v3-{uuid4().hex}",
                     "X-Correlation-ID": f"historical-shifts-{token}"},
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]

    with TestClient(app) as client:
        corrected = workbook_bytes(None, None, standard=True)
        excluded = apply_workbook(client, corrected)
        assert excluded["import_counts"]["imported_count"] == 0
        assert excluded["current_conflict_count"] == 2
        assert all("historical_service_time_terms_unavailable" in row["issue_codes"] for row in excluded["row_issues"])

        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.executemany(
                    "UPDATE orders SET service_start_time=%s,service_end_time=%s,service_end_day_offset=0 "
                    "WHERE case_no=%s",
                    (("09:00:00", "13:00:00", morning_case), ("13:30:00", "17:30:00", afternoon_case)),
                )
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM order_terms_change_events WHERE case_no IN (%s,%s)",
                    (morning_case, afternoon_case),
                )
                assert cursor.fetchone()["total"] == 0
            connection.commit()
        finally:
            connection.close()

        imported = apply_workbook(client, corrected)
        assert imported["import_counts"]["imported_count"] == 2
        assert imported["assignments_created"] == 2
        identical = apply_workbook(client, corrected)
        assert identical["import_counts"] == {"imported_count": 0, "duplicate_skipped_count": 2, "not_imported_count": 0}
        assert identical["assignments_created"] == 0

        connection = get_connection()
        try:
            absent_case, _ = _seed_case(connection, token, "added-later")
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE orders SET status='訂單成立',lifecycle_version=lifecycle_version+1 WHERE case_no=%s",
                    (morning_case,),
                )
            connection.commit()
        finally:
            connection.close()

        reimported = apply_workbook(client, corrected)
        assert reimported["import_counts"] == {"imported_count": 1, "duplicate_skipped_count": 1, "not_imported_count": 0}
        assert reimported["assignments_created"] == 0
        assert reimported["absent_order_cancellation_count"] == 1

        conflict = apply_workbook(client, workbook_bytes("9:00-13:00(4小時)", "12:30-16:30(4小時)", date(2026, 9, 15)))
        assert conflict["import_counts"]["not_imported_count"] == 2
        assert conflict["absent_order_cancellation_count"] == 0
        assert all(any(";overlap=" in code for code in row["issue_codes"]) for row in conflict["row_issues"])

        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE orders SET service_start_time='12:30:00' WHERE case_no=%s", (afternoon_case,))
            connection.commit()
        finally:
            connection.close()
        overlapping = workbook_bytes(None, None, date(2026, 9, 15), standard=True)
        conflict = apply_workbook(client, overlapping)
        assert conflict["import_counts"]["not_imported_count"] == 2
        assert conflict["assignments_created"] == 0
        assert all(any("T12:30:00" in code and "T13:00:00" in code for code in row["issue_codes"])
                   for row in conflict["row_issues"])

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT o.case_no,o.status,a.staff_id,a.assigned_start_date,a.assigned_end_date,"
                "r.result_snapshot FROM orders o JOIN case_staff_assignments a ON a.case_no=o.case_no "
                "JOIN historical_order_adoption_receipts r ON r.id=(SELECT MAX(candidate.id) "
                "FROM historical_order_adoption_receipts candidate WHERE candidate.case_no=o.case_no) "
                "WHERE o.case_no IN (%s,%s)", (morning_case, afternoon_case),
            )
            rows = cursor.fetchall()
            cursor.execute("SELECT status FROM orders WHERE case_no=%s", (absent_case,))
            assert cursor.fetchone()["status"] == OrderLifecycleStatus.CANCELLED.value
            cursor.execute("SELECT COUNT(*) AS total FROM admin_command_receipts WHERE command_family='historical_order_workbook_ingest'")
            assert cursor.fetchone()["total"] == 0
        assert len(rows) == 2
        assert rows[0]["staff_id"] == rows[1]["staff_id"]
        monkeypatch.setattr(staff_monthly_calendar_query, "get_connection", get_connection)
        calendar = staff_monthly_calendar_query.get_staff_monthly_calendar_schedule(rows[0]["staff_id"], 2026, 10, clock=clock)
        shifts = [item for item in calendar["days"] if item["work_date"] == "2026-10-19" and item["case_no"] in {morning_case, afternoon_case}]
        assert [(shift["case_no"], shift["starts_at"][11:16], shift["ends_at"][11:16]) for shift in shifts] == [
            (morning_case, "09:00", "13:00"), (afternoon_case, "13:30", "17:30"),
        ]
        by_case = {row["case_no"]: row for row in rows}
        for case, status, start_date, end_date, start_time, end_time in (
            (morning_case, OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED, date(2026, 9, 15), date(2026, 10, 30), "09:00:00", "13:00:00"),
            (afternoon_case, OrderLifecycleStatus.HISTORICAL_IN_SERVICE, date(2026, 10, 19), date(2026, 11, 9), "13:30:00", "17:30:00"),
        ):
            row = by_case[case]
            assert (row["status"], row["assigned_start_date"], row["assigned_end_date"]) == (status.value, start_date, end_date)
            assert json.loads(row["result_snapshot"])["historical_service_time"] == {
                "start_time": start_time, "end_time": end_time, "end_day_offset": 0,
            }
        morning = _accounting_snapshot(connection, morning_case)
        assert morning[:3] == original_accounting[morning_case][:3]
        assert [(item["amount_due_ntd"], item["due_date"]) for item in morning[3]] == [(72000, date(2026, 11, 15))]
        assert _accounting_snapshot(connection, afternoon_case) == original_accounting[afternoon_case]
        with connection.cursor() as cursor:
            cursor.execute("SELECT lifecycle_version FROM orders WHERE case_no=%s", (afternoon_case,))
            version = cursor.fetchone()["lifecycle_version"]
        connection.rollback()

        job = {
            "case_no": afternoon_case,
            "expected_order_version": version,
            "evaluation_at": "2026-11-10T00:00:00+08:00",
            "idempotency_key": f"historical-rollover:{token}",
            "actor": "system:historical-service-completion",
            "reason": "historical service end date passed",
            "correlation_id": f"historical-rollover:{token}",
        }
        receipt, _ = historical_service_completion_handler(job)
        replay, _ = historical_service_completion_handler(job)
        assert receipt["after_status"] == OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value
        assert replay["replayed"] is True
        assert _order_status(connection, afternoon_case) == OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value
        afternoon = _accounting_snapshot(connection, afternoon_case)
        assert afternoon[:3] == original_accounting[afternoon_case][:3]
        assert [(item["amount_due_ntd"], item["due_date"]) for item in afternoon[3]] == [(72000, date(2026, 12, 15))]
    finally:
        connection.close()


def test_manual_service_days_apply_and_replay_preserve_original_finance(tmp_path):
    token = uuid4().hex
    connection = get_connection()
    try:
        case_no, staff_name = _seed_case(connection, token, "days")
        _seed_original_partial_payment(connection, case_no)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE orders SET service_start_time='09:00:00',service_end_time='17:00:00',service_end_day_offset=0 "
                "WHERE case_no=%s", (case_no,),
            )
        connection.commit()
        workbook = _write_single_workbook(tmp_path / "historical-days.xlsx", case_no, staff_name, 1)
        row = load_historical_order_workbook(workbook).rows[0]
        adoption = HistoricalOrderAdoptionWorkflow(
            MySqlHistoricalOrderAdoptionRepository(connection), lambda: MySqlUnitOfWork(connection),
            MySqlHistoricalAssignmentWriter(connection),
        )
        adoption_preview = adoption.preview(row)
        adoption.apply(HistoricalOrderAdoptionRequest(
            row, adoption_preview.fingerprint, f"adopt:{token}", "synthetic", "原歷史訂單", token,
        ))
        original = _accounting_snapshot(connection, case_no)
        connection.rollback()
        app = FastAPI()
        app.include_router(historical_accounting_routes.router)
        app.dependency_overrides[historical_accounting_routes.require_system_admin] = lambda: AdminPrincipal(
            1, "synthetic", "測試工會人員", "system_admin",
        )
        path = f"/api/v1/orders/{case_no}/historical-service-accounting"
        headers = {"Idempotency-Key": f"historical-days:{token}", "X-Correlation-ID": token}
        with TestClient(app) as client:
            queried = client.get(path)
            assert queried.status_code == 200, queried.text
            facts = queried.json()["data"]
            assert facts["historical_day_revision"] == 0
            assignment = facts["assignments"][0]
            caregivers = [{
                "assignment_identity": assignment["assignment_identity"],
                "staff_id": assignment["staff_id"],
                "actual_service_days": 26,
            }]
            response = client.post(f"{path}/preview", json={"caregivers": caregivers})
            assert response.status_code == 200, response.text
            preview = response.json()["data"]
            assert preview["client_obligation_amount_ntd"] > 0
            assert _accounting_snapshot(connection, case_no) == original
            connection.rollback()
            body = {
                "caregivers": caregivers, "reason": "合成原服務紀錄",
                "expected_lifecycle_version": facts["lifecycle_version"],
                "expected_historical_day_revision": facts["historical_day_revision"],
                "expected_client_finance_version": facts["client_finance_version"],
                "expected_payroll_version": facts["payroll_version"],
                "preview_fingerprint": preview["preview_fingerprint"],
            }
            first = client.post(f"{path}/apply", json=body, headers=headers)
            assert first.status_code == 200, first.text
            receipt = first.json()["data"]
            assert receipt["resulting_historical_day_revision"] == 1
            assert receipt["resulting_client_finance_version"] == facts["client_finance_version"]
            assert receipt["resulting_payroll_version"] == facts["payroll_version"] == 1
            assert receipt["client_obligation_amount_ntd"] == preview["client_obligation_amount_ntd"]
            assert receipt["replayed"] is False
            saved = _accounting_snapshot(connection, case_no, expected_revisions=1)
            assert saved[:4] == original[:4]
            connection.rollback()
            replay = client.post(f"{path}/apply", json=body, headers=headers)
            assert replay.status_code == 200, replay.text
            assert replay.json()["data"] == {**receipt, "replayed": True}
            stale = client.post(f"{path}/apply", json=body, headers={**headers, "Idempotency-Key": f"stale:{token}"})
            assert stale.status_code == 409, stale.text
            assert _accounting_snapshot(connection, case_no, expected_revisions=1) == saved
            with connection.cursor() as cursor:
                cursor.execute("SELECT staff_payment_due_date FROM orders WHERE case_no=%s", (case_no,))
                assert cursor.fetchone()["staff_payment_due_date"] == date(2025, 2, 15)
                cursor.execute("SELECT COUNT(*) AS n FROM payroll_outbox WHERE case_no=%s", (case_no,))
                assert cursor.fetchone()["n"] == 1
    finally:
        connection.close()


def test_workbook_apply_uses_only_the_canonical_six_columns(tmp_path):
    token = uuid4().hex
    connection = get_connection()
    try:
        first_case, first_staff = _seed_case(connection, token, "single")
        second_case, second_staff = _seed_case(connection, token, "dual")
        second_staff_two = _seed_staff(connection, token, "dual-two")
        workbook_path = _write_workbook(tmp_path, first_case, first_staff, second_case, second_staff, second_staff_two)
        service = _service(connection)

        preview = service.preview(str(workbook_path))
        receipt = service.apply(str(workbook_path), f"historical-workbook:{token}", preview.preview_fingerprint, "historical-workbook-test", token)
        repeat = service.preview(str(workbook_path))
        replay = service.apply(str(workbook_path), f"historical-workbook:{token}:repeat", repeat.preview_fingerprint, "historical-workbook-test", token)

        assert receipt.adopted_count == 2
        assert receipt.assignments_created == 1
        assert replay.replayed_workbook is False
        assert replay.assignments_created == 0
        _assert_assignment_and_evidence(connection, first_case, second_case)
    finally:
        connection.close()


def test_six_column_workbook_applies_zero_one_two_as_distinct_order_statuses(tmp_path):
    token = uuid4().hex
    connection = get_connection()
    try:
        cancelled_case, _ = _seed_case(connection, token, "zero")
        completed_case, _ = _seed_case(connection, token, "one")
        discussion_case, _ = _seed_case(connection, token, "two")
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE orders SET status='訂單完成',lifecycle_version=1 WHERE case_no=%s",
                (discussion_case,),
            )
        connection.commit()
        workbook_path = _write_status_workbook(
            tmp_path / "statuses-012.xlsx",
            ((cancelled_case, 0), (completed_case, 1), (discussion_case, 2)),
        )
        service = _service(connection)

        preview = service.preview(str(workbook_path))
        receipt = service.apply(
            str(workbook_path), f"historical-workbook:status-012:{token}", preview.preview_fingerprint,
            "historical-workbook-test", token,
        )
        repeat = service.preview(str(workbook_path))
        replay = service.apply(
            str(workbook_path), f"historical-workbook:status-012:{token}:repeat", repeat.preview_fingerprint,
            "historical-workbook-test", token,
        )

        expected_counts = {
            "cancelled_0": 1,
            "deposit_paid_1": 1,
            "discussion_2": 1,
            "invalid_or_blank": 0,
        }
        assert preview.status_counts.as_dict() == expected_counts
        assert receipt.status_counts.as_dict() == expected_counts
        assert replay.status_counts.as_dict() == expected_counts
        assert replay.replayed_workbook is False
        assert replay.assignments_created == 0
        assert _order_status(connection, cancelled_case) == "洽談中"
        assert _order_status(connection, completed_case) == "歷史訂單－未服務"
        assert _order_status(connection, discussion_case) == "洽談中"
        assert _count(connection, "order_lifecycle_state_events", cancelled_case) == 0
        assert _count(connection, "historical_order_adoption_receipts", cancelled_case) == 0
        for case_no in (completed_case, discussion_case):
            assert _count(connection, "order_lifecycle_state_events", case_no) == 1
            assert _count(connection, "historical_order_adoption_receipts", case_no) == 1
    finally:
        connection.close()


def test_workbook_refreshes_a_later_row_for_the_same_case_after_its_own_write(tmp_path):
    token = uuid4().hex
    connection = get_connection()
    try:
        case_no, _ = _seed_case(connection, token, "repeated")
        workbook_path = _write_status_workbook(
            tmp_path / "repeated-case.xlsx",
            ((case_no, 1), (case_no, 1)),
        )
        service = _service(connection)

        preview = service.preview(str(workbook_path))
        receipt = service.apply(
            str(workbook_path),
            f"historical-workbook:repeated:{token}",
            preview.preview_fingerprint,
            "historical-workbook-test",
            token,
        )

        assert receipt.source_row_count == 2
        assert receipt.adopted_count == 2
        assert receipt.import_counts.as_dict() == {"imported_count": 1, "duplicate_skipped_count": 1, "not_imported_count": 0}
        assert _order_status(connection, case_no) == "歷史訂單－未服務"
        assert _count(connection, "order_lifecycle_state_events", case_no) == 1
        assert _count(connection, "historical_order_adoption_receipts", case_no) == 1
    finally:
        connection.close()


def test_six_column_workbook_adopts_pending_orders_with_truthful_before_status(tmp_path):
    token = uuid4().hex
    connection = get_connection()
    try:
        cancelled_case, _ = _seed_case(connection, token, "pzero")
        completed_case, _ = _seed_case(connection, token, "qone")
        discussion_case, _ = _seed_case(connection, token, "rtwo")
        case_numbers = (cancelled_case, completed_case, discussion_case)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE orders SET status='待補件',lifecycle_version=0 "
                "WHERE case_no IN (%s,%s,%s)",
                case_numbers,
            )
        connection.commit()
        workbook_path = _write_status_workbook(
            tmp_path / "pending-statuses-012.xlsx",
            ((cancelled_case, 0), (completed_case, 1), (discussion_case, 2)),
        )
        service = _service(connection)

        preview = service.preview(str(workbook_path))
        receipt = service.apply(
            str(workbook_path),
            f"historical-workbook:pending-status-012:{token}",
            preview.preview_fingerprint,
            "historical-workbook-test",
            token,
        )
        repeat = service.preview(str(workbook_path))
        replay = service.apply(
            str(workbook_path),
            f"historical-workbook:pending-status-012:{token}:repeat",
            repeat.preview_fingerprint,
            "historical-workbook-test",
            token,
        )

        assert receipt.adopted_count == 2
        assert replay.replayed_workbook is False
        assert replay.assignments_created == 0
        expected_after = {
            completed_case: "歷史訂單－未服務",
            discussion_case: "洽談中",
        }
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT case_no,before_status,after_status FROM "
                "order_lifecycle_state_events WHERE case_no IN (%s,%s,%s) "
                "ORDER BY case_no",
                case_numbers,
            )
            events = {row["case_no"]: row for row in cursor.fetchall()}
        assert set(events) == set(expected_after)
        assert all(row["before_status"] == "待補件" for row in events.values())
        assert {
            case_no: row["after_status"] for case_no, row in events.items()
        } == expected_after
        assert {
            case_no: _order_status(connection, case_no) for case_no in expected_after
        } == expected_after
        assert _order_status(connection, cancelled_case) == "待補件"
        assert _count(connection, "historical_order_adoption_receipts", cancelled_case) == 0
        for case_no in expected_after:
            assert _count(connection, "historical_order_adoption_receipts", case_no) == 1
    finally:
        connection.close()


def test_workbook_conflict_rejects_changed_source_before_row_apply(tmp_path):
    token = uuid4().hex
    connection = get_connection()
    try:
        case_no, staff_name = _seed_case(connection, token, "conflict")
        first_path = _write_single_workbook(tmp_path / "first.xlsx", case_no, staff_name, status=1)
        changed_path = _write_single_workbook(tmp_path / "changed.xlsx", case_no, staff_name, status=2)
        service = _service(connection)
        first_preview = service.preview(str(first_path))
        service.apply(str(first_path), f"historical-workbook:conflict:{token}", first_preview.preview_fingerprint, "historical-workbook-test", token)

        with pytest.raises(HistoricalOrderWorkbookConflict, match="historical_order_preview_stale"):
            service.apply(str(changed_path), f"historical-workbook:conflict:{token}:new", first_preview.preview_fingerprint, "historical-workbook-test", token)

        assert _order_status(connection, case_no) == "歷史訂單－服務完成"
    finally:
        connection.close()


def test_valid_historical_values_replace_current_values_without_false_conflict(tmp_path):
    token = uuid4().hex
    connection = get_connection()
    try:
        case_no, staff_name = _seed_case(connection, token, "replace")
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE orders SET status='訂單取消',lifecycle_version=3,"
                "actual_start_date='2024-12-01',actual_end_date='2024-12-31' "
                "WHERE case_no=%s",
                (case_no,),
            )
        connection.commit()
        workbook = _write_single_workbook(
            tmp_path / "replace.xlsx", case_no, staff_name, status=1
        )
        service = _service(connection)
        preview = service.preview(str(workbook))

        receipt = service.apply(
            str(workbook), f"historical-workbook:replace:{token}", preview.preview_fingerprint,
            "historical-workbook-test", token,
        )

        assert receipt.adopted_count == 1
        assert preview.review_required_count == preview.current_conflict_count == 0
        assert receipt.review_required_count == receipt.current_conflict_count == 0
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT status,lifecycle_version,actual_start_date,actual_end_date "
                "FROM orders WHERE case_no=%s",
                (case_no,),
            )
            assert cursor.fetchone() == {
                "status": "歷史訂單－服務完成",
                "lifecycle_version": 4,
                "actual_start_date": date(2025, 1, 2),
                "actual_end_date": date(2025, 1, 31),
            }
    finally:
        connection.close()


def test_row_apply_rolls_back_when_persist_fails(tmp_path, monkeypatch):
    token = uuid4().hex
    connection = get_connection()
    try:
        case_no, staff_name = _seed_case(connection, token, "rollback")
        row = load_historical_order_workbook(str(_write_single_workbook(tmp_path / "rollback.xlsx", case_no, staff_name, status=1))).rows[0]
        repository = MySqlHistoricalOrderAdoptionRepository(connection)
        workflow = HistoricalOrderAdoptionWorkflow(
            repository, lambda: MySqlUnitOfWork(connection), MySqlHistoricalAssignmentWriter(connection),
        )
        preview = workflow.preview(row)
        monkeypatch.setattr(repository, "_append_outbox", _raise_after_domain_writes)

        with pytest.raises(RuntimeError, match="historical_workbook_forced_outbox_failure"):
            workflow.apply(HistoricalOrderAdoptionRequest(row, preview.fingerprint, f"historical-workbook:rollback:{token}", "historical-workbook-test", "rollback", token))

        assert _order_status(connection, case_no) == "洽談中"
        assert _count(connection, "order_lifecycle_state_events", case_no) == 0
        assert _count(connection, "case_staff_assignments", case_no) == 0
    finally:
        connection.close()


def test_workbook_apply_rolls_back_every_prior_row_when_a_later_row_fails(
    tmp_path, monkeypatch
):
    token = uuid4().hex
    connection = get_connection()
    try:
        first_case, _ = _seed_case(connection, token, "atomic-first")
        second_case, _ = _seed_case(connection, token, "atomic-second")
        repository = MySqlHistoricalOrderAdoptionRepository(connection)
        workflow = HistoricalOrderAdoptionWorkflow(
            repository,
            lambda: MySqlUnitOfWork(connection),
            MySqlHistoricalAssignmentWriter(connection),
            matching_pending_deposit=MySqlHistoricalPendingDepositMatchingRepository(connection),
        )
        service = HistoricalOrderWorkbookImportService(
            HistoricalOrderWorkbookImportRepository(connection),
            workflow,
            lambda: MySqlUnitOfWork(connection),
        )
        workbook_path = _write_status_workbook(
            tmp_path / "whole-workbook-rollback.xlsx",
            ((first_case, 1), (second_case, 2)),
        )
        original_append_outbox = repository._append_outbox
        outbox_calls = 0

        def fail_after_first_row(*args):
            nonlocal outbox_calls
            outbox_calls += 1
            if outbox_calls == 2:
                raise RuntimeError("historical_workbook_forced_second_row_failure")
            return original_append_outbox(*args)

        monkeypatch.setattr(repository, "_append_outbox", fail_after_first_row)
        preview = service.preview(str(workbook_path))

        with pytest.raises(
            RuntimeError, match="historical_workbook_forced_second_row_failure"
        ):
            service.apply(
                str(workbook_path),
                f"historical-workbook:whole-rollback:{token}",
                preview.preview_fingerprint,
                "historical-workbook-test",
                token,
            )

        assert _order_status(connection, first_case) == "洽談中"
        assert _order_status(connection, second_case) == "洽談中"
        assert _count(connection, "order_lifecycle_state_events", first_case) == 0
        assert _count(connection, "order_lifecycle_state_events", second_case) == 0
        assert _count(connection, "historical_order_adoption_receipts", first_case) == 0
        assert _count(connection, "historical_order_adoption_receipts", second_case) == 0
    finally:
        connection.close()


def test_matched_dirty_row_acknowledges_orders_historical_review_outbox():
    token = uuid4().hex
    connection = get_connection()
    try:
        case_no, _ = _seed_case(connection, token, "review")
        row = HistoricalOrderWorkbookRow(
            2,
            f"historical-orders:{token}:review",
            "a" * 64,
            case_no,
            _client_name(case_no),
            HistoricalOrderSourceStatus.DEPOSIT_PAID,
            None,
            None,
            (HistoricalCaregiverSource(1, f"missing-{token[:8]}", None, None, False, ("staff_missing",)),),
            ("staff_missing",),
        )
        workflow = HistoricalOrderAdoptionWorkflow(
            MySqlHistoricalOrderAdoptionRepository(connection), lambda: MySqlUnitOfWork(connection),
            MySqlHistoricalAssignmentWriter(connection),
        )
        preview = workflow.preview(row)
        receipt = workflow.apply(
            HistoricalOrderAdoptionRequest(
                row, preview.fingerprint, f"historical-workbook:review:{token}", "historical-workbook-test", "review", token
            )
        )
        result = consume_historical_order_adoption_review_events(
            connection, runtime=_OutboxRuntime()
        )

        assert result.failed_count == 0
        assert receipt.review_identity is not None
        _assert_orders_review_outbox_acknowledged(connection, receipt.review_identity)
    finally:
        connection.close()


def test_historical_unknown_issue_remains_an_orders_review_and_is_acknowledged():
    token = uuid4().hex
    raw_issue = "future_order_state:完整客戶名不得寫入錯誤"
    connection = get_connection()
    try:
        case_no, _ = _seed_case(connection, token, "unknown")
        row = HistoricalOrderWorkbookRow(
            3,
            f"historical-orders:{token}:unknown",
            "b" * 64,
            case_no,
            _client_name(case_no),
            HistoricalOrderSourceStatus.DEPOSIT_PAID,
            None,
            None,
            (),
            (raw_issue,),
        )
        workflow = HistoricalOrderAdoptionWorkflow(
            MySqlHistoricalOrderAdoptionRepository(connection),
            lambda: MySqlUnitOfWork(connection), MySqlHistoricalAssignmentWriter(connection),
        )
        preview = workflow.preview(row)
        receipt = workflow.apply(
            HistoricalOrderAdoptionRequest(
                row, preview.fingerprint, f"historical-workbook:unknown:{token}",
                "historical-workbook-test", "unknown", token,
            )
        )
        assert receipt.review_identity is not None

        result = consume_historical_order_adoption_review_events(
            connection, maximum_events=1, runtime=_OutboxRuntime()
        )
        assert result.delivered_count == 1
        assert result.failed_count == 0

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT outbox.published_at,outbox.attempts,outbox.last_error "
                "FROM historical_order_adoption_outbox outbox "
                "JOIN historical_order_adoption_receipts receipt "
                "ON receipt.id=outbox.receipt_id "
                "WHERE receipt.review_identity=%s "
                "AND outbox.intent_type='historical_order_review_required'",
                (receipt.review_identity,),
            )
            outbox = cursor.fetchone()
            assert outbox["published_at"] is not None
            assert outbox["attempts"] == 0
            assert outbox["last_error"] is None
    finally:
        connection.close()


def test_controlled_deidentified_historical_workbook_rebuilds_and_reimports(tmp_path):
    fixture = Path(__file__).resolve().parents[8] / "document" / "資料庫、資料處理" / "假資料_歷史訂單.xlsx"
    original = load_historical_order_workbook(fixture).rows[0]
    workbook_path = tmp_path / "controlled-source.xlsx"
    book = load_workbook(fixture)
    try:
        case_cell, = (cell for cell in book.active[original.source_row] if str(cell.value) == original.case_no)
        case_cell.value = f"HISTORICAL-FIXTURE-{uuid4().hex[:10]}"
        book.save(workbook_path)
    finally:
        book.close()
    parsed = load_historical_order_workbook(str(workbook_path))
    assert len(parsed.rows) == 1
    source_row = parsed.rows[0]
    assert source_row.case_no is not None
    assert source_row.client_name is not None
    connection = get_connection()
    try:
        _seed_controlled_source_roots(connection, source_row)
        service = _service(connection)
        preview = service.preview(str(workbook_path))
        receipt = service.apply(
            str(workbook_path), "historical-workbook:controlled-deidentified-source",
            preview.preview_fingerprint, "historical-workbook-test", "controlled-deidentified-source",
        )
        repeat = service.preview(str(workbook_path))
        replay = service.apply(
            str(workbook_path), "historical-workbook:controlled-deidentified-source:repeat",
            repeat.preview_fingerprint, "historical-workbook-test", "controlled-deidentified-source",
        )

        assert preview.source_row_count == 1
        assert receipt.adopted_count == 1
        assert replay.replayed_workbook is False
        assert replay.assignments_created == 0
        assert _order_status(connection, source_row.case_no) == "歷史訂單－服務完成"
    finally:
        connection.close()


def _seed_original_partial_payment(connection, case_no):
    obligation = f"client-obligation:{case_no}:first"
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO client_finance_accounts (case_no,aggregate_version) VALUES (%s,1)", (case_no,))
        cursor.execute(
            "INSERT INTO client_obligation_events "
            "(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,"
            "after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) "
            "VALUES (%s,%s,'first','receivable_from_client','established',0,12000,'2026-10-20',%s,0,%s,'test','original installment')",
            (obligation, case_no, f"{case_no}:original-terms", f"{case_no}:original-obligation"),
        )
        event_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO client_obligations "
            "(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) "
            "VALUES (%s,%s,'first','receivable_from_client',4000,'2026-10-20','open',%s,1)",
            (obligation, case_no, event_id),
        )
        cursor.execute(
            "INSERT INTO client_ledger_entries "
            "(case_no,entry_type,amount_ntd,occurred_on,reconciliation_reference,idempotency_key,actor,reason) "
            "VALUES (%s,'receipt',8000,'2026-10-20',%s,%s,'test','original receipt')",
            (case_no, f"{case_no}:original-receipt", f"{case_no}:receipt-key"),
        )
        cursor.execute(
            "INSERT INTO client_ledger_obligation_allocations "
            "(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) VALUES (%s,%s,8000,1)",
            (cursor.lastrowid, obligation),
        )
    connection.commit()


def _accounting_snapshot(connection, case_no, *, expected_revisions=0):
    with connection.cursor() as cursor:
        snapshot = []
        for statement in (
            "SELECT obligation_identity,amount_due_ntd,due_date,current_event_id FROM client_obligations WHERE case_no=%s ORDER BY obligation_identity",
            "SELECT id,after_amount_ntd FROM client_obligation_events WHERE case_no=%s ORDER BY id",
            "SELECT e.id,e.amount_ntd,a.obligation_identity,a.amount_ntd AS allocated FROM client_ledger_entries e "
            "JOIN client_ledger_obligation_allocations a ON a.ledger_entry_id=e.id WHERE e.case_no=%s ORDER BY e.id,a.allocation_ordinal",
            "SELECT obligation_identity,amount_due_ntd,due_date,current_event_id FROM staff_obligations WHERE case_no=%s ORDER BY obligation_identity",
            "SELECT id FROM historical_service_day_events WHERE case_no=%s ORDER BY id",
        ):
            cursor.execute(statement, (case_no,))
            snapshot.append(cursor.fetchall())
    assert [row["amount_due_ntd"] for row in snapshot[0]] == [4000]
    assert [row["allocated"] for row in snapshot[2]] == [8000]
    assert len(snapshot[4]) == expected_revisions
    return snapshot


def _service(connection):
    workflow = HistoricalOrderAdoptionWorkflow(
        MySqlHistoricalOrderAdoptionRepository(connection), lambda: MySqlUnitOfWork(connection),
        MySqlHistoricalAssignmentWriter(connection),
        matching_pending_deposit=MySqlHistoricalPendingDepositMatchingRepository(connection),
    )
    return HistoricalOrderWorkbookImportService(
        HistoricalOrderWorkbookImportRepository(connection),
        workflow,
        lambda: MySqlUnitOfWork(connection),
    )
def _seed_controlled_source_roots(connection, source_row):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM clients WHERE case_no=%s", (source_row.case_no,))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO clients (case_no,name) VALUES (%s,%s)", (source_row.case_no, source_row.client_name))
            cursor.execute(
                "INSERT INTO orders (case_no,client_id,status,lifecycle_version) VALUES (%s,%s,'洽談中',0)",
                (source_row.case_no, cursor.lastrowid),
            )
            seed_accounting_basis(cursor, source_row.case_no)
        for caregiver in source_row.caregivers:
            cursor.execute("SELECT id FROM staff WHERE name=%s", (caregiver.name,))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO staff (name,identity_card) VALUES (%s,%s)",
                    (caregiver.name, f"W{uuid4().hex[:9]}"),
                )
    connection.commit()


def _seed_case(connection, token, suffix):
    case_no = f"HISTORICAL-WORKBOOK-{suffix}-{token[:10]}"
    client_name = f"historical-workbook-client-{suffix}-{token[:6]}"
    staff_name = f"historical-workbook-staff-{suffix}-{token[:6]}"
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO clients (case_no,name) VALUES (%s,%s)", (case_no, client_name))
        cursor.execute(
            "INSERT INTO orders (case_no,client_id,status,lifecycle_version) VALUES (%s,%s,'洽談中',0)",
            (case_no, cursor.lastrowid),
        )
        seed_accounting_basis(cursor, case_no)
        cursor.execute("INSERT INTO staff (name,identity_card) VALUES (%s,%s)", (staff_name, f"W{uuid4().hex[:10]}"))
    connection.commit()
    return (case_no, staff_name)


def _write_workbook(tmp_path, first_case, first_staff, second_case, second_staff, second_staff_two):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "任意來源"
    sheet.append([
        "客戶姓名", "案件編號", "開始日期", "結束日期", "狀態", "月嫂姓名", "月嫂姓名2",
    ])
    sheet.append([
        _client_name(first_case), first_case, date(2025, 1, 2), date(2025, 1, 31), 1, first_staff, None,
    ])
    sheet.append([_client_name(second_case), second_case, None, None, 1, second_staff, second_staff_two, None, None])
    destination = tmp_path / "workbook.xlsx"
    workbook.save(destination)
    return destination


def _write_single_workbook(destination, case_no, staff_name, status):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "任意來源"
    sheet.append(["客戶姓名", "案件編號", "開始日期", "結束日期", "狀態", "月嫂姓名"])
    sheet.append([_client_name(case_no), case_no, date(2025, 1, 2), date(2025, 1, 31), status, staff_name])
    workbook.save(destination)
    return destination


def _write_status_workbook(destination, case_statuses):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "六欄狀態驗收"
    sheet.append(["客戶姓名", "案件編號", "開始日期", "結束日期", "狀態", "月嫂姓名"])
    for case_no, status in case_statuses:
        suffix, token = case_no.removeprefix("HISTORICAL-WORKBOOK-").rsplit("-", 1)
        staff_name = f"historical-workbook-staff-{suffix}-{token[:6]}"
        sheet.append([_client_name(case_no), case_no, None, None, status, staff_name])
    workbook.save(destination)
    return destination


def _client_name(case_no):
    suffix, token = case_no.removeprefix("HISTORICAL-WORKBOOK-").rsplit("-", 1)
    return f"historical-workbook-client-{suffix}-{token[:6]}"


def _seed_staff(connection, token, suffix):
    staff_name = f"historical-workbook-staff-{suffix}-{token[:6]}"
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO staff (name,identity_card) VALUES (%s,%s)", (staff_name, f"W{token[:8]}{suffix[:2]}"))
    connection.commit()
    return staff_name


def _assert_assignment_and_evidence(connection, first_case, second_case):
    assert _count(connection, "case_staff_assignments", first_case) == 1
    assert _count(connection, "case_staff_assignments", second_case) == 0
    assert _count(connection, "historical_order_pairing_evidence", first_case, via_receipt=True) == 1
    assert _count(connection, "historical_order_pairing_evidence", second_case, via_receipt=True) == 1


def _assert_orders_review_outbox_acknowledged(connection, review_identity):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT review_identity FROM historical_order_adoption_reviews "
            "WHERE review_identity=%s",
            (review_identity,),
        )
        assert cursor.fetchone() == {"review_identity": review_identity}
        cursor.execute(
            "SELECT published_at,attempts,last_error FROM historical_order_adoption_outbox outbox "
            "JOIN historical_order_adoption_receipts receipt ON receipt.id=outbox.receipt_id "
            "WHERE receipt.review_identity=%s AND outbox.intent_type='historical_order_review_required'",
            (review_identity,),
        )
        assert cursor.fetchone()["published_at"] is not None


def _order_status(connection, case_no):
    with connection.cursor() as cursor:
        cursor.execute("SELECT status FROM orders WHERE case_no=%s", (case_no,))
        return cursor.fetchone()["status"]


def _count(connection, table_name, case_no, *, via_receipt=False):
    with connection.cursor() as cursor:
        if via_receipt:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM historical_order_pairing_evidence evidence "
                "JOIN historical_order_adoption_receipts receipt ON receipt.id=evidence.receipt_id WHERE receipt.case_no=%s",
                (case_no,),
            )
        else:
            cursor.execute(f"SELECT COUNT(*) AS count FROM {table_name} WHERE case_no=%s", (case_no,))
        return int(cursor.fetchone()["count"])


def _raise_after_domain_writes(*_args):
    raise RuntimeError("historical_workbook_forced_outbox_failure")
