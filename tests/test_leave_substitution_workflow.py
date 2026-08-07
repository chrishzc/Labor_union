from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from domains.scheduling.leave_substitution import (
    LeaveResolutionType,
    LeaveSubstitutionBatchIntent,
    LeaveSubstitutionItem,
)
from subsystems.scheduling.leave_substitution_workflow import (
    _canonical_staff_ids,
    leave_request_fingerprint,
)


def _intent() -> LeaveSubstitutionBatchIntent:
    return LeaveSubstitutionBatchIntent(
        1,
        (LeaveSubstitutionItem(10, date(2026, 8, 3), LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS),),
    )


def test_leave_substitution_workflow_is_readable_source_without_bridge():
    source = Path("subsystems/scheduling/leave_substitution_workflow.py").read_text(encoding="utf-8")
    assert "load_preserved_module" not in source
    assert "_bytecode_bridge" not in source


def test_leave_request_fingerprint_is_deterministic_for_typed_batch():
    assert leave_request_fingerprint(_intent()) == leave_request_fingerprint(_intent())


def test_preflight_staff_ids_must_be_already_canonical():
    assert _canonical_staff_ids((1, 2)) == (1, 2)
    with pytest.raises(ValueError, match="canonical"):
        _canonical_staff_ids((2, 1))
