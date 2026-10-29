"""Shared real-accounting setup for historical-adoption native regressions."""

from infrastructure.mysql.historical_service_accounting_repository import MySqlHistoricalServiceAccountingRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.orders.historical_service_accounting_workflow import HistoricalServiceAccountingWorkflow


def default_accounting(connection):
    return HistoricalServiceAccountingWorkflow(
        MySqlHistoricalServiceAccountingRepository(connection), lambda: MySqlUnitOfWork(connection),
    )

def seed_accounting_basis(cursor, case_no):
    cursor.execute("UPDATE clients SET identity_status='一般市民' WHERE case_no=%s", (case_no,))
    cursor.execute("UPDATE orders SET service_days=30,service_hours_per_day=8,floor_fee=0,"
                   "start_date='2025-02-01',end_date='2025-03-02' WHERE case_no=%s", (case_no,))
    cursor.execute(
        "INSERT INTO client_payment_terms_events(case_no,policy_version,client_hourly_rate_ntd,"
        "deposit_service_days,deposit_due_date,first_payment_due_date,second_payment_due_date,"
        "expected_account_version,source_event_identity,idempotency_key,actor,reason) "
        "VALUES (%s,'historical-fixture-v1',300,0,'2025-01-01','2025-01-02',NULL,0,%s,%s,'test','fixture')",
        (case_no, case_no+'-terms-source', case_no+'-terms-key'),
    )
    event_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO client_payment_terms(case_no,policy_version,client_hourly_rate_ntd,"
        "deposit_service_days,deposit_due_date,first_payment_due_date,second_payment_due_date,current_event_id) "
        "VALUES (%s,'historical-fixture-v1',300,0,'2025-01-01','2025-01-02',NULL,%s)",
        (case_no, event_id),
    )
    cursor.execute(
        "INSERT INTO case_architecture_bootstrap_events(case_no,order_version,client_payment_terms_event_id,"
        "client_policy_version,client_hourly_rate_ntd,payroll_policy_version,payroll_policy_kind,"
        "payroll_hourly_rate_ntd,source_identity_status,candidate_fingerprint,idempotency_key,actor,reason,correlation_id) "
        "VALUES (%s,0,%s,'historical-fixture-v1',300,'approved-rates-v1','citizen',300,'一般市民',%s,%s,'test','fixture',%s)",
        (case_no, event_id, 'a'*64, case_no+'-bootstrap', case_no+'-bootstrap-correlation'),
    )
    cursor.execute(
        "INSERT INTO case_payroll_rate_policy_snapshots(case_no,policy_version,policy_kind,hourly_rate_ntd,"
        "source_identity_status,source_event_id) VALUES (%s,'approved-rates-v1','citizen',300,'一般市民',%s)",
        (case_no, cursor.lastrowid),
    )
