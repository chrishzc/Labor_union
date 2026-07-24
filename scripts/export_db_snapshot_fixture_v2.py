"""Read-only deterministic exporter for the fixed v3 fixture."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, tempfile
from datetime import timedelta
from pathlib import Path
from services.db_service import get_connection
from scripts.db_snapshot_fixture_v2_serializer import serialize_table, build_manifest
from scripts.db_snapshot_fixture_v2_validator import validate_snapshot_fixture_v2

FIXTURE_NAME="labor_union_db_snapshot"; FIXTURE_VERSION="v3"; SCHEMA_VERSION="db-snapshot-fixture-v2"
DEFAULT_OUTPUT=Path("fixtures/db_snapshot_v2/v3")
TABLE_NAMES=("clients","beclass_records","staff","staff_bank_accounts","staff_regions","staff_time_slots","staff_cooking_skills",
"staff_transportation","staff_holiday_availability","staff_weekly_rest","staff_baby_types","holidays","orders","matching_records",
"client_payments","client_payment_transactions","case_staff_assignments","staff_schedule","staff_payments","staff_payment_transactions",
"staff_monthly_settlements","staff_monthly_settlement_details","staff_actual_transfers","staff_transfer_allocations",
"finance_import_batches","finance_import_rows","finance_import_occurrences")
KEYS={"clients":("case_no",),"beclass_records":("query_no",),"staff":("identity_card",),"staff_bank_accounts":("staff_id","bank_code","branch_code","account_no"),
"staff_regions":("staff_id","region_name"),"staff_time_slots":("staff_id","slot_name"),"staff_cooking_skills":("staff_id","skill_name"),
"staff_transportation":("staff_id","vehicle_type"),"staff_holiday_availability":("staff_id","holiday_name"),"staff_weekly_rest":("staff_id","rest_type"),
"staff_baby_types":("staff_id","baby_type"),"holidays":("holiday_date",),"orders":("case_no",),"matching_records":("id",),
"client_payments":("case_no",),"client_payment_transactions":("id",),"case_staff_assignments":("case_no","assignment_sequence"),
"staff_schedule":("assignment_id","work_date"),"staff_payments":("assignment_id",),"staff_payment_transactions":("id",),
"staff_monthly_settlements":("staff_id","settlement_month","revision"),"staff_monthly_settlement_details":("id",),
"staff_actual_transfers":("id",),"staff_transfer_allocations":("id",),"finance_import_batches":("id",),
"finance_import_rows":("dedup_fingerprint",),"finance_import_occurrences":("id",)}
JSON_COLUMNS={"orders":{"custom_rest_dates"},"finance_import_rows":{"bank_references","warnings","raw_payload","matched_identity_ids"},"finance_import_occurrences":{"warnings"}}

def _normalize(table,rows):
    for r in rows:
        for c in JSON_COLUMNS.get(table,()):
            if isinstance(r.get(c),str): r[c]=json.loads(r[c])
        if table=="finance_import_rows" and isinstance(r.get("transaction_time"),timedelta):
            s=int(r["transaction_time"].total_seconds())
            if not 0<=s<86400: raise ValueError("transaction_time outside day")
            r["transaction_time"]=f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"

def read_consistent_snapshot(conn):
    tables={}; specs=[]
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"); cur.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
        for name in TABLE_NAMES:
            cur.execute(f"SELECT * FROM `{name}`")
            columns=tuple(x[0] for x in cur.description); rows=[dict(r) for r in cur.fetchall()]; _normalize(name,rows)
            spec={"table_name":name,"relative_path":f"tables/{name}.jsonl","columns":columns,"business_key":KEYS[name],"sort_key":KEYS[name],"source_id_column":"id" if "id" in columns else None}
            tables[name]=rows; specs.append(spec)
    return tables,specs

def publish(target,tables,manifest):
    target=target.resolve(); target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        old=json.loads((target/"manifest.json").read_text(encoding="utf-8"))
        if old.get("snapshot_checksum")==manifest.snapshot_checksum:return "identical"
        raise RuntimeError("fixture version exists with different checksum")
    temp=Path(tempfile.mkdtemp(prefix=f".{target.name}-",dir=target.parent))
    try:
        for t in tables:
            p=temp/t.relative_path; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(t.jsonl_bytes)
            if hashlib.sha256(p.read_bytes()).hexdigest()!=t.file_sha256:raise RuntimeError("write checksum mismatch")
        (temp/"manifest.json").write_bytes(manifest.manifest_bytes); os.replace(temp,target); return "published"
    finally:
        if temp.exists():shutil.rmtree(temp)

def export_snapshot_fixture(output=DEFAULT_OUTPUT,connection_factory=get_connection):
    conn=connection_factory()
    try:
        rows,specs=read_consistent_snapshot(conn); validation=validate_snapshot_fixture_v2(rows)
        serialized=[serialize_table(s,rows[s["table_name"]]) for s in specs]
        manifest=build_manifest(FIXTURE_NAME,FIXTURE_VERSION,SCHEMA_VERSION,serialized)
        status=publish(Path(output),serialized,manifest)
        return {"status":status,"fixture_version":FIXTURE_VERSION,"snapshot_checksum":manifest.snapshot_checksum,
        "table_counts":{t.table_name:t.row_count for t in serialized},"validation":validation}
    finally: conn.rollback(); conn.close()
def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,default=DEFAULT_OUTPUT);a=p.parse_args()
    print(json.dumps(export_snapshot_fixture(a.output),ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
