"""Rebuild local union_db schema and import the fixed v3 fixture."""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
import pymysql
from infrastructure.mysql.mysql_adapter import DB_CONFIG
from scripts.init_db import DB_CONFIG as SERVER_CONFIG,load_schema_parts
from scripts.import_db_snapshot_fixture_v2 import DEFAULT_OUTPUT,load_fixture_bundle,import_fixture
ROOT=Path(__file__).resolve().parents[1];SCHEMA=ROOT/"db/schema.sql";PARTS=ROOT/"db/schema_parts"
class FakeDatabaseResetError(RuntimeError):pass
def validate_target(config=DB_CONFIG,environment=None):
    env=environment if environment is not None else os.environ
    if str(config.get("host","")).lower() not in {"localhost","127.0.0.1","::1"}:raise FakeDatabaseResetError("local MySQL only")
    if config.get("database")!="union_db":raise FakeDatabaseResetError("database must be union_db")
    if any("prod" in str(env.get(k,"")).lower() for k in ("APP_ENV","ENV","FLASK_ENV")):raise FakeDatabaseResetError("production environment refused")
def split_sql(text):
    out=[];buf=[];quote=None;escape=False;comment=False;i=0
    while i<len(text):
        ch=text[i];n=text[i+1] if i+1<len(text) else ""
        if comment:
            if ch in "\r\n":comment=False;buf.append(ch)
        elif quote:
            buf.append(ch)
            if escape:escape=False
            elif ch=="\\":escape=True
            elif ch==quote:quote=None
        elif ch=="-" and n=="-":comment=True;i+=1
        elif ch in "'\"`":quote=ch;buf.append(ch)
        elif ch==";":
            s="".join(buf).strip()
            if s:out.append(s)
            buf=[]
        else:buf.append(ch)
        i+=1
    s="".join(buf).strip()
    if s:out.append(s)
    return out
def rebuild_schema(connection_factory=pymysql.connect):
    statements=split_sql(SCHEMA.read_text(encoding="utf-8"));conn=connection_factory(**SERVER_CONFIG)
    try:
        with conn.cursor() as c:
            c.execute("SET NAMES utf8mb4")
            for s in statements:c.execute(s)
            parts=load_schema_parts(c,PARTS)
        conn.commit();return {"schema_statements":len(statements),"schema_parts":parts}
    except Exception as e:conn.rollback();raise FakeDatabaseResetError("schema reset failed; DROP may have taken effect") from e
    finally:conn.close()
def reset(apply=False,confirm_database=None,fixture=DEFAULT_OUTPUT):
    validate_target();_,checksum=load_fixture_bundle(fixture)
    preview={"target":{"host":DB_CONFIG["host"],"port":DB_CONFIG["port"],"database":"union_db"},"fixture_directory":str(fixture),"snapshot_checksum":checksum}
    if not apply:return {"status":"preview",**preview}
    if confirm_database!="union_db":raise FakeDatabaseResetError("apply requires --confirm-database union_db")
    schema=rebuild_schema();result=import_fixture(fixture,True)
    if result["status"]!="committed" or result["validation"]["status"]!="pass":raise FakeDatabaseResetError("import validation failed")
    return {"status":"completed",**preview,"schema_report":schema,"import_report":result}
def main():
    p=argparse.ArgumentParser();p.add_argument("--apply",action="store_true");p.add_argument("--confirm-database");p.add_argument("--fixture",type=Path,default=DEFAULT_OUTPUT);a=p.parse_args()
    print(json.dumps(reset(a.apply,a.confirm_database,a.fixture),ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
