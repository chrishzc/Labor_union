from scripts.import_db_snapshot_fixture_v2 import load_fixture_bundle,import_fixture
def test_bundle_and_database_dry_run_are_identical():
    tables,checksum=load_fixture_bundle()
    assert len(tables["clients"])==50 and len(tables["holidays"])==15
    report=import_fixture()
    assert report["status"]=="dry_run" and report["snapshot_checksum"]==checksum
    assert all(not x["would_insert"] for x in report["table_counts"].values())
