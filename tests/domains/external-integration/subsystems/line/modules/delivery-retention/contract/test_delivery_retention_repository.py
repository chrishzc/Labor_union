"""Execute the owner SQL against isolated SQLite; MySQL trigger tests live with migration."""
from contextlib import AbstractContextManager
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from types import SimpleNamespace

from pymysql.err import IntegrityError
import pytest

from domains.line.delivery import LineDeliveryRequest, LineDeliveryStatus, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineDeliveryTaskId, LineUserId
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.line_receipt_outbox_audit import MySqlLineIdempotencyReceiptRepository
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.delivery_retention import LineDeliveryRetentionApplication, RETENTION_PAYLOAD


NOW=datetime(2026,11,18,1,2,tzinfo=timezone.utc)
OLD=datetime(2025,1,1,1,2)


class Cursor(AbstractContextManager):
    def __init__(self,connection):self.connection=connection;self.inner=connection.db.cursor()
    def __exit__(self,*_):self.inner.close()
    def execute(self,sql,parameters=()):
        if sql.startswith('SET @line_delivery_retention_key'):
            self.connection.retention_key=parameters[0] if parameters else None
            return
        if self.connection.fail_redaction and sql.startswith('UPDATE line_delivery_tasks SET payload_snapshot'):
            raise RuntimeError('synthetic redaction failure')
        if sql.startswith('DELETE FROM line_delivery_attempt_events'):
            assert self.connection.retention_key
            assert self.connection.db.execute('SELECT COUNT(*) FROM line_command_receipts WHERE idempotency_key=?',
                (self.connection.retention_key,)).fetchone()[0]==1
        sql=sql.replace(' FOR UPDATE','').replace('%s','?')
        try:self.inner.execute(sql,parameters)
        except sqlite3.IntegrityError as error:raise IntegrityError(1062,str(error)) from error
    @property
    def rowcount(self):return self.inner.rowcount
    @property
    def lastrowid(self):return self.inner.lastrowid
    def fetchone(self):
        row=self.inner.fetchone()
        if row is None:return None
        result=dict(zip((column[0] for column in self.inner.description),row))
        for name,value in tuple(result.items()):
            if name.endswith('_utc') and value is not None:result[name]=datetime.fromisoformat(value)
        return result
    def fetchall(self):
        result=[]
        while (row:=self.fetchone()) is not None:result.append(row)
        return result


class Connection:
    def __init__(self):
        self.db=sqlite3.connect(':memory:')
        self.db.create_function('JSON_UNQUOTE',1,lambda value: 'true' if value==1 else 'false' if value==0 else value)
        self.retention_key=None
        self.fail_redaction=False
    def cursor(self):return Cursor(self)


@pytest.fixture
def connection():
    connection=Connection()
    connection.db.executescript('''
    CREATE TABLE line_delivery_tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,recipient_type TEXT,recipient_identity TEXT,
      message_kind TEXT,payload_snapshot TEXT,payload_fingerprint TEXT,scheduled_at_utc TEXT,
      source_aggregate_type TEXT,source_aggregate_identity TEXT,idempotency_key TEXT UNIQUE,correlation_id TEXT,
      processing_status TEXT DEFAULT 'pending',completed_attempts INTEGER DEFAULT 0,max_attempts INTEGER DEFAULT 3,
      next_attempt_at_utc TEXT,lease_owner TEXT,lease_acquired_at_utc TEXT,lease_expires_at_utc TEXT,
      updated_at_utc TEXT,error_code TEXT,error_message TEXT);
    CREATE TABLE line_delivery_attempt_events(id INTEGER PRIMARY KEY,task_id INTEGER,attempt_number INTEGER,
      error_code TEXT,completed_at_utc TEXT);
    CREATE TABLE line_notification_intents(id INTEGER PRIMARY KEY,delivery_task_id INTEGER,intent_status TEXT,
      payload_snapshot TEXT,payload_fingerprint TEXT);
    CREATE TABLE line_command_receipts(idempotency_key TEXT PRIMARY KEY,command_family TEXT,payload_fingerprint TEXT,
      result_reference TEXT,correlation_id TEXT,result_snapshot TEXT);
    ''')
    yield connection
    connection.db.close()


def seed(connection,key='synthetic-original',**changes):
    request=LineDeliveryRequest(LineRecipient(LineRecipientType.USER,LineUserId('U'+'1'*32)),LineMessageKind.TEXT,
        '{"text":"synthetic confidential content","type":"text"}',OLD.replace(tzinfo=timezone.utc),
        IdempotencyKey(key),CorrelationId('synthetic-correlation'),'order','SYNTH-RETENTION')
    repo=MySqlLineDeliveryTaskRepository(connection)
    task_id=repo.enqueue(request).task_id
    values={'processing_status':'sent','updated_at_utc':OLD.isoformat(sep=' '),'completed_attempts':1,
            'error_message':'synthetic detailed provider error',**changes}
    connection.db.execute('UPDATE line_delivery_tasks SET '+','.join(name+'=?' for name in values)+' WHERE id=?',
        (*values.values(),task_id.value))
    connection.db.execute('INSERT INTO line_delivery_attempt_events VALUES(?,?,?,?,?)',
        (task_id.value,task_id.value,1,None,OLD.isoformat(sep=' ')))
    connection.db.execute('INSERT INTO line_notification_intents VALUES(?,?,?,?,?)',
        (task_id.value,task_id.value,'provider_accepted',request.payload_json,request.fingerprint.value))
    connection.db.commit()
    return task_id,request


class Unit:
    def __init__(self,connection):
        self.connection=connection
        self.delivery_tasks=MySqlLineDeliveryTaskRepository(connection)
        self.receipts=MySqlLineIdempotencyReceiptRepository(connection)
        self.audit=SimpleNamespace(append=lambda _:None)
    def __enter__(self):return self
    def __exit__(self,*_):self.connection.db.rollback()
    def commit(self):self.connection.db.commit()


def test_actual_owner_sql_redacts_both_payloads_deletes_attempts_and_retains_original_dedup(connection):
    task_id,request=seed(connection)
    other_id,_=seed(connection,key='other',processing_status='pending')
    app=LineDeliveryRetentionApplication(lambda:Unit(connection),lambda:NOW,'synthetic-worker')
    assert app.run_once()==1
    task=connection.db.execute('SELECT payload_snapshot,payload_fingerprint,error_message,updated_at_utc,completed_attempts '
        'FROM line_delivery_tasks WHERE id=?',(task_id.value,)).fetchone()
    assert task==(RETENTION_PAYLOAD,request.fingerprint.value,None,OLD.isoformat(sep=' '),1)
    assert connection.db.execute('SELECT payload_snapshot FROM line_notification_intents WHERE delivery_task_id=?',
        (task_id.value,)).fetchone()[0]==RETENTION_PAYLOAD
    assert connection.db.execute('SELECT COUNT(*) FROM line_delivery_attempt_events WHERE task_id=?',(task_id.value,)).fetchone()[0]==0
    assert connection.db.execute('SELECT payload_snapshot FROM line_delivery_tasks WHERE id=?',(other_id.value,)).fetchone()[0]!=RETENTION_PAYLOAD
    assert connection.retention_key is None
    assert app.run_once()==0
    replay=MySqlLineDeliveryTaskRepository(connection).enqueue(request)
    assert replay.task_id==task_id and replay.status is LineDeliveryStatus.SENT
    assert connection.db.execute('SELECT COUNT(*) FROM line_delivery_tasks').fetchone()[0]==2
    snapshot=json.loads(connection.db.execute('SELECT result_snapshot FROM line_command_receipts').fetchone()[0])
    assert set(snapshot)=={'task_id','cutoff','expired_at'}


def test_redaction_failure_rolls_back_attempt_delete_intent_payload_and_receipt(connection):
    task_id,request=seed(connection)
    connection.fail_redaction=True
    with pytest.raises(RuntimeError,match='synthetic redaction failure'):
        LineDeliveryRetentionApplication(lambda:Unit(connection),lambda:NOW,'synthetic-worker').run_once()
    assert connection.retention_key is None
    assert connection.db.execute('SELECT COUNT(*) FROM line_delivery_attempt_events').fetchone()[0]==1
    assert connection.db.execute('SELECT COUNT(*) FROM line_command_receipts').fetchone()[0]==0
    assert connection.db.execute('SELECT payload_snapshot FROM line_notification_intents').fetchone()[0]==request.payload_json
    assert connection.db.execute('SELECT payload_snapshot FROM line_delivery_tasks').fetchone()[0]==request.payload_json


@pytest.mark.parametrize('change',[
    "UPDATE line_notification_intents SET intent_status='scheduled'",
    "UPDATE line_delivery_tasks SET completed_attempts=2",
    "UPDATE line_delivery_tasks SET lease_expires_at_utc='2025-01-02 00:00:00'",
    "UPDATE line_delivery_tasks SET error_code='line_reply_outcome_uncertain'",
    "UPDATE line_delivery_attempt_events SET error_code='line_reply_outcome_uncertain'",
    "UPDATE line_delivery_attempt_events SET completed_at_utc='2026-11-18 00:00:00'",
])
def test_candidate_sql_excludes_unconfirmed_or_inconsistent_terminal_details(connection,change):
    seed(connection)
    connection.db.execute(change);connection.db.commit()
    assert LineDeliveryRetentionApplication(lambda:Unit(connection),lambda:NOW,'synthetic-worker').run_once()==0
    assert connection.db.execute('SELECT COUNT(*) FROM line_command_receipts').fetchone()[0]==0
    assert connection.db.execute('SELECT COUNT(*) FROM line_delivery_attempt_events').fetchone()[0]==1
