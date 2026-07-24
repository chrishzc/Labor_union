"""Reconcile fixed fixture order dates to client lineage and service rules."""
from __future__ import annotations
import argparse,json
from datetime import date,datetime
from services.db_service import get_connection
from scripts.imports.import_client_hcm import _calculate_service_end_date,_parse_date
EXPECTED={str(x) for x in range(115000001,115000051)}
def _d(v):
    if isinstance(v,datetime):return v.date()
    return v
def reconcile(apply=False,connection_factory=get_connection):
    conn=connection_factory();committed=False
    try:
        with conn.cursor() as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE");c.execute("START TRANSACTION")
            c.execute("SELECT holiday_date FROM holidays");holidays={_d(r["holiday_date"]) for r in c.fetchall()}
            c.execute("""SELECT c.case_no,c.service_start_date,c.service_type,o.start_date,o.end_date,o.service_days,o.status
            FROM clients c JOIN orders o ON o.case_no=c.case_no ORDER BY c.case_no FOR UPDATE""");rows=c.fetchall()
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
def main():
    p=argparse.ArgumentParser();p.add_argument("--apply",action="store_true");a=p.parse_args()
    print(json.dumps(reconcile(a.apply),ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
