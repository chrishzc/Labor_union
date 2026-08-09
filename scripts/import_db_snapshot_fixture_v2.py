"""Checksum-verified insert-only importer for fixture v3."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import date,datetime
from decimal import Decimal
from pathlib import Path
from infrastructure.mysql.mysql_adapter import get_connection
from scripts.db_snapshot_fixture_v2_serializer import SerializedTable,build_manifest
from scripts.db_snapshot_fixture_v2_validator import validate_snapshot_fixture_v2
from scripts.export_db_snapshot_fixture_v2 import FIXTURE_NAME,FIXTURE_VERSION,SCHEMA_VERSION,DEFAULT_OUTPUT,TABLE_NAMES,JSON_COLUMNS,KEYS

class SnapshotImportError(RuntimeError):pass
def decode(v):
    t=v.get("type"); x=v.get("value")
    if t=="null":return None
    if t=="boolean":return bool(x)
    if t=="integer":return int(x)
    if t=="decimal":return Decimal(x)
    if t=="date":return date.fromisoformat(x)
    if t=="datetime":return datetime.fromisoformat(x)
    if t=="string":return x
    if t=="list":return [decode(i) for i in x]
    if t=="object":return {k:decode(i) for k,i in x.items()}
    raise SnapshotImportError("malformed tagged value")
def _row(encoded):
    row={k:decode(v) for k,v in encoded.items() if not k.startswith("__")}
    source=encoded.get("__source_id")
    if source is not None:row["id"]=decode(source)
    return row
def load_fixture_bundle(directory=DEFAULT_OUTPUT):
    directory=Path(directory).resolve()
    try: raw=(directory/"manifest.json").read_bytes(); manifest=json.loads(raw)
    except Exception as e:raise SnapshotImportError("fixture manifest is missing or invalid") from e
    if manifest.get("fixture_name")!=FIXTURE_NAME or manifest.get("fixture_version")!=FIXTURE_VERSION or manifest.get("schema_version")!=SCHEMA_VERSION:raise SnapshotImportError("manifest contract mismatch")
    if [e["table_name"] for e in manifest["tables"]]!=list(TABLE_NAMES):raise SnapshotImportError("table allowlist/order mismatch")
    tables={}; serialized=[]
    for e in manifest["tables"]:
        p=directory/e["relative_path"]; data=p.read_bytes()
        if hashlib.sha256(data).hexdigest()!=e["file_sha256"]:raise SnapshotImportError(f"{e['table_name']} checksum mismatch")
        lines=data.splitlines()
        if len(lines)!=e["row_count"]:raise SnapshotImportError("row count mismatch")
        encoded=[json.loads(x) for x in lines]; tables[e["table_name"]]=[_row(x) for x in encoded]
        serialized.append(SerializedTable(e["table_name"],e["relative_path"],len(lines),data,e["file_sha256"]))
    rebuilt=build_manifest(FIXTURE_NAME,FIXTURE_VERSION,SCHEMA_VERSION,serialized)
    if rebuilt.manifest_bytes!=raw:raise SnapshotImportError("snapshot checksum mismatch")
    validate_snapshot_fixture_v2(tables);return tables,rebuilt.snapshot_checksum
def _dbvalue(table,col,v):
    return json.dumps(v,ensure_ascii=False,separators=(",",":"),sort_keys=True) if col in JSON_COLUMNS.get(table,()) and v is not None else v
def import_fixture(directory=DEFAULT_OUTPUT,apply=False,connection_factory=get_connection):
    tables,checksum=load_fixture_bundle(directory);conn=connection_factory();committed=False;counts={}
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE");cur.execute("START TRANSACTION")
            for table in TABLE_NAMES:
                counts[table]={"inserted":0,"would_insert":0,"skipped_identical":0}
                for row in tables[table]:
                    columns=tuple(row); key_columns=("id",) if "id" in row else KEYS[table]
                    where=" AND ".join(f"`{key}` <=> %s" for key in key_columns)
                    cur.execute(f"SELECT 1 FROM `{table}` WHERE {where}",tuple(row[key] for key in key_columns))
                    if cur.fetchone() is not None:counts[table]["skipped_identical"]+=1;continue
                    if apply:
                        names=", ".join(f"`{c}`" for c in columns);marks=", ".join(["%s"]*len(columns))
                        cur.execute(f"INSERT INTO `{table}` ({names}) VALUES ({marks})",tuple(_dbvalue(table,c,row[c]) for c in columns))
                        counts[table]["inserted"]+=1
                    else:counts[table]["would_insert"]+=1
            if apply:
                # Validate exact landed facts inside the transaction.
                landed={}
                for table in TABLE_NAMES:
                    cur.execute(f"SELECT * FROM `{table}`"); rows=[dict(r) for r in cur.fetchall()]
                    for r in rows:
                        for c in JSON_COLUMNS.get(table,()):
                            if isinstance(r.get(c),str):r[c]=json.loads(r[c])
                    landed[table]=rows
                validation=validate_snapshot_fixture_v2(landed);conn.commit();committed=True
            else:validation={"status":"fixture_validated"}
        return {"status":"committed" if apply else "dry_run","fixture_version":FIXTURE_VERSION,"snapshot_checksum":checksum,"table_counts":counts,"validation":validation}
    finally:
        if not committed:conn.rollback()
        conn.close()
def main():
    p=argparse.ArgumentParser();p.add_argument("--fixture",type=Path,default=DEFAULT_OUTPUT);p.add_argument("--apply",action="store_true");a=p.parse_args()
    print(json.dumps(import_fixture(a.fixture,a.apply),ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
