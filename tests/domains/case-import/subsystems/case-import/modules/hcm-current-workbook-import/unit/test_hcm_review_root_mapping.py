"""Root mappings retained for current HCM review queries and historical evidence."""

import pytest

from domains.case_import.hcm_resubmission import hcm_field_targets


@pytest.mark.parametrize(
    ("field_path", "targets"),
    [
        ("服務時間", ("orders.service_hours_per_day", "orders.service_start_time", "orders.service_end_time", "orders.service_end_day_offset")),
        ("預計服務日期", ("orders.start_date", "orders.end_date")),
        ("希望服務天數", ("orders.service_days", "orders.end_date")),
        ("服務方式", ("clients.service_type",)),
    ],
)
def test_review_field_maps_to_its_authoritative_roots(field_path, targets):
    assert hcm_field_targets(field_path) == targets


def test_unknown_field_cannot_invent_an_authoritative_root():
    with pytest.raises(ValueError, match="field_not_owned"):
        hcm_field_targets("身分資格")
