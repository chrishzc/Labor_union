"""Disposable MySQL proof for Actual Start without Scheduling/Finance/Payroll roots."""

from argparse import Namespace
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import json
import os

import pymysql
import pytest

from infrastructure.mysql.order_actual_start_repository import (
    MySqlOrderActualStartRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.matching_schedule_confirmation_repository import MySqlMatchingScheduleConfirmationRepository
from infrastructure.mysql.service_date_adjustment_repository import (
    MySqlServiceDateAdjustmentRepository,
    _active_pairs,
    _load_formal_receipts,
)
from infrastructure.mysql.service_date_confirmation_repository import MySqlServiceDateConfirmationRepository
from domains.orders.service_date_confirmation import ConfirmedServiceDateCandidate
from domains.scheduling.service_date_adjustment import AdjustmentTarget, ServiceDay, plan_service_date_adjustment
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.orders.actual_start_workflow import (
    ActualStartDateOnlyApplyRequest,
    ActualStartWorkflow,
    ActualStartWorkflowError,
)
from subsystems.scheduling.service_date_adjustment import ServiceDateAdjustmentIntent, ServiceDateAdjustmentPreview


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def _arguments(database: str) -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=database,
        confirm_database=database,
    )


def _connect(database: str):
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _seed_order(connection, case_no):
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO clients(case_no,name,identity_status,city,address,service_time,service_type) "
            "VALUES (%s,%s,'一般市民','新竹市','東區','09:00-17:00','連續服務')",
            (case_no, f"{case_no} client"),
        )
        client_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,end_date,"
            "service_days,service_hours_per_day,requires_cooking,floor_fee,service_start_time,"
            "service_end_time,service_end_day_offset,actual_start_date) "
            "VALUES (%s,%s,'洽談中',1,'2026-09-03','2026-09-04',2,8,0,0,"
            "'09:00:00','17:00:00',0,NULL)",
            (case_no, client_id),
        )
    connection.commit()


def _snapshot(connection, case_no):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT actual_start_date,lifecycle_version,status,actual_end_date "
            "FROM orders WHERE case_no=%s",
            (case_no,),
        )
        order = cursor.fetchone()
        counts = {}
        for name, table in {
            "scheduling": "scheduling_aggregates",
            "finance": "client_finance_accounts",
            "payroll": "payroll_case_accounts",
            "actual_start_events": "order_actual_start_events",
            "actual_start_receipts": "order_actual_start_apply_receipts",
            "lifecycle_events": "order_lifecycle_state_events",
        }.items():
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table} WHERE case_no=%s", (case_no,))
            counts[name] = int(cursor.fetchone()["total"])
    return order, counts


def test_date_only_first_save_and_correction_do_not_bootstrap_downstream_roots():
    database = f"{DATABASE}_actual_start_date_only"
    bootstrap(_arguments(database))
    connection = _connect(database)
    case_no = "DATE-ONLY-001"
    try:
        _seed_order(connection, case_no)
        repository = MySqlOrderActualStartRepository(connection)
        workflow = ActualStartWorkflow(
            repository,
            lambda: MySqlUnitOfWork(connection),
            FixedBusinessClock(datetime(2026, 9, 2, tzinfo=TAIPEI_TIME_ZONE)),
        )

        first_query = repository.load_actual_start_query(case_no, for_update=False)
        first_preview = workflow.preview_date_only(first_query, date(2026, 9, 4))
        first = workflow.apply_date_only(ActualStartDateOnlyApplyRequest(
            case_no,
            date(2026, 9, 4),
            ExpectedVersion(first_query.order_version),
            first_preview.fingerprint,
            CorrelationId("date-only-first"),
        ))
        second_query = repository.load_actual_start_query(case_no, for_update=False)
        second_preview = workflow.preview_date_only(second_query, date(2026, 9, 5))
        second = workflow.apply_date_only(ActualStartDateOnlyApplyRequest(
            case_no,
            date(2026, 9, 5),
            ExpectedVersion(second_query.order_version),
            second_preview.fingerprint,
            CorrelationId("date-only-correction"),
        ))
        order, counts = _snapshot(connection, case_no)

        assert first.order_version == 2
        assert second.order_version == 3
        assert order == {
            "actual_start_date": date(2026, 9, 5),
            "lifecycle_version": 3,
            "status": "洽談中",
            "actual_end_date": None,
        }
        assert counts == {
            "scheduling": 0,
            "finance": 0,
            "payroll": 0,
            "actual_start_events": 0,
            "actual_start_receipts": 0,
            "lifecycle_events": 0,
        }
    finally:
        connection.close()


def test_input_start_then_confirm_dates_uses_fresh_versions_without_downstream_roots():
    """#335: the existing two writers accept an earlier/later/cross-month draft after human confirmation."""
    from infrastructure.mysql.service_date_confirmation_repository import MySqlServiceDateConfirmationRepository
    from infrastructure.mysql.matching_schedule_confirmation_repository import MySqlMatchingScheduleConfirmationRepository
    from subsystems.orders.service_date_confirmation_workflow import ServiceDateConfirmationWorkflow
    from datetime import timedelta

    database = f"{DATABASE}_service_dates"
    bootstrap(_arguments(database))
    connection = _connect(database)
    try:
        for ordinal, start_date in enumerate((date(2026, 8, 30), date(2026, 9, 15), date(2026, 9, 30))):
            case_no = f"INPUT-335-{ordinal}"
            _seed_order(connection, case_no)
            actual_repository = MySqlOrderActualStartRepository(connection)
            actual_workflow = ActualStartWorkflow(actual_repository, lambda: MySqlUnitOfWork(connection),
                FixedBusinessClock(datetime(2026, 9, 2, tzinfo=TAIPEI_TIME_ZONE)))
            dates_workflow = ServiceDateConfirmationWorkflow(MySqlServiceDateConfirmationRepository(connection),
                lambda: MySqlUnitOfWork(connection), MySqlMatchingScheduleConfirmationRepository(connection))
            selected = (start_date, start_date + timedelta(days=1))
            initial = actual_repository.load_actual_start_query(case_no, for_update=False)
            preview = actual_workflow.preview_date_only(initial, start_date)
            before, before_counts = _snapshot(connection, case_no)
            assert before["actual_start_date"] is None
            assert not any(before_counts.values())

            start_result = actual_workflow.apply_date_only(ActualStartDateOnlyApplyRequest(case_no, start_date,
                ExpectedVersion(initial.order_version), preview.fingerprint, CorrelationId(f"input-335-{ordinal}")))
            current = dates_workflow.query(case_no)
            assert current.order_version == start_result.order_version == 2
            assert current.selectable_dates[0] == start_date
            # A failure here leaves only the date saved; a later Preview can safely continue.
            with pytest.raises(ValueError, match="outside_selectable_range"):
                dates_workflow.preview(case_no, (start_date - timedelta(days=1), start_date))
            assert dates_workflow.query(case_no).current_version is None
            candidate = dates_workflow.preview(case_no, selected)
            receipt = dates_workflow.apply(case_no, selected, expected_order_version=current.order_version,
                expected_scheduling_version=current.scheduling_version, preview_fingerprint=candidate.candidate.fingerprint.value,
                actor="issue335-test", reason="確認正式服務日期", idempotency_key=f"input-335-dates-{ordinal}")
            observed = dates_workflow.query(case_no)
            after, counts = _snapshot(connection, case_no)
            assert observed.current_version == receipt.confirmed_version == 1
            assert observed.current_dates == selected
            assert after["actual_start_date"] == start_date
            assert after["lifecycle_version"] == 2
            assert after["status"] == before["status"]
            assert not any(counts.values())
            print({"database": database, "case": case_no, "actual_start": start_date.isoformat(),
                   "confirmed_dates": [value.isoformat() for value in observed.current_dates],
                   "confirmed_version": observed.current_version, "downstream_counts": counts})
    finally:
        connection.close()


def test_date_only_reset_restores_normal_days_and_rolls_back_partial_writes(monkeypatch):
    database = f"{DATABASE}_actual_start_reset"
    bootstrap(_arguments(database))
    connection = _connect(database)
    case_no = "DATE-ONLY-RESET"
    first, second = date(2026, 9, 3), date(2026, 9, 4)
    new_start, new_end = date(2026, 9, 5), date(2026, 9, 6)
    try:
        _seed_order(connection, case_no)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE orders SET service_hours_per_day=4,service_end_time='13:00:00' WHERE case_no=%s",
                (case_no,),
            )
            cursor.execute("INSERT INTO staff(name,status) VALUES ('Reset A','active')")
            first_staff = int(cursor.lastrowid)
            cursor.execute("INSERT INTO staff(name,status) VALUES ('Reset B','active')")
            second_staff = int(cursor.lastrowid)

        confirm = MySqlServiceDateConfirmationRepository(connection)
        original = ConfirmedServiceDateCandidate(case_no, 1, 0, (first, second), 2)
        confirm.save(original, actor="admin", reason="fixture", idempotency_key="date-reset-confirm",
                     command_fingerprint=original.fingerprint.value, staff_ids=(first_staff, second_staff))
        adjustments = MySqlServiceDateAdjustmentRepository(connection)
        facts = adjustments.load(case_no)
        intent = ServiceDateAdjustmentIntent((first, second), (AdjustmentTarget(second, second_staff),))
        change = plan_service_date_adjustment(facts.days, Decimal(4), intent.source_dates, intent.targets)
        adjustments.save(
            ServiceDateAdjustmentPreview(facts, change, "a" * 64),
            intent, key="date-reset-merge", fingerprint="a" * 64, actor="admin",
        )
        connection.commit()
        old_adjustments = adjustments.load(case_no)
        assert old_adjustments.days == (ServiceDay(second, second_staff, 8),)
        assert len(old_adjustments.pairs) == 1
        assert old_adjustments.confirmed_version == 2
        before = _snapshot(connection, case_no)

        repository = MySqlOrderActualStartRepository(connection)
        workflow = ActualStartWorkflow(
            repository, lambda: MySqlUnitOfWork(connection),
            FixedBusinessClock(datetime(2026, 9, 2, tzinfo=TAIPEI_TIME_ZONE)),
        )
        facts = repository.load_actual_start_query(case_no, for_update=False)
        unchanged = workflow.preview_date_only(facts, first)
        assert unchanged.service_date_adjustment_reset is None
        preview = workflow.preview_date_only(facts, new_start)
        assert preview.service_date_adjustment_reset.service_dates == (new_start, new_end)
        assert preview.service_date_adjustment_reset.contracted_daily_hours == 4
        assert preview.service_date_adjustment_reset.confirmed_version == 2
        assert _snapshot(connection, case_no) == before
        assert adjustments.load(case_no) == old_adjustments

        unconfirmed = ActualStartDateOnlyApplyRequest(
            case_no, new_start, ExpectedVersion(facts.order_version), preview.fingerprint,
            CorrelationId("date-reset"), idempotency_key=IdempotencyKey("date-reset"),
            actor=ActorContext("admin"),
        )
        with pytest.raises(ActualStartWorkflowError) as rejected:
            workflow.apply_date_only(unconfirmed)
        assert rejected.value.error.code == "actual_start_adjustment_reset_confirmation_mismatch"
        approved = replace(unconfirmed, reset_service_date_adjustments=True)

        def fail_after_confirmed_write(_repository, _case_no):
            raise RuntimeError("matching snapshot invalidation failed")

        with monkeypatch.context() as patch:
            patch.setattr(MySqlMatchingScheduleConfirmationRepository, "invalidate_current_snapshot", fail_after_confirmed_write)
            with pytest.raises(RuntimeError, match="snapshot invalidation failed"):
                workflow.apply_date_only(approved)
        assert _snapshot(connection, case_no) == before
        assert adjustments.load(case_no) == old_adjustments

        receipt = workflow.apply_date_only(approved)
        current = adjustments.load(case_no)
        order, counts = _snapshot(connection, case_no)
        assert (order["actual_start_date"], receipt.order_version) == (new_start, 2)
        assert receipt.scheduling_version is receipt.scheduling_generation is None
        assert current.confirmed_version == receipt.service_date_adjustment_reset.confirmed_version == 3
        assert current.days == (ServiceDay(new_start, first_staff, None), ServiceDay(new_end, second_staff, None))
        assert current.pairs == ()
        assert not any(counts.values())
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM service_date_adjustment_receipts WHERE case_no=%s", (case_no,))
            assert cursor.fetchone()["total"] == 1
        with pytest.raises(ActualStartWorkflowError) as stale:
            workflow.apply_date_only(approved)
        assert stale.value.error.code == "order_version_conflict"
        assert adjustments.load(case_no) == current
    finally:
        connection.close()


def test_formal_adjustment_stays_inactive_after_first_actual_start_reset() -> None:
    database = f"{DATABASE}_formal_reset_barrier"
    bootstrap(_arguments(database))
    connection = _connect(database)
    case_no = "FORMAL-RESET-001"
    first_day, merged_day = date(2026, 9, 3), date(2026, 9, 4)
    current_days = (ServiceDay(merged_day, 2, 8),)
    adjustment_snapshot = {
        "scheduling_version": 5,
        "confirmed_version": None,
        "removed": [
            {"service_date": first_day.isoformat(), "staff_id": 1, "hours_override": 4},
            {"service_date": merged_day.isoformat(), "staff_id": 2, "hours_override": 4},
        ],
        "inserted": [{"service_date": merged_day.isoformat(), "staff_id": 2, "hours_override": 8}],
    }
    reset_snapshot = {
        "service_date_adjustment_reset": {
            "service_dates": [merged_day.isoformat(), "2026-09-05"],
            "contracted_daily_hours": 4,
            "confirmed_version": 1,
        },
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TEMPORARY TABLE scheduling_command_receipts ("
                "id BIGINT PRIMARY KEY, case_no VARCHAR(32), idempotency_key VARCHAR(128), "
                "command_family VARCHAR(64), resulting_scheduling_version BIGINT)"
            )
            cursor.execute(
                "CREATE TEMPORARY TABLE order_actual_start_apply_receipts ("
                "scheduling_command_receipt_id BIGINT, case_no VARCHAR(32), result_snapshot JSON)"
            )
            cursor.execute(
                "CREATE TEMPORARY TABLE order_actual_start_events ("
                "idempotency_key VARCHAR(128), case_no VARCHAR(32), "
                "before_actual_start_date DATE NULL, after_actual_start_date DATE)"
            )
            cursor.execute(
                "CREATE TEMPORARY TABLE service_date_adjustment_receipts ("
                "id BIGINT PRIMARY KEY, case_no VARCHAR(32), reverse_receipt_id BIGINT NULL, result_snapshot JSON)"
            )
            cursor.execute(
                "CREATE TEMPORARY TABLE confirmed_service_date_versions ("
                "case_no VARCHAR(32), version BIGINT, scheduling_version BIGINT)"
            )
            cursor.execute(
                "INSERT INTO scheduling_command_receipts VALUES "
                "(1,%s,'first-actual-start','orders_actual_start_rebuild',6)",
                (case_no,),
            )
            cursor.execute(
                "INSERT INTO order_actual_start_events VALUES ('first-actual-start',%s,NULL,%s)",
                (case_no, merged_day),
            )
            cursor.execute(
                "INSERT INTO order_actual_start_apply_receipts VALUES (1,%s,%s)",
                (case_no, json.dumps(reset_snapshot)),
            )
            cursor.execute(
                "INSERT INTO service_date_adjustment_receipts VALUES (9,%s,NULL,%s)",
                (case_no, json.dumps(adjustment_snapshot)),
            )

            after_reset = _load_formal_receipts(cursor, case_no, None, "")
            assert after_reset == ()
            assert _active_pairs(after_reset, current_days) == ()

            cursor.execute(
                "UPDATE order_actual_start_apply_receipts SET result_snapshot='{}' WHERE case_no=%s",
                (case_no,),
            )
            without_reset = _load_formal_receipts(cursor, case_no, None, "")
            pairs = _active_pairs(without_reset, current_days)
            assert len(pairs) == 1
            assert pairs[0].receipt_id == 9
            assert pairs[0].change.inserted == current_days
    finally:
        connection.close()
