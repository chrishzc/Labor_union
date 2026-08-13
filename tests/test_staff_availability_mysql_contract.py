from pathlib import Path


def test_repository_and_schema_share_staff_availability_column_contract():
    schema = Path(
        "db/schema_parts/188_matching_preferences_and_staff_availability.sql"
    ).read_text(encoding="utf-8")
    repository = Path(
        "infrastructure/mysql/staff_availability_repository.py"
    ).read_text(encoding="utf-8")

    for column in (
        "event_key",
        "aggregate_version",
        "before_snapshot",
        "after_snapshot",
        "request_fingerprint",
        "preview_fingerprint",
        "result_snapshot",
        "correlation_id",
    ):
        assert column in schema
        assert column in repository

    assert "ENUM('created','pause_ended','cancelled')" in schema
    assert 'StaffAvailabilityAction.END_PAUSE: "pause_ended"' in repository
    assert "_canonical_json(_block_payload(before) or {})" in repository
