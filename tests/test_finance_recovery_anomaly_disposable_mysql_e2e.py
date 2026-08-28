"""
File: test_finance_recovery_anomaly_disposable_mysql_e2e.py
Description: 以隔離 MySQL 驗證三類財務追償只在完整 owner 規則成立後解除異常。
"""

from __future__ import annotations

from argparse import Namespace
import hashlib
import json
import os
from uuid import uuid4

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


@pytest.fixture(scope="module", autouse=True)
def _bootstrap_database() -> None:
    bootstrap(_arguments())


@pytest.fixture(autouse=True)
def _use_disposable_database(monkeypatch) -> None:
    from infrastructure.mysql import mysql_adapter

    monkeypatch.setattr(
        mysql_adapter,
        "DB_CONFIG",
        {
            "host": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
            "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
            "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
            "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
            "database": DATABASE,
            "charset": "utf8mb4",
        },
    )


def test_government_disposition_removes_only_completed_root_from_active_list() -> None:
    from subsystems.anomalies.government_overpayment_anomaly_consumer import (
        consume_government_overpayment_anomaly_events,
    )
    from tests.test_government_subsidy_durable_mysql_e2e import (
        _seed_receiptable_batch,
    )
    from tests.test_government_subsidy_overpayment_disposable_mysql_e2e import (
        _application,
        _offset_request,
        _seed_overpayment,
    )

    batch_id, item_id, source_row_id = _seed_receiptable_batch()
    identity = _seed_overpayment(batch_id, source_row_id, "anomaly-lifecycle", 500)
    _enqueue_government_established(batch_id, identity)

    connection = _connection()
    try:
        assert consume_government_overpayment_anomaly_events(connection) == (1, 0)
        _assert_alert(connection, "GOVSUB-006", f"government-overpayment:{identity}", True, 500)
    finally:
        connection.close()

    application, owner_connection = _application()
    try:
        request = _offset_request(
            application,
            identity,
            item_id,
            key="government-anomaly-offset",
        )
        receipt = application.apply_overpayment_offset(request)
        assert application.apply_overpayment_offset(request) == receipt
    finally:
        owner_connection.close()

    connection = _connection()
    try:
        assert consume_government_overpayment_anomaly_events(connection) == (1, 0)
        _assert_alert(connection, "GOVSUB-006", f"government-overpayment:{identity}", False, 0)
        assert consume_government_overpayment_anomaly_events(connection) == (0, 0)
        _assert_not_active(connection, "GOVSUB-006", f"government-overpayment:{identity}")
    finally:
        connection.close()


def test_client_partial_stays_active_and_recovered_root_is_removed() -> None:
    from subsystems.anomalies.client_over_refund_recovery_anomaly_consumer import (
        consume_client_over_refund_recovery_anomaly_events,
    )

    identity = "client-recovery:task96-mysql"
    case_no = "TASK96-CLIENT-RECOVERY"
    _seed_client_recovery(case_no, identity, 500)

    connection = _connection()
    try:
        assert consume_client_over_refund_recovery_anomaly_events(connection) == (1, 0)
        source_identity = f"client-over-refund-recovery:{identity}"
        _assert_alert(connection, "client_over_refund_recovery_open", source_identity, True, 500)

        _advance_client_recovery(connection, case_no, identity, 200, "partially_recovered", 2)
        assert consume_client_over_refund_recovery_anomaly_events(connection) == (1, 0)
        _assert_alert(connection, "client_over_refund_recovery_open", source_identity, True, 200)

        _advance_client_recovery(connection, case_no, identity, 0, "recovered", 3)
        assert consume_client_over_refund_recovery_anomaly_events(connection) == (1, 0)
        _assert_alert(connection, "client_over_refund_recovery_open", source_identity, False, 0)
        assert consume_client_over_refund_recovery_anomaly_events(connection) == (0, 0)
        _assert_not_active(connection, "client_over_refund_recovery_open", source_identity)
    finally:
        connection.close()


def test_staff_partial_stays_active_and_recovered_root_is_removed() -> None:
    from subsystems.anomalies.staff_overpayment_recovery_anomaly_consumer import (
        consume_staff_overpayment_recovery_anomaly_events,
    )
    from api.dependencies.staff_payout import build_staff_payout_application
    from domains.staff_payables.reconciliation import (
        StaffPayoutDifferenceMode,
        StaffPayoutEventType,
    )
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.staff_payables.payout_reconciliation import (
        StaffPayoutApplyRequest,
        StaffPayoutSelection,
    )

    staff_id, bank_row_id, obligation_identity = _seed_staff_payout_difference()
    connection = _connection()
    try:
        selection = StaffPayoutSelection(
            StaffPayoutEventType.PAYOUT,
            (str(bank_row_id),),
            (obligation_identity,),
            difference_mode=StaffPayoutDifferenceMode.OVERPAYMENT,
        )
        application = build_staff_payout_application(connection)
        preview = application.preview(selection, CorrelationId(f"staff-preview:{uuid4().hex}"))
        request = StaffPayoutApplyRequest(
            selection,
            ExpectedVersion(preview.staff_payables_version),
            ExpectedVersion(preview.bank_facts_version),
            preview.fingerprint,
            IdempotencyKey(f"staff-overpayment:{uuid4().hex}"),
            ActorContext("task96-staff-payout"),
            "establish staff overpayment recovery for anomaly lifecycle",
            CorrelationId(f"staff-apply:{uuid4().hex}"),
        )
        payout_receipt = application.apply(request)
        identity = payout_receipt.recovery_identity
        assert identity is not None
        assert payout_receipt.recovery_amount_ntd == 600
        _assert_established_outbox(connection, staff_id, identity)
    finally:
        connection.close()

    connection = _connection()
    try:
        from subsystems.anomalies.staff_payout_difference_anomaly_consumer import (
            consume_staff_payout_difference_anomaly_events,
        )

        assert consume_staff_payout_difference_anomaly_events(connection) == (1, 0)
        old_source_identity = _old_payout_source_identity(connection, identity)
        _assert_alert(connection, "staff_payout_overpayment", old_source_identity, True, 0)

        assert consume_staff_overpayment_recovery_anomaly_events(connection) == (1, 0)
        source_identity = f"staff-overpayment-recovery:{identity}"
        _assert_alert(connection, "staff_overpayment_recovery_open", source_identity, True, 600)
        assert _occurrence_count(connection, "staff_payout_overpayment", old_source_identity) == 1
        assert _occurrence_count(connection, "staff_overpayment_recovery_open", source_identity) == 1

        old_alert = _load_alert_identity(connection, "staff_payout_overpayment", old_source_identity)
        assert _reclassify_old_payout_alert(old_alert, identity) is True
        _assert_alert(connection, "staff_payout_overpayment", old_source_identity, False, 0)
        _assert_alert(connection, "staff_overpayment_recovery_open", source_identity, True, 600)
        assert _occurrence_count(connection, "staff_payout_overpayment", old_source_identity) == 1
        assert _occurrence_count(connection, "staff_overpayment_recovery_open", source_identity) == 1

        _advance_staff_recovery(connection, staff_id, identity, 250, "partially_recovered", 1)
        assert consume_staff_overpayment_recovery_anomaly_events(connection) == (1, 0)
        _assert_alert(connection, "staff_overpayment_recovery_open", source_identity, True, 250)

        _advance_staff_recovery(connection, staff_id, identity, 0, "recovered", 2)
        assert consume_staff_overpayment_recovery_anomaly_events(connection) == (1, 0)
        _assert_alert(connection, "staff_overpayment_recovery_open", source_identity, False, 0)
        assert consume_staff_overpayment_recovery_anomaly_events(connection) == (0, 0)
        _assert_not_active(connection, "staff_overpayment_recovery_open", source_identity)
    finally:
        connection.close()


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def _connection():
    from infrastructure.mysql.mysql_adapter import get_connection

    return get_connection()


def _enqueue_government_established(batch_id: int, identity: str) -> None:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_transaction_id,source_finance_import_row_id "
                "FROM government_subsidy_overpayments "
                "WHERE overpayment_identity=%s",
                (identity,),
            )
            source = cursor.fetchone()
            transaction_id = int(source["source_transaction_id"])
            cursor.execute(
                "INSERT INTO finance_import_batches(format_id,sheet_name,header_row,row_count,status) "
                "VALUES ('sinopac','task96-government',1,1,'completed')"
            )
            finance_import_batch_id = int(cursor.lastrowid)
            cursor.execute(
                "UPDATE finance_import_rows SET batch_id=%s WHERE id=%s AND batch_id IS NULL",
                (finance_import_batch_id, int(source["source_finance_import_row_id"])),
            )
            assert cursor.rowcount == 1
            cursor.execute(
                "SELECT id FROM government_subsidy_projection_events "
                "WHERE transaction_id=%s ORDER BY id DESC LIMIT 1",
                (transaction_id,),
            )
            projection_event_id = int(cursor.fetchone()["id"])
            cursor.execute(
                "INSERT INTO government_subsidy_outbox "
                "(batch_id,transaction_id,projection_event_id,intent_key,intent_type,payload_snapshot) "
                "VALUES (%s,%s,%s,%s,'government_subsidy_overpayment_established',%s)",
                (
                    batch_id,
                    transaction_id,
                    projection_event_id,
                    f"government-overpayment-established:{identity}",
                    json.dumps({"overpayment_identity": identity}, sort_keys=True),
                ),
            )
        connection.commit()
    finally:
        connection.close()


def _seed_client_recovery(case_no: str, identity: str, amount: int) -> None:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES (%s,'Task 96 Client')", (case_no,))
            client_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO orders(case_no,client_id,status) VALUES (%s,%s,'訂單完成')",
                (case_no, client_id),
            )
            cursor.execute(
                "INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,1)",
                (case_no,),
            )
            cursor.execute(
                "INSERT INTO finance_import_batches(format_id,sheet_name,header_row,row_count,status) "
                "VALUES ('taishin','task96',1,1,'completed')"
            )
            batch_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO finance_import_rows "
                "(dedup_fingerprint,batch_id,format_id,transaction_date,debit,credit,direction,currency,"
                "bank_references,warnings,raw_payload,classification_type) "
                "VALUES (%s,%s,'taishin','2026-08-27',%s,NULL,'outgoing','TWD',"
                "JSON_OBJECT(),JSON_ARRAY(),JSON_OBJECT(),'client_refund')",
                (_digest(f"client-bank:{identity}"), batch_id, amount),
            )
            bank_row_id = int(cursor.lastrowid)
            obligation_identity = f"refund:{case_no}"
            cursor.execute(
                "INSERT INTO client_obligation_events "
                "(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,"
                "after_amount_ntd,before_due_date,after_due_date,source_event_identity,"
                "source_obligation_identity,expected_account_version,idempotency_key,actor,reason) "
                "VALUES (%s,%s,'refund','payable_to_client','established',0,%s,NULL,'2026-08-27',"
                "%s,NULL,0,%s,'task96','fixture')",
                (obligation_identity, case_no, amount, f"client-obligation:{identity}", f"client-obligation:{identity}"),
            )
            obligation_event_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO client_obligations "
                "(obligation_identity,case_no,obligation_type,direction,source_obligation_identity,"
                "amount_due_ntd,due_date,status,current_event_id,projection_version) "
                "VALUES (%s,%s,'refund','payable_to_client',NULL,%s,'2026-08-27','settled',%s,1)",
                (obligation_identity, case_no, 0, obligation_event_id),
            )
            cursor.execute(
                "INSERT INTO client_ledger_entries "
                "(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,"
                "reconciliation_reference,idempotency_key,actor,reason) "
                "VALUES (%s,%s,'refund',%s,'2026-08-27',%s,%s,'task96','fixture')",
                (case_no, bank_row_id, amount, f"client-ledger:{identity}", f"client-ledger:{identity}"),
            )
            ledger_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO client_over_refund_recoveries "
                "(recovery_identity,case_no,finance_import_row_id,refund_ledger_entry_id,"
                "refund_obligation_identity,amount_due_ntd,status,idempotency_key,actor,reason,projection_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,'open',%s,'task96','fixture',1)",
                (identity, case_no, bank_row_id, ledger_id, obligation_identity, amount, f"client-root:{identity}"),
            )
            cursor.execute(
                "INSERT INTO client_over_refund_recovery_events "
                "(recovery_identity,event_type,before_amount_ntd,after_amount_ntd,idempotency_key,actor,reason) "
                "VALUES (%s,'established',0,%s,%s,'task96','fixture')",
                (identity, amount, f"client-established:{identity}"),
            )
            _insert_client_projection_event(cursor, case_no, identity, "established", 1)
        connection.commit()
    finally:
        connection.close()


def _advance_client_recovery(connection, case_no: str, identity: str, remaining: int, status: str, version: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE client_over_refund_recoveries SET amount_due_ntd=%s,status=%s,projection_version=%s "
            "WHERE recovery_identity=%s",
            (remaining, status, version, identity),
        )
        assert cursor.rowcount == 1
        _insert_client_projection_event(cursor, case_no, identity, "updated", version)
    connection.commit()


def _insert_client_projection_event(cursor, case_no: str, identity: str, event_type: str, version: int) -> None:
    cursor.execute(
        "INSERT INTO client_finance_outbox(case_no,intent_type,intent_key,payload_snapshot) "
        "VALUES (%s,'projection_refresh',%s,%s)",
        (
            case_no,
            f"client-over-refund-recovery-{identity}:{version}",
            json.dumps(
                {"event_type": f"client_over_refund_recovery_{event_type}", "recovery_identity": identity},
                sort_keys=True,
            ),
        ),
    )


def _seed_staff_recovery(identity: str, amount: int) -> int:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO staff(name) VALUES ('Task 96 Staff')")
            staff_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO staff_payable_accounts(staff_id,aggregate_version) VALUES (%s,1)",
                (staff_id,),
            )
            cursor.execute(
                "INSERT INTO finance_import_batches(format_id,sheet_name,header_row,row_count,status) "
                "VALUES ('sinopac','task96-staff',1,1,'completed')"
            )
            batch_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO finance_import_rows "
                "(dedup_fingerprint,batch_id,format_id,transaction_date,debit,credit,direction,currency,"
                "bank_references,warnings,raw_payload,classification_type) "
                "VALUES (%s,%s,'sinopac','2026-08-27',%s,NULL,'outgoing','TWD',"
                "JSON_OBJECT(),JSON_ARRAY(),JSON_OBJECT(),'staff_payout')",
                (_digest(f"staff-bank:{identity}"), batch_id, amount),
            )
            bank_row_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO staff_overpayment_recoveries "
                "(recovery_identity,staff_id,original_amount_ntd,remaining_amount_ntd,status,aggregate_version,"
                "source_bank_fact_identities,source_payout_event_ids,source_obligation_identities,actor,reason) "
                "VALUES (%s,%s,%s,%s,'open',0,%s,JSON_ARRAY(),JSON_ARRAY(),'task96','fixture')",
                (
                    identity,
                    staff_id,
                    amount,
                    amount,
                    json.dumps([f"finance-import-row:{bank_row_id}"]),
                ),
            )
            _insert_staff_projection_event(cursor, staff_id, identity, "established", 0)
        connection.commit()
        return staff_id
    finally:
        connection.close()


def _seed_staff_payout_difference() -> tuple[int, int, str]:
    """Seed only owner roots; formal Staff Payout Apply creates recovery/outbox."""
    from tests.test_assignment_plan_durable_mysql_e2e import _seed_waiting_lock_case
    from tests.test_staff_payout_durable_mysql_e2e import _apply_assignment_plan

    connection = _connection()
    try:
        staff_id = _seed_waiting_lock_case(connection)
        _apply_assignment_plan(connection, staff_id)
        bank_row_id = _seed_payout_roots_for_difference(connection, staff_id)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE finance_import_rows SET debit=3000 WHERE id=%s",
                (bank_row_id,),
            )
        connection.commit()
        return staff_id, bank_row_id, "staff-obligation-durable-payout"
    finally:
        connection.close()


def _seed_payout_roots_for_difference(connection, staff_id: int) -> int:
    """Fixture boundary: canonical assignment/staff roots and one outgoing bank fact."""
    from datetime import date

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM case_staff_assignments WHERE case_no=%s AND staff_id=%s",
            ("AP-DURABLE-1", staff_id),
        )
        assignment_id = int(cursor.fetchone()["id"])
        cursor.execute(
            "SELECT aggregate_version FROM payroll_case_accounts WHERE case_no=%s",
            ("AP-DURABLE-1",),
        )
        payroll_version = int(cursor.fetchone()["aggregate_version"])
        obligation_identity = "staff-obligation-durable-payout"
        cursor.execute(
            "INSERT INTO staff_obligation_events "
            "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,"
            "event_type,before_amount_ntd,after_amount_ntd,due_date,payroll_fingerprint,"
            "expected_payroll_version,resulting_payroll_version,idempotency_key,actor,reason) "
            "VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff','established',0,2400,%s,%s,%s,%s,%s,'task96','fixture')",
            (obligation_identity, assignment_id, "AP-DURABLE-1", staff_id,
             date(2026, 8, 15), "a" * 64, payroll_version, payroll_version + 1,
             f"{obligation_identity}-event"),
        )
        event_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO staff_obligations "
            "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,"
            "amount_due_ntd,due_date,status,current_event_id,payroll_version) "
            "VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff',2400,%s,'open',%s,%s)",
            (obligation_identity, assignment_id, "AP-DURABLE-1", staff_id,
             date(2026, 8, 15), event_id, payroll_version + 1),
        )
        cursor.execute(
            "INSERT INTO staff_bank_accounts "
            "(staff_id,bank_code,branch_code,account_no,is_primary) "
            "VALUES (%s,'001','0001','PAYOUT-ACCOUNT',1)",
            (staff_id,),
        )
        cursor.execute(
            "INSERT INTO finance_import_batches(format_id,sheet_name,header_row,row_count,status) "
            "VALUES ('legacy','task96-staff-difference',1,1,'completed')"
        )
        batch_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO finance_import_rows "
            "(dedup_fingerprint,batch_id,format_id,transaction_date,debit,credit,direction,"
            "currency,resolved_counterparty_account,bank_references,warnings,raw_payload,"
            "classification_type,reconciliation_status) VALUES "
            "(%s,%s,'legacy',%s,2400,0,'outgoing','TWD','PAYOUT-ACCOUNT',"
            "JSON_ARRAY(),JSON_ARRAY(),JSON_OBJECT(),'staff_payout','pending')",
            (_digest("task96-staff-difference-bank"), batch_id, date(2026, 8, 16)),
        )
        bank_row_id = int(cursor.lastrowid)
    connection.commit()
    return bank_row_id


def _advance_staff_recovery(connection, staff_id: int, identity: str, remaining: int, status: str, version: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE staff_overpayment_recoveries SET remaining_amount_ntd=%s,status=%s,aggregate_version=%s "
            "WHERE recovery_identity=%s",
            (remaining, status, version, identity),
        )
        assert cursor.rowcount == 1
        event_type = "collected" if status == "recovered" else "updated"
        _insert_staff_projection_event(cursor, staff_id, identity, event_type, version)
    connection.commit()


def _insert_staff_projection_event(cursor, staff_id: int, identity: str, event_type: str, version: int) -> None:
    intent_type = (
        "staff_overpayment_recovery_collected"
        if event_type == "collected"
        else "staff_overpayment_recovery_updated"
    )
    cursor.execute(
        "INSERT INTO staff_payables_outbox(staff_id,intent_key,intent_type,payload_snapshot) "
        "VALUES (%s,%s,%s,%s)",
        (
            staff_id,
            f"staff-overpayment-recovery:{identity}:{version}",
            intent_type,
            json.dumps(
                {"event_type": f"staff_overpayment_recovery_{event_type}", "recovery_identity": identity},
                sort_keys=True,
            ),
        ),
    )


def _assert_alert(connection, code: str, source_identity: str, active: bool, remaining: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT fingerprint,predicate_active,workflow_status,source_version "
            "FROM anomaly_current_alerts WHERE definition_code=%s AND source_identity=%s",
            (code, source_identity),
        )
        row = cursor.fetchone()
        assert row is not None
        assert bool(row["predicate_active"]) is active
        assert row["workflow_status"] == ("open" if active else "resolved")
        cursor.execute(
            "SELECT amount_delta_ntd FROM anomaly_root_fact_snapshots "
            "WHERE alert_fingerprint=%s",
            (row["fingerprint"],),
        )
        assert cursor.fetchone() == {"amount_delta_ntd": remaining}


def _assert_not_active(connection, code: str, source_identity: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) count FROM anomaly_current_alerts "
            "WHERE definition_code=%s AND source_identity=%s "
            "AND predicate_active=1 AND workflow_status<>'resolved'",
            (code, source_identity),
        )
        assert cursor.fetchone() == {"count": 0}


def _old_payout_source_identity(connection, recovery_identity: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT payout_difference_identity FROM staff_payout_difference_sources "
            "WHERE recovery_identity=%s",
            (recovery_identity,),
        )
        row = cursor.fetchone()
    assert row is not None
    return f"staff-payout-difference:{row['payout_difference_identity']}"


def _assert_established_outbox(connection, staff_id: int, recovery_identity: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT intent_type,payload_snapshot FROM staff_payables_outbox "
            "WHERE staff_id=%s AND intent_type='staff_overpayment_recovery_updated' "
            "ORDER BY id DESC LIMIT 1",
            (staff_id,),
        )
        row = cursor.fetchone()
    assert row is not None
    payload = json.loads(row["payload_snapshot"]) if isinstance(row["payload_snapshot"], str) else row["payload_snapshot"]
    assert row["intent_type"] == "staff_overpayment_recovery_updated"
    assert payload["event_type"] == "staff_overpayment_recovery_established"
    assert payload["recovery_identity"] == recovery_identity

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_bank_fact_identities FROM staff_overpayment_recoveries "
            "WHERE recovery_identity=%s",
            (recovery_identity,),
        )
        source = cursor.fetchone()
    assert source is not None
    assert json.loads(source["source_bank_fact_identities"]) == [
        f"finance-import-row:{_source_bank_row_id(connection, recovery_identity)}"
    ]


def _source_bank_row_id(connection, recovery_identity: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT JSON_UNQUOTE(JSON_EXTRACT(source_bank_fact_identities, '$[0]')) "
            "AS source_identity FROM staff_overpayment_recoveries "
            "WHERE recovery_identity=%s",
            (recovery_identity,),
        )
        row = cursor.fetchone()
    assert row is not None
    return int(str(row["source_identity"]).split(":")[-1])


def _occurrence_count(connection, definition_code: str, source_identity: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM finance_anomaly_occurrences "
            "WHERE definition_code=%s AND source_event_identity LIKE %s",
            (definition_code, f"{source_identity}:%"),
        )
        return int(cursor.fetchone()["count"])


def _load_alert_identity(connection, definition_code: str, source_identity: str):
    from domains.anomalies.maintenance import AnomalyReclassificationAlertIdentity
    from shared_kernel.fingerprints import PreviewFingerprint

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT fingerprint,definition_code,source_identity,source_version,workflow_version "
            "FROM anomaly_current_alerts WHERE definition_code=%s AND source_identity=%s",
            (definition_code, source_identity),
        )
        row = cursor.fetchone()
    assert row is not None
    return AnomalyReclassificationAlertIdentity(
        PreviewFingerprint(str(row["fingerprint"])),
        str(row["definition_code"]),
        str(row["source_identity"]),
        int(row["source_version"]),
        int(row["workflow_version"]),
    )


def _reclassify_old_payout_alert(old_alert, recovery_identity: str) -> bool:
    from api.dependencies.anomaly_recovery import _maintenance_application
    from domains.anomalies.maintenance import (
        AnomalyReclassificationApplyRequest,
        AnomalyReclassificationDisposition,
        AnomalyReclassificationTargetBinding,
    )
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey

    source_connection = get_connection()
    projection_connection = get_connection()
    try:
        with source_connection.cursor() as cursor:
            cursor.execute(
                "SELECT aggregate_version FROM staff_overpayment_recoveries "
                "WHERE recovery_identity=%s",
                (recovery_identity,),
            )
            row = cursor.fetchone()
        assert row is not None
        target = AnomalyReclassificationTargetBinding(
            "staff_payables", recovery_identity, int(row["aggregate_version"])
        )
        actor = ActorContext("task96-anm-nm-c", ("system.administration",))
        app = _maintenance_application(source_connection, projection_connection)
        preview = app.preview_reclassification(
            old_alert,
            AnomalyReclassificationDisposition.REPLACED_BY_SUCCESSOR,
            target,
            actor,
            "staff payout overpayment replaced by established recovery successor",
            "test-scenario:task96-anm-nm-c",
            "document/架構重整/01_規格基線/06_Anomalies_Domain.md#異常必要性與一般工作項分界",
            "document/架構重整/03_追蹤清單與證據/evidence/2026-08-27_anomaly_rulebook_oracle_matrix.md#staff_payout_overpayment",
        )
        request = AnomalyReclassificationApplyRequest.from_preview(
            preview,
            idempotency_key=IdempotencyKey(f"task96-anm-nm-c:{uuid4().hex}"),
            correlation_id=CorrelationId(f"task96-anm-nm-c:{uuid4().hex}"),
        )
        receipt = app.apply_reclassification(request)
        replay = app.apply_reclassification(request)
        assert receipt.resulting_predicate_active is False
        assert replay.replayed is True
        return True
    finally:
        projection_connection.close()
        source_connection.close()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
