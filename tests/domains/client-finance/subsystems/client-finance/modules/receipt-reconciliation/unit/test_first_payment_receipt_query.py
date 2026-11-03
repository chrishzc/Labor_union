"""First-stage receipt eligibility is Finance-owned and requires committed exact allocation."""
from contextlib import contextmanager
from types import SimpleNamespace
from datetime import date
import json,sqlite3,pytest
from infrastructure.mysql.first_payment_query_repository import MySqlFirstPaymentQueryRepository
from infrastructure.mysql.client_receipt_reconciliation_repository import _append_projection_outbox
from domains.client_finance.reconciliation import PaymentStage
from shared_kernel.identities import IdempotencyKey


class Connection:
    def __init__(self,raw):self.raw=raw;self.reads=[]
    @contextmanager
    def cursor(self):
        owner=self
        class Cursor:
            def execute(self,sql,params=()):
                owner.reads.append(sql);self.cursor=owner.raw.execute(sql.replace('%s','?').replace(' FOR UPDATE',''),params)
            def fetchone(self):
                row=self.cursor.fetchone();return dict(row) if row else None
            def fetchall(self):return tuple(dict(row) for row in self.cursor.fetchall())
        yield Cursor()


@pytest.fixture
def first():
    raw=sqlite3.connect(':memory:');raw.row_factory=sqlite3.Row
    raw.create_function('JSON_UNQUOTE',1,lambda value:value)
    raw.executescript("""
      CREATE TABLE client_finance_accounts(case_no TEXT,aggregate_version INTEGER);
      CREATE TABLE client_payment_terms(case_no TEXT,first_payment_due_date DATE);
      CREATE TABLE client_obligations(obligation_identity TEXT,case_no TEXT,obligation_type TEXT,direction TEXT,status TEXT,amount_due_ntd INTEGER,current_event_id INTEGER);
      CREATE TABLE client_obligation_events(id INTEGER,after_amount_ntd INTEGER);
      CREATE TABLE client_finance_outbox(case_no TEXT,intent_type TEXT,payload_snapshot TEXT);
      CREATE TABLE client_ledger_entries(id INTEGER,entry_type TEXT,reconciliation_reference TEXT,reversal_of_entry_id INTEGER);
      CREATE TABLE client_ledger_obligation_allocations(ledger_entry_id INTEGER,obligation_identity TEXT,amount_ntd INTEGER);
      INSERT INTO client_finance_accounts VALUES ('CASE-FIRST',2);
      INSERT INTO client_payment_terms VALUES ('CASE-FIRST','2026-11-05');
      INSERT INTO client_obligations VALUES ('first-one','CASE-FIRST','first','receivable_from_client','settled',0,1);
      INSERT INTO client_obligation_events VALUES (1,12000);
      INSERT INTO client_ledger_entries VALUES (1,'receipt','receipt-one',NULL);
      INSERT INTO client_ledger_obligation_allocations VALUES (1,'first-one',12000);
    """)
    payload={'line_first_payment_notification':True,'settlement_identity':'receipt-one','obligation_identities':['first-one'],'amount_ntd':12000}
    raw.execute("INSERT INTO client_finance_outbox VALUES ('CASE-FIRST','projection_refresh',?)",(json.dumps(payload),))
    raw.commit();conn=Connection(raw)
    yield raw,conn,MySqlFirstPaymentQueryRepository(conn)
    raw.close()


def test_first_receipt_requires_exact_settlement_and_queries_are_readonly(first):
    raw,conn,query=first
    result=query.settlement('CASE-FIRST','receipt-one',lock=True)
    assert result and result.settled_amount==12000 and result.remaining_amount==0
    assert result.obligation_identity=='first-one'
    assert all(sql.startswith('SELECT') for sql in conn.reads)


@pytest.mark.parametrize('change',[
    "UPDATE client_obligations SET status='open',amount_due_ntd=1000",
    "UPDATE client_obligation_events SET after_amount_ntd=0",
    "DELETE FROM client_finance_outbox",
    "UPDATE client_ledger_obligation_allocations SET amount_ntd=11000",
    "UPDATE client_ledger_entries SET reconciliation_reference='foreign'",
    "INSERT INTO client_ledger_entries VALUES (2,'reversal','reversed',1)",
    "INSERT INTO client_obligations VALUES ('ambiguous','CASE-FIRST','first','receivable_from_client','settled',0,1)",
])
def test_partial_ambiguous_unmarked_or_reversed_first_receipt_is_not_eligible(first,change):
    raw,_,query=first;raw.execute(change)
    assert query.settlement('CASE-FIRST','receipt-one') is None


def test_first_receipt_identity_and_case_are_not_substituted(first):
    _,_,query=first
    assert query.settlement('CASE-FIRST','other-receipt') is None
    assert query.settlement('OTHER-CASE','receipt-one') is None


def test_existing_reconciliation_outbox_marks_first_stage_in_the_same_writer():
    writes=[]
    cursor=SimpleNamespace(execute=lambda sql,params:writes.append((sql,params)))
    request=SimpleNamespace(selection=SimpleNamespace(case_no='CASE-FIRST',payment_stage=PaymentStage.FIRST,obligation_identities=('first-one',)),idempotency_key=IdempotencyKey('first-receipt'))
    _append_projection_outbox(cursor,request,'receipt-one',2,{'first-one':12000})
    payload=next(json.loads(value) for value in writes[0][1] if isinstance(value,str) and value.startswith('{'))
    assert payload['line_first_payment_notification'] is True and payload['payment_stage']=='first'
    assert payload['amount_ntd']==12000 and payload['obligation_identities']==['first-one']
    assert 'line_second_payment_notification' not in payload
