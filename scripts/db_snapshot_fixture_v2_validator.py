"""Fail-closed validation for the fixed 50-case v3 fixture."""
from __future__ import annotations
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from scripts.imports.import_client_hcm import _calculate_service_end_date

class SnapshotFixtureValidationError(ValueError): pass
def _fail(m): raise SnapshotFixtureValidationError(m)
def _date(v,label):
    if isinstance(v,datetime): return v.date()
    if isinstance(v,date): return v
    if isinstance(v,str):
        for fmt in ("%Y-%m-%d","%Y/%m/%d"):
            try: return datetime.strptime(v[:10],fmt).date()
            except ValueError: pass
    _fail(f"invalid {label}")
EXPECTED_HOLIDAYS_2026={
date(2026,1,1):"中華民國開國紀念日(元旦)",date(2026,2,17):"農曆除夕",date(2026,2,18):"春節初一",
date(2026,2,19):"春節初二",date(2026,2,20):"春節初三",date(2026,2,21):"春節初四",date(2026,2,22):"春節初五",
date(2026,2,27):"和平紀念日(補假)",date(2026,2,28):"和平紀念日",date(2026,4,3):"兒童節",
date(2026,4,4):"清明節/民族掃墓節",date(2026,6,19):"端午節",date(2026,9,25):"中秋節",
date(2026,10,9):"國慶日(補假)",date(2026,10,10):"國慶日"}

def validate_snapshot_fixture_v2(tables, reference_case_range=(115000001,115000050)):
    required=("clients","orders","staff","holidays","case_staff_assignments","staff_schedule","client_payments","client_payment_transactions",
    "staff_payments","staff_monthly_settlements","staff_monthly_settlement_details","staff_actual_transfers","staff_transfer_allocations",
    "finance_import_batches","finance_import_rows","finance_import_occurrences")
    for n in required:
        if n not in tables or not isinstance(tables[n],list): _fail(f"missing required table: {n}")
    expected={str(x) for x in range(reference_case_range[0],reference_case_range[1]+1)}
    def index(rows,key,name):
        out={}
        for r in rows:
            k=str(r.get(key))
            if k in out:_fail(f"{name} duplicate key")
            out[k]=r
        return out
    clients=index(tables["clients"],"case_no","clients"); orders=index(tables["orders"],"case_no","orders")
    if set(clients)!=expected or set(orders)!=expected:_fail("clients/orders must contain exactly 50 fixed cases")
    if len(tables["staff"])!=50:_fail("staff count must be 50")
    holidays={_date(r.get("holiday_date"),"holiday"):r for r in tables["holidays"]}
    if set(holidays)!=set(EXPECTED_HOLIDAYS_2026):_fail("holidays must contain exactly fixed 15 dates")
    for d,n in EXPECTED_HOLIDAYS_2026.items():
        if holidays[d].get("holiday_name")!=n or not bool(holidays[d].get("is_double_pay_default")):_fail(f"holiday {d} mismatch")
    for case,o in orders.items():
        c=clients[case]; start=_date(o.get("start_date"),"start"); client_start=_date(c.get("service_start_date"),"client start")
        if start!=client_start:_fail(f"orders {case} start_date does not match client")
        end=_calculate_service_end_date(start,int(o["service_days"]),c.get("service_type"),set(holidays))
        if _date(o.get("end_date"),"end")!=end:_fail(f"orders {case} end_date does not match service rules")
    staff_ids={r["id"] for r in tables["staff"]}; assignments={r["id"]:r for r in tables["case_staff_assignments"]}
    for r in assignments.values():
        if str(r["case_no"]) not in orders or r["staff_id"] not in staff_ids:_fail("assignment orphan")
    for r in tables["staff_schedule"]:
        a=assignments.get(r["assignment_id"])
        if not a or a["staff_id"]!=r["staff_id"] or a["case_no"]!=r["case_no"]:_fail("schedule ownership mismatch")
    payments={r["id"]:r for r in tables["client_payments"]}
    tx= tables["client_payment_transactions"]
    for r in tx:
        if r["client_payment_id"] not in payments or payments[r["client_payment_id"]]["case_no"]!=r["case_no"]:_fail("client transaction orphan")
    bycase={r["case_no"]:r for r in tables["client_payments"]}
    specs={"115000013":("first_payment",3,Decimal("1000")),"115000014":("second_payment",1,Decimal("3000"))}
    for case,(stage,count,amount) in specs.items():
        p=bycase[case]
        if Decimal(str(p[f"{stage}_receivable"]))!=2500 or Decimal(str(p[f"{stage}_received"]))!=3000:_fail(f"{case} overpayment summary")
        rows=[r for r in tx if r["case_no"]==case and r.get("stage")==stage and r.get("transaction_type")=="receipt" and r.get("transaction_status")=="succeeded"]
        if len(rows)!=count or any(Decimal(str(r["amount"]))!=amount for r in rows):_fail(f"{case} receipt transactions")
    if len(tables["finance_import_batches"])!=2 or len(tables["finance_import_rows"])!=1 or len(tables["finance_import_occurrences"])!=2:_fail("finance staging cardinality")
    if not any(str(r.get("case_no"))=="115000018" and bool(r.get("is_double_pay")) for r in tables["staff_schedule"]):_fail("115000018 double-pay")
    return {"status":"pass","case_coverage":{"first":min(expected),"last":max(expected),"count":50},"staff_count":50,
            "table_counts":{k:len(v) for k,v in sorted(tables.items())},
            "boundary_cases":["115000003","115000004","115000005","115000008","115000009","115000013","115000014","115000018"],
            "finance_staging":{"batches":2,"canonical_rows":1,"occurrences":2}}
