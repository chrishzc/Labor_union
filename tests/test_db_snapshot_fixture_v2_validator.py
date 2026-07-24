from services.db_service import get_connection
from scripts.export_db_snapshot_fixture_v2 import read_consistent_snapshot
from scripts.db_snapshot_fixture_v2_validator import validate_snapshot_fixture_v2,SnapshotFixtureValidationError
def test_current_fixture_database_passes_full_validation():
    c=get_connection()
    try:
        tables,_=read_consistent_snapshot(c)
        assert validate_snapshot_fixture_v2(tables)["status"]=="pass"
    finally:c.rollback();c.close()
def test_wrong_end_date_is_rejected():
    c=get_connection()
    try:tables,_=read_consistent_snapshot(c)
    finally:c.rollback();c.close()
    tables["orders"][0]["end_date"]=tables["orders"][0]["start_date"]
    try:validate_snapshot_fixture_v2(tables);assert False
    except SnapshotFixtureValidationError:pass
