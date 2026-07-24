"""Deterministic tagged JSONL serialization for database fixture bundles."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

@dataclass(frozen=True)
class SerializedTable:
    table_name: str; relative_path: str; row_count: int; jsonl_bytes: bytes; file_sha256: str
@dataclass(frozen=True)
class SerializedManifest:
    manifest_bytes: bytes; snapshot_checksum: str

def _json(value): return json.dumps(value, ensure_ascii=False, separators=(",",":"), sort_keys=False).encode()
def encode_tagged_value(v):
    if v is None: return {"type":"null"}
    if isinstance(v,bool): return {"type":"boolean","value":v}
    if isinstance(v,int): return {"type":"integer","value":str(v)}
    if isinstance(v,Decimal): return {"type":"decimal","value":format(v,"f")}
    if isinstance(v,datetime): return {"type":"datetime","value":v.isoformat(timespec="seconds")}
    if isinstance(v,date): return {"type":"date","value":v.isoformat()}
    if isinstance(v,str): return {"type":"string","value":v}
    if isinstance(v,Mapping): return {"type":"object","value":{str(k):encode_tagged_value(v[k]) for k in sorted(v,key=str)}}
    if isinstance(v,(list,tuple)): return {"type":"list","value":[encode_tagged_value(x) for x in v]}
    raise TypeError(f"unsupported snapshot value type: {type(v).__name__}")

def serialize_table(spec, rows, table_file_metadata=None):
    meta=table_file_metadata or {}; name=str(meta.get("table_name") or spec["table_name"])
    path=str(meta.get("relative_path") or spec.get("relative_path") or f"tables/{name}.jsonl").replace("\\","/")
    if path.startswith("/") or ":" in path or ".." in PurePosixPath(path).parts: raise ValueError("relative_path must be relative")
    columns=tuple(spec["columns"]); business=tuple(spec["business_key"]); sort=tuple(spec.get("sort_key") or business); source=spec.get("source_id_column")
    prepared=[]; seen=set()
    for row in rows:
        missing=(set(columns)|set(business)|set(sort)) - set(row)
        if missing: raise ValueError(f"{name} row missing columns: {sorted(missing)}")
        key=[{"column":c,"value":encode_tagged_value(row[c])} for c in business]; kb=_json(key)
        if kb in seen: raise ValueError(f"{name} contains a duplicate business key")
        seen.add(kb)
        fields={c:encode_tagged_value(row[c]) for c in columns if c!=source}
        sha=hashlib.sha256(_json({"__row_key":key,"fields":fields})).hexdigest()
        output={"__row_key":key,"__row_sha256":sha,"__source_id":encode_tagged_value(row[source]) if source else None}; output.update(fields)
        token=_json([{"column":c,"value":encode_tagged_value(row[c])} for c in sort])
        prepared.append((token,output))
    prepared.sort(key=lambda x:x[0]); data=b"".join(_json(r)+b"\n" for _,r in prepared)
    return SerializedTable(name,path,len(rows),data,hashlib.sha256(data).hexdigest())

def build_manifest(fixture_name, fixture_version, schema_version, tables):
    names=[t.table_name for t in tables]; paths=[t.relative_path for t in tables]
    if len(names)!=len(set(names)) or len(paths)!=len(set(paths)): raise ValueError("duplicate manifest table/path")
    entries=[{"table_name":t.table_name,"relative_path":t.relative_path,"row_count":t.row_count,"file_sha256":t.file_sha256} for t in tables]
    base={"fixture_name":fixture_name,"fixture_version":fixture_version,"schema_version":schema_version,"tables":entries}
    checksum=hashlib.sha256(_json(base)).hexdigest(); base["snapshot_checksum"]=checksum
    return SerializedManifest(_json(base)+b"\n",checksum)
