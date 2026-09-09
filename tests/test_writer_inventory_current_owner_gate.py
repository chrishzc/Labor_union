import pytest

from scripts.check_production_writers import _require_resolved_retained_owners


def test_retained_writer_requires_resolved_owner() -> None:
    with pytest.raises(ValueError, match="unresolved owner decisions"):
        _require_resolved_retained_owners(
            [
                {
                    "identity": "example.py:preview:commit:COMMIT:-:deadbeef:1",
                    "owner": "owner_review_required",
                    "transaction_boundary": "exact Task 97 accepted unclassified commit boundary",
                    "final_disposition": "retain_canonical",
                }
            ]
        )


def test_resolved_owner_can_remain_restricted() -> None:
    _require_resolved_retained_owners(
        [
            {
                "identity": "example.py:worker:commit:COMMIT:-:feedface:1",
                "owner": "line_delivery",
                "transaction_boundary": "bounded worker transaction",
                "final_disposition": "retain_restricted",
            }
        ]
    )
