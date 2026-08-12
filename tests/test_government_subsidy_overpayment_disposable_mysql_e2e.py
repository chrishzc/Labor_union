"""Disposable-MySQL proof for government overpayment dispositions and replay."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import replace
import os
from queue import Queue
from threading import Barrier, Thread

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap
from tests.test_government_subsidy_durable_mysql_e2e import _seed_receiptable_batch


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


@pytest.fixture(autouse=True)
def _use_disposable_database(monkeypatch):
    from infrastructure.mysql import mysql_adapter

    monkeypatch.setattr(mysql_adapter, "DB_CONFIG", {
        "host": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        "database": DATABASE,
        "charset": "utf8mb4",
    })


def test_overpayment_offset_replays_once_and_rejects_key_reuse():
    bootstrap(_arguments())
    batch_id, item_id, source_row_id = _seed_receiptable_batch()
    identity = _seed_overpayment(batch_id, source_row_id, "offset", 500)
    application, connection = _application()
    try:
        request = _offset_request(application, identity, item_id)
        first = application.apply_overpayment_offset(request)
        replay = application.apply_overpayment_offset(request)

        assert replay == first
        _assert_offset_persisted(connection, identity, batch_id)
        with pytest.raises(ValueError, match="idempotency_mismatch"):
            application.apply_overpayment_offset(replace(request, reason="different command"))
    finally:
        connection.close()


def test_return_payable_and_early_outgoing_reconciliation_replay_once():
    bootstrap(_arguments())
    batch_id, _item_id, source_row_id = _seed_receiptable_batch()
    identity = _seed_overpayment(batch_id, source_row_id, "return", 500)
    application, connection = _application()
    try:
        _seed_payer_account(connection)
        return_request = _return_request(application, identity)
        return_receipt = application.apply_overpayment_return(return_request)
        assert application.apply_overpayment_return(return_request) == return_receipt

        outgoing_row_id = _seed_early_outgoing_row(connection, 500)
        reconciliation_request = _reconciliation_request(application, identity, outgoing_row_id)
        receipt = application.apply_overpayment_return_reconciliation(reconciliation_request)
        assert application.apply_overpayment_return_reconciliation(reconciliation_request) == receipt
        _assert_return_persisted(connection, identity, outgoing_row_id)
    finally:
        connection.close()


def test_competing_offset_apply_returns_one_durable_receipt_and_writes_once():
    bootstrap(_arguments())
    batch_id, item_id, source_row_id = _seed_receiptable_batch()
    identity = _seed_overpayment(batch_id, source_row_id, "concurrent", 500)
    start = Barrier(2)
    outcomes: Queue[tuple[str, object]] = Queue()
    threads = [
        Thread(
            target=_apply_competing_offset,
            args=(identity, item_id, start, outcomes),
            daemon=True,
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not any(thread.is_alive() for thread in threads)
    results = [outcomes.get_nowait() for _ in range(2)]
    assert [kind for kind, _value in results] == ["receipt", "receipt"], results
    assert results[0][1] == results[1][1]
    verification_application, verification_connection = _application()
    del verification_application
    try:
        _assert_offset_persisted(verification_connection, identity, batch_id)
    finally:
        verification_connection.close()


def _apply_competing_offset(identity: str, item_id: int, start: Barrier, outcomes: Queue) -> None:
    application, connection = _application()
    try:
        request = _offset_request(application, identity, item_id, key="concurrent-offset")
        start.wait(timeout=10)
        outcomes.put(("receipt", application.apply_overpayment_offset(request)))
    except Exception as error:
        outcomes.put(("error", str(error)))
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


def _application():
    from api.dependencies.government_subsidy import build_government_subsidy_application
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    return build_government_subsidy_application(connection), connection


def _seed_overpayment(batch_id: int, source_row_id: int, suffix: str, amount: int) -> str:
    from infrastructure.mysql.mysql_adapter import get_connection

    identity = f"government-overpayment-e2e:{suffix}"
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO government_subsidy_transactions "
                "(claim_batch_id,finance_import_row_id,transaction_type,transaction_status,amount,occurred_at,external_reference,expected_batch_version,resulting_batch_version,preview_fingerprint,idempotency_key,actor,reason,correlation_id) "
                "VALUES (%s,%s,'receipt','succeeded',%s,'2026-08-03',%s,0,1,%s,%s,'test','fixture','fixture')",
                (batch_id, source_row_id, amount, f"overpayment-source:{suffix}", "a" * 64, f"source:{suffix}"),
            )
            transaction_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO government_subsidy_projection_events "
                "(batch_id,transaction_id,before_status,after_status,before_net_allocated_ntd,after_net_allocated_ntd,outstanding_ntd,expected_batch_version,resulting_batch_version,preview_fingerprint,actor,reason,idempotency_key) "
                "VALUES (%s,%s,'approved','approved',0,0,4800,0,1,%s,'test','fixture',%s)",
                (batch_id, transaction_id, "b" * 64, f"projection:{suffix}"),
            )
            cursor.execute(
                "INSERT INTO government_subsidy_overpayments "
                "(overpayment_identity,source_finance_import_row_id,source_transaction_id,payer_identity,original_amount_ntd,remaining_amount_ntd,status,projection_version,actor,reason,evidence_reference) "
                "VALUES (%s,%s,%s,'hccg',%s,%s,'pending_review',1,'test','fixture','notice')",
                (identity, source_row_id, transaction_id, amount, amount),
            )
            cursor.execute(
                "INSERT INTO government_subsidy_overpayment_events "
                "(overpayment_identity,event_type,before_remaining_ntd,after_remaining_ntd,resulting_status,expected_version,resulting_version,preview_fingerprint,idempotency_key,actor,reason,evidence_reference) "
                "VALUES (%s,'established',%s,%s,'pending_review',0,1,%s,%s,'test','fixture','notice')",
                (identity, amount, amount, "c" * 64, f"established:{suffix}"),
            )
        connection.commit()
    finally:
        connection.close()
    return identity


def _offset_request(application, identity: str, item_id: int, *, key="offset-key", reason="offset approved"):
    from domains.government_subsidy.overpayment import GovernmentSubsidyOffsetIntent
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from shared_kernel.money import MoneyNTD
    from subsystems.government_subsidy.overpayment_workflow import OffsetApplyRequest

    intents = (GovernmentSubsidyOffsetIntent(item_id, MoneyNTD(500)),)
    preview = application.preview_overpayment_offset(identity, intents)
    return OffsetApplyRequest(identity, intents, ExpectedVersion(1), preview.fingerprint, IdempotencyKey(key), ActorContext("test"), reason, "notice", CorrelationId(key))


def _return_request(application, identity: str):
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.government_subsidy.overpayment_workflow import ReturnApplyRequest

    preview = application.preview_overpayment_return(identity, "2026-08-15", "notice")
    return ReturnApplyRequest(identity, "2026-08-15", "notice", ExpectedVersion(1), preview.fingerprint, IdempotencyKey("return-key"), ActorContext("test"), "return approved", CorrelationId("return-key"))


def _reconciliation_request(application, identity: str, row_id: int):
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.government_subsidy.overpayment_workflow import ReturnReconciliationApplyRequest

    preview = application.preview_overpayment_return_reconciliation(identity, row_id)
    return ReturnReconciliationApplyRequest(identity, row_id, ExpectedVersion(2), preview.fingerprint, IdempotencyKey("return-reconciliation-key"), ActorContext("test"), "early bank statement", "statement", CorrelationId("return-reconciliation-key"))


def _seed_payer_account(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO government_payer_receiving_accounts "
            "(payer_identity,bank_code,account_number,account_name,effective_from,reason,evidence_reference,created_by) "
            "VALUES ('hccg','004','GOV-RETURN-ACCOUNT','新竹市政府','2026-01-01','fixture','notice','test')"
        )
    connection.commit()


def _seed_early_outgoing_row(connection, amount: int) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO finance_import_rows "
            "(dedup_fingerprint,format_id,transaction_date,debit,credit,direction,currency,resolved_counterparty_account,bank_references,warnings,raw_payload,classification_type) "
            "VALUES (%s,'sinopac','2026-07-01',%s,NULL,'outgoing','TWD','GOV-RETURN-ACCOUNT',JSON_ARRAY(),JSON_ARRAY(),JSON_OBJECT(),'government_subsidy')",
            ("d" * 64, amount),
        )
        row_id = int(cursor.lastrowid)
    connection.commit()
    return row_id


def _assert_offset_persisted(connection, identity: str, batch_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT remaining_amount_ntd,status,projection_version FROM government_subsidy_overpayments WHERE overpayment_identity=%s", (identity,))
        assert cursor.fetchone() == {"remaining_amount_ntd": 0, "status": "offset_applied", "projection_version": 2}
        cursor.execute("SELECT net_allocated_ntd,outstanding_ntd,aggregate_version FROM government_subsidy_batch_accounts WHERE batch_id=%s", (batch_id,))
        assert cursor.fetchone() == {"net_allocated_ntd": 500, "outstanding_ntd": 4300, "aggregate_version": 2}
        cursor.execute("SELECT COUNT(*) count FROM government_subsidy_overpayment_apply_receipts")
        assert cursor.fetchone() == {"count": 1}


def _assert_return_persisted(connection, identity: str, outgoing_row_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT remaining_amount_ntd,status,projection_version FROM government_subsidy_overpayments WHERE overpayment_identity=%s", (identity,))
        assert cursor.fetchone() == {"remaining_amount_ntd": 0, "status": "returned", "projection_version": 3}
        cursor.execute("SELECT COUNT(*) count FROM government_overpayment_return_payouts WHERE finance_import_row_id=%s", (outgoing_row_id,))
        assert cursor.fetchone() == {"count": 1}
        cursor.execute("SELECT COUNT(*) count FROM government_subsidy_overpayment_apply_receipts")
        assert cursor.fetchone() == {"count": 2}
