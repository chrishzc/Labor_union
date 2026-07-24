from scripts.export_db_snapshot_fixture_v2 import export_snapshot_fixture
def test_export_is_valid_and_idempotent(tmp_path):
    target=tmp_path/"v3"
    first=export_snapshot_fixture(target);second=export_snapshot_fixture(target)
    assert first["status"]=="published" and first["validation"]["status"]=="pass"
    assert second["status"]=="identical" and second["snapshot_checksum"]==first["snapshot_checksum"]
