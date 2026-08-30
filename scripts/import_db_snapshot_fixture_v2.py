"""Checksum-verified insert-only importer for fixture v3."""
from __future__ import annotations
import argparse, hashlib, json, re
import os
from datetime import date,datetime
from decimal import Decimal
from pathlib import Path
from infrastructure.mysql.mysql_adapter import DB_CONFIG,get_connection
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

def _require_target_database(target: str) -> None:
    configured = str(DB_CONFIG.get("database") or "")
    if not target or target != configured:
        raise ValueError("target database must exactly match configured DB_DATABASE")
    if not re.fullmatch(r"lu_test_[a-z0-9_]+", target):
        raise ValueError("target database must be an explicitly named lu_test_* database")
    if os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}:
        raise ValueError("production environment is not permitted for fixture import")


def _check_connected_identity(target: str) -> None:
    if not os.getenv("DB_HOST", "").strip():
        raise RuntimeError("DB_HOST must be configured explicitly")
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server")
            identity = cursor.fetchone()
        if not identity or identity.get("database_name") != target:
            raise RuntimeError("connected database does not match --target-database")
        if not str(identity.get("server") or "").strip():
            raise RuntimeError("connected MySQL server identity is unavailable")
    finally:
        conn.close()


def _validate_backup(path_value: str | None, target: str) -> dict[str, object]:
    if not path_value:
        raise ValueError("--apply requires --backup-receipt")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("backup receipt does not exist or is empty")
    header = path.read_bytes()[:1_048_576]
    if not header.startswith((b"-- MySQL dump", b"-- MariaDB dump")):
        raise ValueError("backup receipt is not a MySQL dump")
    if f"Current Database: `{target}`".encode() not in header and f"USE `{target}`".encode() not in header:
        raise ValueError("backup receipt does not identify the target database")
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "target_database": target}


def _read_plan(path_value: str | None, target: str, checksum: str) -> dict[str, object]:
    if not path_value:
        raise ValueError("--apply requires --plan-receipt from a prior --dry-run")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValueError("dry-run plan receipt does not exist")
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("dry-run plan receipt is not valid UTF-8 JSON") from exc
    if plan.get("mode") != "dry-run" or plan.get("target_database") != target:
        raise ValueError("dry-run plan receipt belongs to another target")
    if plan.get("snapshot_checksum") != checksum:
        raise ValueError("fixture snapshot checksum drift detected")
    return plan


def _write_receipt(path_value: Path | None, payload: dict[str, object]) -> None:
    if path_value is None:
        return
    path_value = path_value.expanduser().resolve()
    path_value.parent.mkdir(parents=True, exist_ok=True)
    path_value.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fixture", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--target-database", required=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--confirm-apply")
    p.add_argument("--plan-receipt", type=Path)
    p.add_argument("--backup-receipt", type=Path)
    p.add_argument("--receipt-path", type=Path)
    a = p.parse_args()
    if a.apply and a.dry_run:
        p.error("--apply and --dry-run are mutually exclusive")
    try:
        _require_target_database(a.target_database)
        tables, checksum = load_fixture_bundle(a.fixture)
        if a.apply:
            expected = f"APPLY {a.target_database}"
            if a.confirm_apply != expected:
                p.error(f"--confirm-apply must exactly equal {expected!r}")
            _read_plan(a.plan_receipt, a.target_database, checksum)
            backup = _validate_backup(a.backup_receipt, a.target_database)
            if not a.receipt_path:
                p.error("--apply requires --receipt-path for a terminal receipt")
            _check_connected_identity(a.target_database)
        else:
            backup = None
    except (ValueError, RuntimeError) as exc:
        p.error(str(exc))
    result = import_fixture(a.fixture, a.apply)
    result["mode"] = "apply" if a.apply else "dry-run"
    if backup is not None:
        result["backup_receipt"] = backup
        result["receipt_status"] = "committed"
    _write_receipt(a.receipt_path, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
if __name__=="__main__":raise SystemExit(main())
