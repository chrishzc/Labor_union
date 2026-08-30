"""Reconcile fixed fixture order dates to client lineage and service rules."""
from __future__ import annotations
import argparse
import json
import os
from datetime import date,datetime

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.mysql.mysql_adapter import DB_CONFIG,get_connection
from scripts.imports.import_client_hcm import _calculate_service_end_date,_parse_date
EXPECTED={str(x) for x in range(115000001,115000051)}
CLI_BLOCKED_REASON = (
    "fixture order-date reconciliation is not absorbed by a canonical owner; "
    "apply is disabled until the operator guard contract is complete"
)

def _require_target_database(target: str) -> None:
    configured = str(DB_CONFIG.get("database") or "").strip()
    if not target or target != configured:
        raise RuntimeError("target database must exactly match configured DB_DATABASE")
    if target == "union_db" or not target.startswith("lu_test_"):
        raise RuntimeError("target database must be an explicitly named lu_test_* database")
    if not os.getenv("DB_HOST", "").strip():
        raise RuntimeError("DB_HOST must be configured explicitly")
    if os.getenv("APP_ENV", "").strip().lower() in {"prod", "production"}:
        raise RuntimeError("production environment is not permitted for this operator CLI")

def _require_target_host(host: str) -> None:
    configured = os.getenv("DB_HOST", "").strip()
    if not configured or host.strip() != configured:
        raise RuntimeError("target host must exactly match configured DB_HOST")

def _check_connected_identity(connection, target: str, host: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server")
        identity = cursor.fetchone() or {}
    if identity.get("database_name") != target:
        raise RuntimeError("connected database does not match --target-database")
    _require_target_host(host)
    if not str(identity.get("server") or "").strip():
        raise RuntimeError("connected MySQL server identity is unavailable")

def _d(v):
    if isinstance(v,datetime):return v.date()
    return v
def reconcile(apply=False,connection_factory=get_connection,*,target_database=None,target_host=None):
    if apply:
        raise RuntimeError(CLI_BLOCKED_REASON)
    if target_database is None:
        raise RuntimeError("explicit target database is required")
    _require_target_database(target_database)
    _require_target_host(target_host or os.getenv("DB_HOST", ""))
    conn=connection_factory();committed=False
    try:
        _check_connected_identity(conn,target_database,target_host or os.getenv("DB_HOST", ""))
        with conn.cursor() as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            c.execute("SET TRANSACTION READ ONLY")
            c.execute("START TRANSACTION")
            c.execute("SELECT holiday_date FROM holidays");holidays={_d(r["holiday_date"]) for r in c.fetchall()}
            c.execute("""SELECT c.case_no,c.service_start_date,c.service_type,o.start_date,o.end_date,o.service_days,o.status
            FROM clients c JOIN orders o ON o.case_no=c.case_no ORDER BY c.case_no""");rows=c.fetchall()
            if {r["case_no"] for r in rows}!=EXPECTED or len(rows)!=50:raise RuntimeError("fixture must contain exactly 50 cases")
            changes=[]
            for r in rows:
                start=_parse_date(r["service_start_date"])
                if not start:raise RuntimeError(f"{r['case_no']} invalid service_start_date")
                end=_calculate_service_end_date(start,int(r["service_days"]),r["service_type"],holidays)
                if _d(r["start_date"])!=start or _d(r["end_date"])!=end:
                    changes.append({"case_no":r["case_no"],"before_start_date":str(r["start_date"]),"before_end_date":str(r["end_date"]),"expected_start_date":str(start),"expected_end_date":str(end)})
                    if apply:
                        c.execute("UPDATE orders SET start_date=%s,end_date=%s WHERE case_no=%s AND start_date <=> %s AND end_date <=> %s",
                        (start,end,r["case_no"],r["start_date"],r["end_date"]))
                        if c.rowcount!=1:raise RuntimeError("optimistic update conflict")
            if apply:conn.commit();committed=True
        return {"mode":"apply" if apply else "check","scanned":50,"unchanged":50-len(changes),"would_update":0 if apply else len(changes),"updated":len(changes) if apply else 0,"invalid":0,"conflicts":0,"changes":changes}
    finally:
        if not committed:conn.rollback()
        conn.close()
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run",action="store_true",help="Read-only fixture audit (the default).")
    mode.add_argument("--apply",action="store_true",help=argparse.SUPPRESS)
    mode.add_argument("--verify",action="store_true",help=argparse.SUPPRESS)
    mode.add_argument("--replay",action="store_true",help=argparse.SUPPRESS)
    p.add_argument("--target-database",required=True)
    p.add_argument("--target-host",required=True)
    p.add_argument("--plan-receipt")
    p.add_argument("--backup-receipt")
    p.add_argument("--receipt-path")
    p.add_argument("--confirm")
    a=p.parse_args(argv)
    try:
        if a.apply or a.verify or a.replay:
            raise RuntimeError(CLI_BLOCKED_REASON)
        _require_target_database(a.target_database)
        result=reconcile(
            False,target_database=a.target_database,target_host=a.target_host
        )
    except Exception as exc:
        requested_mode = "apply" if a.apply else "verify" if a.verify else "replay" if a.replay else "dry-run"
        print(json.dumps({"mode":requested_mode,"status":"blocked","error":str(exc)},ensure_ascii=False))
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
