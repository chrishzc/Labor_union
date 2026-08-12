import pytest

from scripts.rebuild_legacy_ui_dataset_projections import (
    PROJECTION_TABLES,
    verify_preserved_root_projections,
)


def test_projection_rebuild_receipt_proves_all_non_root_projections_are_empty():
    receipt = verify_preserved_root_projections({table: 0 for table in PROJECTION_TABLES})

    assert receipt["projection_source"] == "preserved_roots_only"
    assert receipt["verified"] is True
    assert receipt["projection_counts_after_rebuild"] == {table: 0 for table in PROJECTION_TABLES}


def test_projection_rebuild_verifier_rejects_a_derived_row():
    counts = {table: 0 for table in PROJECTION_TABLES}
    counts["scheduling_effective_occupancy"] = 1

    with pytest.raises(RuntimeError, match="projection rebuild verification failed"):
        verify_preserved_root_projections(counts)
