from __future__ import annotations

from datetime import date

from subsystems.validation_dataset.staff_master_source import (
    StaffMasterSourceFact,
    _staff_values,
)


def test_staff_master_fixture_is_a_root_source_not_a_derived_assignment():
    fact = StaffMasterSourceFact(
        "測試月嫂一號",
        "T100000001",
        "0911000001",
        date(1988, 1, 15),
        "新竹市",
        1,
    )

    assert _staff_values(fact) == (
        "測試月嫂一號",
        "T100000001",
        "0911000001",
        date(1988, 1, 15),
        "新竹市",
        "active",
        1,
    )
