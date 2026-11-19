"""Historical continuation uses committed owner facts and never infers a cutoff."""
from datetime import date
import json
import sqlite3

import pytest

from infrastructure.mysql.order_notification_continuation_query_repository import (
    notification_continuation_columns, notification_continuation_from_row,
    notification_continuation_eligible_sql,
)
from subsystems.orders.notification_continuation_query import OrderNotificationContinuationFacts


@pytest.fixture
def database():
    connection=sqlite3.connect(':memory:')
    connection.row_factory=sqlite3.Row
    connection.create_function('JSON_UNQUOTE',1,lambda value:value)
    connection.executescript("""
        CREATE TABLE orders(case_no TEXT,status TEXT,actual_start_date TEXT,contract_identity TEXT);
        CREATE TABLE historical_order_adoption_receipts(case_no TEXT,outcome TEXT);
        CREATE TABLE order_lifecycle_state_events(id INTEGER PRIMARY KEY,case_no TEXT,trigger_event TEXT,
            before_status TEXT,after_status TEXT,business_date TEXT,facts_snapshot TEXT);
        CREATE TABLE scheduling_aggregates(case_no TEXT,effective_generation_id INTEGER);
        CREATE TABLE scheduling_generations(id INTEGER PRIMARY KEY,case_no TEXT,status TEXT,effective_marker INTEGER);
        CREATE TABLE case_staff_assignments(id INTEGER PRIMARY KEY,case_no TEXT,generation_id INTEGER,status TEXT);
        CREATE TABLE staff_schedule(case_no TEXT,assignment_id INTEGER,generation_id INTEGER,effective_marker INTEGER,is_work_day INTEGER);
        CREATE TABLE order_actual_start_apply_receipts(case_no TEXT,lifecycle_event_id INTEGER,
            scheduling_command_receipt_id INTEGER,actual_start_date TEXT);
        CREATE TABLE order_contract_flow_events(case_no TEXT,event_type TEXT,contract_identity TEXT);
        CREATE TABLE client_obligations(case_no TEXT,obligation_type TEXT,obligation_identity TEXT,projection_version INTEGER,
            current_event_id INTEGER,due_date TEXT,amount_due_ntd INTEGER,direction TEXT,status TEXT);
        CREATE TABLE client_obligation_events(id INTEGER PRIMARY KEY,after_amount_ntd INTEGER);
    """)
    yield connection
    connection.close()


def facts(connection):
    row=connection.execute('SELECT '+notification_continuation_columns('o')+' FROM orders o').fetchone()
    return notification_continuation_from_row(row)


def historical(connection):
    connection.execute("INSERT INTO orders VALUES ('H','訂單成立',NULL,'unsigned')")
    connection.execute("INSERT INTO historical_order_adoption_receipts VALUES ('H','adopted')")
    connection.execute("INSERT INTO order_lifecycle_state_events VALUES (1,'H','orders_historical_precision_restart',"
        "'歷史訂單－未服務','訂單成立','2026-11-01','{}')")


def schedule(connection):
    connection.execute("INSERT INTO scheduling_aggregates VALUES ('H',9)")
    connection.execute("INSERT INTO scheduling_generations VALUES (9,'H','effective',1)")
    connection.execute("INSERT INTO case_staff_assignments VALUES (9,'H',9,'planned')")
    connection.execute("INSERT INTO staff_schedule VALUES ('H',9,9,1,1)")


def test_general_order_keeps_pre_service_notification_eligibility(database):
    database.execute("INSERT INTO orders VALUES ('G','洽談中',NULL,'general')")
    current=facts(database)
    assert not current.historical and current.eligible
    assert current.allows_automatic_payment(date(2026,1,1))


def test_restart_date_only_empty_generation_and_completed_history_never_qualify(database):
    historical(database)
    assert not facts(database).eligible
    database.execute("UPDATE orders SET actual_start_date='2026-10-01'")
    assert not facts(database).eligible
    database.execute("INSERT INTO scheduling_aggregates VALUES ('H',9)")
    database.execute("INSERT INTO scheduling_generations VALUES (9,'H','effective',1)")
    assert not facts(database).eligible
    database.execute("INSERT INTO case_staff_assignments VALUES (9,'H',9,'planned')")
    assert not facts(database).eligible
    database.execute("INSERT INTO staff_schedule VALUES ('H',9,9,1,1)")
    assert facts(database).eligible
    for status in ('歷史訂單－服務完成','歷史訂單－帳務完成','訂單完成'):
        database.execute('UPDATE orders SET status=?',(status,))
        assert not facts(database).eligible


def test_old_arrangement_without_frozen_date_has_no_automatic_cutoff(database):
    historical(database);schedule(database)
    database.execute("UPDATE orders SET actual_start_date='2026-10-01'")
    database.execute("INSERT INTO order_lifecycle_state_events VALUES (2,'H','orders_historical_restart_arrangement',"
        "'訂單成立','服務中','2026-11-03','{}')")
    current=facts(database)
    assert current.eligible and current.continuation_day is None
    assert not current.allows_automatic_payment(date(2026,12,1))


@pytest.mark.parametrize('trigger',['orders_historical_restart_arrangement','actual_start_confirmed'])
def test_proven_first_continuation_day_survives_later_schedule_replacement(database,trigger):
    historical(database);schedule(database)
    database.execute("UPDATE orders SET actual_start_date='2026-10-01'")
    snapshot=json.dumps({'actual_start_date':'2026-10-01'}) if trigger=='orders_historical_restart_arrangement' else '{}'
    database.execute('INSERT INTO order_lifecycle_state_events VALUES (2,?,?,?,?,?,?)',
        ('H',trigger,'訂單成立','服務中','2026-11-03',snapshot))
    if trigger=='actual_start_confirmed':
        database.execute("INSERT INTO order_actual_start_apply_receipts VALUES ('H',2,12,'2026-10-01')")
    database.execute("INSERT INTO order_lifecycle_state_events VALUES (3,'H','orders_historical_restart_arrangement',"
        "'服務中','服務中','2026-11-15',?)",(json.dumps({'actual_start_date':'2026-10-01'}),))
    database.execute("INSERT INTO scheduling_generations VALUES (10,'H','effective',1)")
    database.execute("UPDATE scheduling_generations SET status='cancelled',effective_marker=NULL WHERE id=9")
    database.execute('UPDATE scheduling_aggregates SET effective_generation_id=10')
    database.execute("UPDATE case_staff_assignments SET generation_id=10")
    database.execute('UPDATE staff_schedule SET generation_id=10')
    current=facts(database)
    assert current.continuation_day==date(2026,11,3)
    assert not current.allows_automatic_payment(date(2026,11,2))
    assert current.allows_automatic_payment(date(2026,11,3))
    assert current.allows_automatic_payment(date(2026,11,4))


def test_historical_unsigned_old_debt_is_in_internal_overdue_query_only_when_ready(database):
    from infrastructure.mysql.overdue_payment_query_repository import _FROM,_SELECT
    historical(database)
    database.execute("INSERT INTO client_obligation_events VALUES (1,100)")
    database.execute("INSERT INTO client_obligations VALUES ('H','deposit','H:deposit',1,1,'2026-10-01',100,'receivable_from_client','open')")
    assert not database.execute(_SELECT+_FROM).fetchall()
    schedule(database)
    database.execute("UPDATE orders SET actual_start_date='2026-10-01'")
    rows=database.execute(_SELECT+_FROM).fetchall()
    assert len(rows)==1 and rows[0]['due_date']=='2026-10-01'
    assert facts(database).eligible and not facts(database).allows_automatic_payment(date(2026,10,1))
    assert database.execute('SELECT COUNT(*) FROM orders o WHERE '+notification_continuation_eligible_sql('o')).fetchone()[0]==1


def test_adapter_does_not_treat_missing_projection_columns_as_general():
    with pytest.raises(KeyError):
        notification_continuation_from_row({})
    assert OrderNotificationContinuationFacts().eligible
