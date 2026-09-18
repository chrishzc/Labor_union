"""Focused owner-flow regressions for #307 using fetched production definitions.

Methods are compiled from repository source. SQLite only translates the MySQL
syntax used by those methods; provider, credentials, production DB and browser
LIFF are not touched.
"""
from __future__ import annotations

import ast, hashlib, json, re, sqlite3
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[6]
P = {
    "app": ROOT / "subsystems/line/feedback_application.py",
    "feedback": ROOT / "infrastructure/mysql/line_feedback_repository.py",
    "notification": ROOT / "infrastructure/mysql/line_notification_repository.py",
    "customer": ROOT / "infrastructure/mysql/customer_service_repository.py",
    "knowledge": ROOT / "infrastructure/mysql/knowledge_retrieval_repository.py",
    "uow": ROOT / "infrastructure/mysql/knowledge_retrieval_unit_of_work.py",
    "route": ROOT / "api/routes/line_feedback.py",
}


class Struct:
    fields = ()
    def __init__(self, *args, **kwargs):
        values = dict(zip(self.fields, args)); values.update(kwargs)
        for name in self.fields: setattr(self, name, values.get(name))
    def __eq__(self, other):
        return type(self) is type(other) and all(getattr(self, name) == getattr(other, name) for name in self.fields)

class PreviewFingerprint(Struct): fields = ("value",)
class IdempotencyKey(Struct): fields = ("value",)
class CorrelationId(Struct): fields = ("value",)
class IdempotencyReceipt(Struct): fields = ("key", "payload_fingerprint", "result_reference")
class KnowledgeAnswerFeedbackContext(Struct): fields = ("source_response_id", "response_revision", "rule_revision")
class FeedbackRoot(Struct): fields = ("actor_id","source_response_id","outcome","binding_version","response_revision","catalog_revision","rule_revision","command_fingerprint","ticket_id","idempotency_key","correlation_id","occurred_at")
class FeedbackReceipt(Struct): fields = ("source_response_id","outcome","command_fingerprint","ticket_id","replayed")
class FeedbackReadback(Struct): fields = ("root", "receipt")
class FeedbackPreview(Struct): fields = ("source_response_id", "outcome", "command_fingerprint", "apply_ready")
class CustomerServiceTicket(Struct): fields = ("ticket_id","line_user_id","category","status","version","client_id","case_no","client_name","client_phone","assigned_admin_user_id","internal_note","created_at","updated_at")
class CreateCustomerServiceMessage(Struct): fields = ("line_user_id","category","message","event_key","client_id","case_no")
class NotificationSourceEvent(Struct): fields = ("identity","event_code","historical_silent","facts","source_domain","source_aggregate_type","source_aggregate_identity","source_version","occurred_at")

class FeedbackOutcome(StrEnum): RESOLVED="resolved"; UNRESOLVED="unresolved"
class CustomerServiceCategory(StrEnum): OTHER="other"
class CustomerServiceStatus(StrEnum): WAITING="waiting"; HANDLING="handling"; RESOLVED="resolved"
class FeedbackConflictError(RuntimeError): pass
class CustomerServiceTicketNotFoundError(LookupError): pass


class MySqlLineDeliveryTaskRepository:
    """Unused collaborator required by the production repository constructor."""

    def __init__(self, connection):
        self.connection = connection


def fp(payload):
    raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    return PreviewFingerprint(hashlib.sha256(raw).hexdigest())

class RecordLineFeedback(Struct):
    fields=("actor_id","source_response_id","outcome","binding_version","response_revision","catalog_revision","rule_revision","idempotency_key","correlation_id")
    @property
    def command_fingerprint(self):
        return fp({k:(getattr(self,k).value if k=="outcome" else getattr(self,k)) for k in self.fields[:7]})


def selected(path, class_name=None, methods=(), names=()):
    tree=ast.parse(path.read_text(encoding="utf-8"),filename=str(path)); out=[]
    if class_name:
        owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name)
        body=[n for n in owner.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in methods]
        assert {n.name for n in body}==set(methods)
        out.append(ast.ClassDef(name=class_name,bases=[],keywords=[],body=body,decorator_list=[],type_params=getattr(owner,"type_params",[])))
    for n in tree.body:
        targets=[]
        if isinstance(n,ast.Assign): targets=[t.id for t in n.targets if isinstance(t,ast.Name)]
        elif isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name): targets=[n.target.id]
        if getattr(n,"name",None) in names or any(t in names for t in targets): out.append(n)
    return out


def compile_nodes(path, nodes, ns):
    future=ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0)
    mod=ast.Module(body=[future,*nodes],type_ignores=[]); ast.fix_missing_locations(mod)
    exec(compile(mod,str(path),"exec"),ns); return ns


def owners():
    base=globals().copy()
    n=compile_nodes(P["notification"],selected(P["notification"],"MySqlLineNotificationRepository",("__init__","register_source_event"),("_SOURCE_EVENT_INSERT_SQL","_SOURCE_EVENT_EXISTING_SQL","_canonical_json","_json_object")),{"json":json,**base})
    f=compile_nodes(P["feedback"],selected(P["feedback"],"MySqlLineFeedbackRepository",("__init__","get","append"),("_FEEDBACK_DOMAIN","_FEEDBACK_SOURCE_CONTRACTS","_FEEDBACK_EVENT_CODES","_root_from_row","_aware_utc")),{"json":json,"MySqlLineNotificationRepository":n["MySqlLineNotificationRepository"],**base})
    c=compile_nodes(P["customer"],selected(P["customer"],"MySqlCustomerServiceRepository",("__init__","create_or_append","get","latest_client_case","_ticket_for_event","_active_ticket","_latest_ticket","_create_ticket","_append_event"),("_ticket","_TICKET_SELECT","_ACTIVE_TICKET_SQL","_LATEST_TICKET_SQL","_TICKET_INSERT_SQL","_EVENT_INSERT_SQL","_LATEST_CLIENT_CASE_SQL")),base.copy())
    a=compile_nodes(P["app"],selected(P["app"],"LineFeedbackApplication",("__init__","apply","_apply_in_unit_of_work"),("_receipt_reference","_readback")),base.copy())
    k=compile_nodes(P["knowledge"],selected(P["knowledge"],"MySqlKnowledgeRetrievalRepository",("__init__","feedback_context","list_answer_requests","_rows"),("_LIST_ANSWER_REQUESTS",)),base.copy())
    u=compile_nodes(P["uow"],selected(P["uow"],"KnowledgeRetrievalMySqlUnitOfWork",("answer_receipt_catalog_revision",)),base.copy())
    r=compile_nodes(P["route"],selected(P["route"],names=("_KNOWLEDGE_RESPONSE_PREFIX","_feedback_command","_knowledge_feedback_source")),{"HTTPException":HTTPException,**base})
    return dict(App=a["LineFeedbackApplication"],Feedback=f["MySqlLineFeedbackRepository"],Customer=c["MySqlCustomerServiceRepository"],Knowledge=k["MySqlKnowledgeRetrievalRepository"],KUow=u["KnowledgeRetrievalMySqlUnitOfWork"],Route=r)


J=re.compile(r"JSON_UNQUOTE\(JSON_EXTRACT\(([^,]+),\s*'([^']+)'\)\)",re.I)
class Cursor:
    def __init__(self,c): self.c=c; self.raw=c.db.cursor(); self._rowcount=-1; self._lastrowid=None
    def __enter__(self): return self
    def __exit__(self,*_): self.raw.close()
    def execute(self,sql,values=()):
        sql=sql.replace("%s","?").replace(" FOR UPDATE","").replace("INSERT IGNORE INTO","INSERT OR IGNORE INTO")
        sql=sql.replace("IF(status='resolved','handling',status)","CASE WHEN status='resolved' THEN 'handling' ELSE status END").replace("CAST(b.subject_reference AS UNSIGNED)","CAST(b.subject_reference AS INTEGER)")
        sql=J.sub(r"json_extract(\1,'\2')",sql); self.raw.execute(sql,values); self._rowcount=self.raw.rowcount; self._lastrowid=self.raw.lastrowid; return self
    @property
    def rowcount(self): return self._rowcount
    @property
    def lastrowid(self): return self._lastrowid
    def cv(self,row):
        if row is None:return None
        d=dict(row)
        if isinstance(d.get("occurred_at_utc"),str): d["occurred_at_utc"]=datetime.fromisoformat(d["occurred_at_utc"])
        return d
    def fetchone(self): return self.cv(self.raw.fetchone())
    def fetchall(self): return tuple(self.cv(r) for r in self.raw.fetchall())

class DB:
    def __init__(self):
        self.db=sqlite3.connect(":memory:"); self.db.row_factory=sqlite3.Row; self.db.create_function("CONCAT",-1,lambda *x:"".join("" if v is None else str(v) for v in x)); self.tx=False
        self.db.executescript("""
CREATE TABLE clients(id INTEGER PRIMARY KEY,name TEXT,phone TEXT);
CREATE TABLE orders(id INTEGER PRIMARY KEY,client_id INTEGER,case_no TEXT,status TEXT,start_date TEXT,end_date TEXT,created_at TEXT);
CREATE TABLE line_identity_role_bindings(line_user_id TEXT,subject_reference TEXT,subject_type TEXT,binding_status TEXT);
CREATE TABLE customer_service_tickets(id INTEGER PRIMARY KEY AUTOINCREMENT,line_user_id TEXT,client_id INTEGER,case_no TEXT,category TEXT,status TEXT DEFAULT 'waiting',version INTEGER DEFAULT 1,assigned_to_admin_user_id INTEGER,internal_note TEXT,created_at_utc TEXT DEFAULT CURRENT_TIMESTAMP,updated_at_utc TEXT DEFAULT CURRENT_TIMESTAMP,resolved_at_utc TEXT);
CREATE TABLE customer_service_ticket_events(id INTEGER PRIMARY KEY AUTOINCREMENT,ticket_id INTEGER,event_key TEXT UNIQUE,event_type TEXT,message_text TEXT,actor_id TEXT,created_at_utc TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE line_notification_source_events(id INTEGER PRIMARY KEY AUTOINCREMENT,source_domain TEXT,event_code TEXT,source_event_identity TEXT,source_aggregate_type TEXT,source_aggregate_identity TEXT,source_version INTEGER,historical_silent INTEGER,facts_snapshot TEXT,occurred_at_utc TEXT,UNIQUE(source_domain,event_code,source_event_identity));
CREATE TABLE receipts(idempotency_key TEXT PRIMARY KEY,fingerprint TEXT,result_reference TEXT);
CREATE TABLE knowledge_answer_requests(id INTEGER PRIMARY KEY,question TEXT,requester_line_user_id TEXT,idempotency_key TEXT UNIQUE,correlation_id TEXT,request_status TEXT,created_at_utc TEXT DEFAULT CURRENT_TIMESTAMP,completed_at_utc TEXT);
CREATE TABLE knowledge_answer_receipts(id INTEGER PRIMARY KEY,answer_request_id INTEGER,answer_text TEXT,index_version INTEGER,authoritative INTEGER DEFAULT 0,line_delivery_task_id INTEGER,answered_at_utc TEXT);
CREATE TABLE knowledge_answer_sources(id INTEGER PRIMARY KEY AUTOINCREMENT,answer_receipt_id INTEGER,source_identity TEXT,source_version INTEGER,safe_excerpt TEXT,citation_order INTEGER);
CREATE TABLE knowledge_jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,answer_request_id INTEGER,last_error_code TEXT);
CREATE TABLE line_delivery_tasks(id INTEGER PRIMARY KEY,processing_status TEXT);
""")
    def cursor(self): return Cursor(self)
    def begin(self): self.db.execute("BEGIN"); self.tx=True
    def commit(self): self.db.commit(); self.tx=False
    def rollback(self): self.db.rollback(); self.tx=False

class Receipts:
    def __init__(self,db): self.db=db.db
    def get(self,key):
        r=self.db.execute("SELECT fingerprint,result_reference FROM receipts WHERE idempotency_key=?",(key.value,)).fetchone()
        return None if r is None else IdempotencyReceipt(key,PreviewFingerprint(r[0]),r[1])
    def append(self,r): self.db.execute("INSERT INTO receipts VALUES (?,?,?)",(r.key.value,r.payload_fingerprint.value,r.result_reference))

class LineUow:
    def __init__(self,db,o): self.db=db; self.feedback=o["Feedback"](db); self.customer_service=o["Customer"](db); self.receipts=Receipts(db); self.done=False
    def __enter__(self): self.db.begin(); return self
    def __exit__(self,e,*_):
        if e or not self.done:self.db.rollback()
    def commit(self): self.db.commit(); self.done=True

class KnowledgeUow:
    def __init__(self,db,o): self.knowledge=o["Knowledge"](db); self.k=o["KUow"](); self.k._connection=db
    def __enter__(self): return self
    def __exit__(self,*_): return False
    def answer_receipt_catalog_revision(self,i): return self.k.answer_receipt_catalog_revision(i)


def seed(db,req,receipt,question=None,actor="U-owner",index=9):
    db.db.execute("INSERT INTO knowledge_answer_requests(id,question,requester_line_user_id,idempotency_key,correlation_id,request_status,completed_at_utc) VALUES (?,?,?,?,?,'answered',CURRENT_TIMESTAMP)",(req,question or f"q-{req}",actor,f"k-{req}",f"c-{req}"))
    db.db.execute("INSERT INTO knowledge_answer_receipts(id,answer_request_id,answer_text,index_version,authoritative,line_delivery_task_id) VALUES (?,?,?,?,0,NULL)",(receipt,req,f"a-{req}",index))
    db.db.execute("INSERT INTO knowledge_answer_sources(answer_receipt_id,source_identity,source_version,safe_excerpt,citation_order) VALUES (?,?,?,?,1)",(receipt,f"line-common-qa:q-{req}",4,"excerpt")); db.db.commit()

def command(receipt,outcome,index=9):
    return RecordLineFeedback(actor_id="U-owner",source_response_id=f"knowledge-answer-receipt:{receipt}",outcome=outcome,binding_version=7,response_revision=1,catalog_revision=index,rule_revision=None,idempotency_key=IdempotencyKey(f"f-{receipt}"),correlation_id=CorrelationId(f"fc-{receipt}"))

@pytest.fixture
def env():
    o=owners(); db=DB(); app=o["App"](lambda:LineUow(db,o),lambda:datetime(2026,9,16,12,tzinfo=timezone.utc))
    try: yield o,db,app
    finally: db.db.close()


def test_unresolved_links_one_ticket_and_exact_replay(env):
    o,db,app=env; seed(db,1,42)
    k=o["Knowledge"](db); ctx=k.feedback_context(42,"U-owner")
    assert (ctx.source_response_id,ctx.response_revision,ctx.rule_revision)==("knowledge-answer-receipt:42",1,None)
    assert k.feedback_context(42,"U-other") is None
    ku=o["KUow"](); ku._connection=db; assert ku.answer_receipt_catalog_revision(42)==9
    first=app.apply(command(42,FeedbackOutcome.UNRESOLVED)); ticket=first.receipt.ticket_id
    assert ticket and not first.receipt.replayed
    event=db.db.execute("SELECT ticket_id,event_key FROM customer_service_ticket_events").fetchone()
    assert tuple(event)==(ticket,"line-feedback-ticket:knowledge-answer-receipt:42")
    replay=app.apply(command(42,FeedbackOutcome.UNRESOLVED))
    assert replay.receipt.replayed and replay.receipt.ticket_id==ticket
    assert db.db.execute("SELECT COUNT(*) FROM customer_service_tickets").fetchone()[0]==1
    assert db.db.execute("SELECT COUNT(*) FROM customer_service_ticket_events").fetchone()[0]==1
    assert db.db.execute("SELECT COUNT(*) FROM line_notification_source_events WHERE source_domain='line_feedback'").fetchone()[0]==1


def test_resolved_has_no_ticket_and_admin_distinguishes_five_states(env):
    o,db,app=env
    seed(db,10,110,"answered-no-feedback"); seed(db,11,111,"answered-resolved"); seed(db,12,112,"answered-unresolved")
    assert app.apply(command(111,FeedbackOutcome.RESOLVED)).receipt.ticket_id is None
    app.apply(command(112,FeedbackOutcome.UNRESOLVED))
    db.db.execute("INSERT INTO knowledge_answer_requests(id,question,requester_line_user_id,idempotency_key,correlation_id,request_status) VALUES (20,'unsupported','U-owner','k20','c20','unsupported')")
    db.db.execute("INSERT INTO knowledge_answer_requests(id,question,requester_line_user_id,idempotency_key,correlation_id,request_status) VALUES (21,'failed','U-owner','k21','c21','failed')"); db.db.commit()
    rows=o["Knowledge"](db).list_answer_requests(100,None)
    got={r["question"]:(r["request_status"],r["feedback_outcome"]) for r in rows}
    assert got=={"answered-no-feedback":("answered",None),"answered-resolved":("answered","resolved"),"answered-unresolved":("answered","unresolved"),"unsupported":("unsupported",None),"failed":("failed",None)}


def test_route_binds_actor_source_and_catalog_revision(env):
    o,db,_=env; seed(db,30,130,actor="U-owner",index=19); route=o["Route"]
    route["open_knowledge_retrieval_unit_of_work"]=lambda:KnowledgeUow(db,o)
    p=SimpleNamespace(source_response_id="knowledge-answer-receipt:130",outcome="resolved",response_revision=1,catalog_revision=19,rule_revision=None,idempotency_key="f130",correlation_id="fc130")
    got=route["_feedback_command"](p,"U-owner",7); assert (got.actor_id,got.catalog_revision)==("U-owner",19)
    with pytest.raises(HTTPException) as e: route["_feedback_command"](p,"U-other",7)
    assert (e.value.status_code,e.value.detail)==(404,"line_feedback_source_unavailable")
    for field,value in (("catalog_revision",20),("response_revision",2)):
        bad=SimpleNamespace(**{**p.__dict__,field:value})
        with pytest.raises(HTTPException) as e: route["_feedback_command"](bad,"U-owner",7)
        assert (e.value.status_code,e.value.detail)==(409,"line_feedback_source_version_conflict")
