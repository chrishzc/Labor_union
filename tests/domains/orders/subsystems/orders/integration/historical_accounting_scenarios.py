"""Synthetic historical cases with real receipts and no invented daily schedules."""
from argparse import Namespace
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import runpy
from uuid import uuid4

import pymysql
from domains.orders.historical_adoption import HistoricalOrderSourceStatus
from infrastructure.mysql import mysql_adapter
from infrastructure.mysql.historical_assignment_writer import MySqlHistoricalAssignmentWriter
from infrastructure.mysql.historical_order_adoption_repository import MySqlHistoricalOrderAdoptionRepository
from infrastructure.mysql.case_manual_supplement_repository import MySqlCaseManualSupplementRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from infrastructure.mysql.nas_mutations import ensure_nas_procedures
from subsystems.finance_import.case_manual_supplement import CaseManualSupplementService
from subsystems.orders.historical_adoption_workflow import HistoricalOrderAdoptionRequest, HistoricalOrderAdoptionWorkflow
from subsystems.orders.historical_order_workbook import HistoricalCaregiverSource, HistoricalOrderWorkbookRow
from shared_kernel.fingerprints import fingerprint_payload
from decimal import Decimal
from domains.client_finance.pricing_policy import CasePricingTerms, HourlyRates, IdentityRule
from subsystems.client_finance.pricing_configuration import pricing_payload

_basis_path=Path(__file__).parents[1]/'modules/historical-adoption/integration/historical_accounting_fixture.py'
_seed_basis=runpy.run_path(str(_basis_path))['seed_accounting_basis']


@dataclass(frozen=True)
class HistoricalScenario:
    case_no: str
    staff_id: int
    assignment_id: int
    client_obligation: str
    staff_obligation: str
    bank_row_id: int
    original_client_paid: int
    original_staff_paid: int
    original_expected: int


@contextmanager
def scenario_database():
    config=mysql_adapter._database_config_from_environment()
    assert config['host'] in {'127.0.0.1','localhost'}
    assert os.getenv('APP_ENV','development')=='development'
    name='lu_test_historical_accounting_'+uuid4().hex[:12]
    bootstrap(Namespace(**{key:config[key] for key in ('host','port','user','password')},database=name,confirm_database=name))
    connection=pymysql.connect(**config|{'database':name,'cursorclass':pymysql.cursors.DictCursor,'autocommit':False})
    try:
        ensure_nas_procedures(connection)
        with connection.cursor() as cursor:
            cursor.execute("INSERT IGNORE INTO payroll_rate_policies(policy_version,policy_kind,hourly_rate_ntd,effective_from) VALUES ('approved-rates-v1','citizen',300,'2024-01-01')")
        connection.commit()
        yield connection
    finally:
        connection.rollback();connection.close()
        assert name.startswith('lu_test_historical_accounting_')
        server=pymysql.connect(**{k:v for k,v in config.items() if k!='database'})
        try:
            with server.cursor() as cursor:cursor.execute(f'DROP DATABASE `{name}`')
        finally:server.close()


def create_historical_scenario(connection, case_no, *, paid=24000, waiting=24000, excess_rate=300, legacy_identity=False, subsidy_return=False, client_stage='first'):
    """Import confirmed historic roots; preserve original obligations and actual cash evidence."""
    staff_name='合成歷史月嫂 '+case_no
    client_obligation=f'historical-original:{case_no}:{client_stage}'
    original_expected = 40 * 300 + 200 * excess_rate
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO clients(case_no,name,identity_status) VALUES (%s,'合成歷史客戶','一般市民')",(case_no,))
        cursor.execute("INSERT INTO orders(case_no,client_id,status,lifecycle_version,service_start_time,service_end_time,service_end_day_offset) VALUES (%s,%s,'洽談中',0,'09:00:00','17:00:00',0)",(case_no,cursor.lastrowid))
        cursor.execute("INSERT INTO staff(name) VALUES (%s)",(staff_name,));staff_id=cursor.lastrowid
        staff_obligation = (f'historical-original:{case_no}:service' if legacy_identity
                            else f'staff-obligation:{case_no}:{staff_id}')
        cursor.execute("INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,1)",(case_no,))
        cursor.execute("INSERT INTO payroll_case_accounts(case_no,aggregate_version) VALUES (%s,1)",(case_no,))
        cursor.execute("INSERT INTO scheduling_aggregates(case_no) VALUES (%s)",(case_no,))
        _seed_basis(cursor,case_no)
        cursor.execute("UPDATE orders SET staff_payment_due_date='2025-02-15' WHERE case_no=%s", (case_no,))
        if excess_rate != 300:
            pricing = CasePricingTerms('一般市民', IdentityRule.CITIZEN, Decimal(40),
                HourlyRates(300, excess_rate), HourlyRates(300, excess_rate))
            cursor.execute("INSERT INTO case_pricing_events(case_no,resulting_revision,pricing_json,actor,reason,created_at_utc) VALUES (%s,1,%s,'synthetic','原歷史個案計價證據',UTC_TIMESTAMP(6))",
                (case_no, json.dumps(pricing_payload(pricing), ensure_ascii=False)))
            cursor.execute('UPDATE orders SET pricing_override_event_id=%s,pricing_revision=1 WHERE case_no=%s',
                (cursor.lastrowid, case_no))
        cursor.execute("INSERT INTO case_staff_assignments(case_no,staff_id,assignment_sequence,assigned_start_date,assigned_end_date,status) VALUES (%s,%s,1,'2025-01-02','2025-01-31','completed')",(case_no,staff_id));assignment_id=cursor.lastrowid
        cursor.execute("INSERT INTO assignment_payroll_rate_snapshots(assignment_id,policy_version,policy_kind,hourly_rate_ntd,source_identity_status) VALUES (%s,'approved-rates-v1','citizen',300,'一般市民')",(assignment_id,))
        cursor.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) VALUES (%s,%s,%s,'receivable_from_client','established',0,%s,'2025-02-15',%s,0,%s,'synthetic','原歷史期款證據')",(client_obligation,case_no,client_stage,original_expected,case_no+'-original',case_no+'-client-original'))
        cursor.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES (%s,%s,%s,'receivable_from_client',%s,'2025-02-15','open',%s,1)",(client_obligation,case_no,client_stage,original_expected,cursor.lastrowid))
        cursor.execute("INSERT INTO staff_obligation_events(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,event_type,before_amount_ntd,after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,resulting_payroll_version,idempotency_key,actor,reason) VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff','established',0,%s,'2025-02-15',%s,0,1,%s,'synthetic','原歷史應付證據')",(staff_obligation,assignment_id,case_no,staff_id,original_expected,'a'*64,case_no+'-staff-original'))
        cursor.execute("INSERT INTO staff_obligations(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,amount_due_ntd,due_date,status,current_event_id,payroll_version) VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff',%s,'2025-02-15','open',%s,1)",(staff_obligation,assignment_id,case_no,staff_id,original_expected,cursor.lastrowid))
        if subsidy_return:
            identity = f'historical-original:{case_no}:subsidy-return'
            cursor.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) VALUES (%s,%s,'subsidy_return','payable_to_client','established',0,12000,'2025-03-15',%s,1,%s,'synthetic','原歷史補助退款證據')",
                (identity,case_no,case_no+'-subsidy-original',case_no+'-subsidy-original'))
            cursor.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES (%s,%s,'subsidy_return','payable_to_client',12000,'2025-03-15','open',%s,2)", (identity,case_no,cursor.lastrowid))
            cursor.execute('UPDATE client_finance_accounts SET aggregate_version=2 WHERE case_no=%s',(case_no,))
    connection.commit()
    service=CaseManualSupplementService(MySqlCaseManualSupplementRepository(connection))
    if paid:
        for direction,target in (('client_receipt',client_obligation),('staff_salary',staff_obligation)):
            with MySqlUnitOfWork(connection) as unit:
                service.execute(case_no,'sinopac',direction,target,paid,'2025-02-15','合成原收付款',case_no+'-'+direction,'synthetic',settlement_mode='exact' if paid==original_expected else 'partial')
                unit.commit()
    original_case = HistoricalScenario(case_no, staff_id, assignment_id, client_obligation,
        staff_obligation, 0, paid, paid, original_expected)
    original_cash = cash_snapshot(connection, original_case)
    row=HistoricalOrderWorkbookRow(2,case_no+'-historical-source',fingerprint_payload({'case':case_no,'synthetic':True}).value,
        case_no,'合成歷史客戶',HistoricalOrderSourceStatus.DEPOSIT_PAID,date(2025,1,2),date(2025,1,31),
        (HistoricalCaregiverSource(1,staff_name,date(2025,1,2),date(2025,1,31),True,()),),())
    workflow=HistoricalOrderAdoptionWorkflow(MySqlHistoricalOrderAdoptionRepository(connection),lambda:MySqlUnitOfWork(connection),MySqlHistoricalAssignmentWriter(connection))
    preview=workflow.preview(row)
    request=HistoricalOrderAdoptionRequest(row,preview.fingerprint,case_no+'-adopt','synthetic','合成歷史承接',case_no+'-adopt')
    workflow.apply(request)
    assert workflow.apply(request).replayed
    assert cash_snapshot(connection,original_case)==original_cash
    with connection.cursor() as cursor:
        account='99781699'+case_no[:3]+case_no[-3:]
        cursor.execute("INSERT INTO client_legacy_virtual_accounts(case_no,virtual_account,source_content_digest,source_row,created_by) VALUES (%s,%s,%s,2,'synthetic')",(case_no,account,'b'*64))
        cursor.execute("INSERT INTO finance_import_batches(format_id,sheet_name,header_row,row_count) VALUES ('sinopac','synthetic historical',1,1)");batch=cursor.lastrowid
        cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,batch_id,format_id,transaction_date,credit,direction,cancellation_code,bank_references,warnings,raw_payload,classification_type) VALUES (%s,%s,'sinopac','2025-02-15',%s,'incoming',%s,%s,'[]','{}','client_receipt')",(hashlib.sha256(uuid4().bytes).hexdigest(),batch,waiting,account,json.dumps({'銷帳編號':account})))
        bank_row=cursor.lastrowid
        cursor.execute("INSERT INTO finance_import_classification_events(batch_id,finance_import_row_id,classification_version,canonical_fact_version,classification_type,disposition,decision_facts_fingerprint,target_identities,evidence,available_actions,actor,reason) VALUES (%s,%s,1,1,'client_receipt','manual_review',%s,%s,'[]','[]','synthetic','原流水待更正後核銷')",(batch,bank_row,'a'*64,json.dumps([client_obligation])))
    connection.commit()
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) n FROM staff_schedule WHERE case_no=%s',(case_no,));assert cursor.fetchone()['n']==0
        cursor.execute("SELECT COUNT(*) n FROM historical_order_adoption_receipts WHERE case_no=%s AND outcome='adopted'",(case_no,));assert cursor.fetchone()['n']==1
    return HistoricalScenario(case_no,staff_id,assignment_id,client_obligation,staff_obligation,bank_row,paid,paid,original_expected)


def cash_snapshot(connection, case):
    with connection.cursor() as cursor:
        result={}
        statements={
            'client_cash':('SELECT * FROM client_ledger_entries WHERE case_no=%s ORDER BY id',(case.case_no,)),
            'client_allocations':('SELECT a.* FROM client_ledger_obligation_allocations a JOIN client_ledger_entries e ON e.id=a.ledger_entry_id WHERE e.case_no=%s ORDER BY a.id',(case.case_no,)),
            'staff_cash':('SELECT e.* FROM staff_payout_events e JOIN staff_payout_obligation_links l ON l.payout_event_id=e.id WHERE l.obligation_identity=%s ORDER BY e.id',(case.staff_obligation,)),
            'staff_allocations':('SELECT * FROM staff_payout_obligation_links WHERE obligation_identity=%s ORDER BY id',(case.staff_obligation,)),
        }
        for name,(sql,params) in statements.items():cursor.execute(sql,params);result[name]=cursor.fetchall()
        return result
