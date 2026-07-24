from datetime import date
from decimal import Decimal
import pytest
from scripts.db_snapshot_fixture_v2_serializer import encode_tagged_value,serialize_table,build_manifest
SPEC={"table_name":"x","columns":("id","code","amount","day"),"business_key":("code",),"sort_key":("code",),"source_id_column":"id"}
def test_tagged_types():
    assert encode_tagged_value(Decimal("1.20"))["value"]=="1.20"
    assert encode_tagged_value(date(2026,1,1))["type"]=="date"
def test_deterministic_and_manifest():
    a=serialize_table(SPEC,[{"id":2,"code":"B","amount":Decimal("2"),"day":None},{"id":1,"code":"A","amount":Decimal("1"),"day":date(2026,1,1)}])
    b=serialize_table(SPEC,[{"id":1,"code":"A","amount":Decimal("1"),"day":date(2026,1,1)},{"id":2,"code":"B","amount":Decimal("2"),"day":None}])
    assert a.jsonl_bytes==b.jsonl_bytes
    assert build_manifest("f","v3","s",[a]).snapshot_checksum
def test_duplicate_rejected():
    with pytest.raises(ValueError):serialize_table(SPEC,[{"id":1,"code":"A","amount":1,"day":None},{"id":2,"code":"A","amount":2,"day":None}])
