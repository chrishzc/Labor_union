"""Disposable-MySQL proof for the client registry receipt summary."""

from __future__ import annotations

import os
from argparse import Namespace
from uuid import uuid4

import pymysql
import pytest

from infrastructure.mysql.client_registry_query_repository import (
    _client_service_received_total,
)
from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_registry_receipt_summary_includes_paid_adjustment_obligation() -> None:
    bootstrap(_arguments())
    case_no = f"REG-{uuid4().hex[:16]}"
    connection = _connection()
    try:
        _seed_paid_stage_and_adjustment(connection, case_no)

        with connection.cursor() as cursor:
            received_total = _client_service_received_total(cursor, case_no)

        assert received_total == 70000
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
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _seed_paid_stage_and_adjustment(connection, case_no: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO clients(case_no,name) VALUES (%s,'Registry Client')",
            (case_no,),
        )
        client_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO orders(case_no,client_id,status) VALUES (%s,%s,'訂單完成')",
            (case_no, client_id),
        )
        cursor.execute(
            "INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,2)",
            (case_no,),
        )
        for ordinal, (obligation_type, amount) in enumerate(
            (("first", 60000), ("adjustment", 10000)), start=1
        ):
            obligation_identity = f"{case_no}:{obligation_type}"
            cursor.execute(
                "INSERT INTO client_obligation_events "
                "(obligation_identity,case_no,obligation_type,direction,event_type,"
                "before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,"
                "source_event_identity,source_obligation_identity,expected_account_version,"
                "idempotency_key,actor,reason) VALUES "
                "(%s,%s,%s,'receivable_from_client','established',0,%s,NULL,'2026-10-01',"
                "%s,NULL,%s,%s,'test','fixture')",
                (
                    obligation_identity,
                    case_no,
                    obligation_type,
                    amount,
                    f"registry-root:{case_no}:{ordinal}",
                    ordinal - 1,
                    f"registry-root:{case_no}:{ordinal}",
                ),
            )
            event_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO client_obligations "
                "(obligation_identity,case_no,obligation_type,direction,"
                "source_obligation_identity,amount_due_ntd,due_date,status,"
                "current_event_id,projection_version) VALUES "
                "(%s,%s,%s,'receivable_from_client',NULL,0,'2026-10-01','settled',%s,1)",
                (obligation_identity, case_no, obligation_type, event_id),
            )
            cursor.execute(
                "INSERT INTO client_ledger_entries "
                "(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,"
                "reconciliation_reference,reversal_of_entry_id,idempotency_key,actor,reason) "
                "VALUES (%s,NULL,'receipt',%s,'2026-10-01',%s,NULL,%s,'test','fixture')",
                (
                    case_no,
                    amount,
                    f"registry-receipt:{case_no}:{ordinal}",
                    f"registry-receipt:{case_no}:{ordinal}",
                ),
            )
            ledger_entry_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO client_ledger_obligation_allocations "
                "(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) "
                "VALUES (%s,%s,%s,1)",
                (ledger_entry_id, obligation_identity, amount),
            )
    connection.commit()
