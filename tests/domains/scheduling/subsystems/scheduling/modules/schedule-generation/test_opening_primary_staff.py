"""The opening principal survives substitution and same-person generation changes."""
from datetime import date

import pytest

from domains.scheduling.assignment_plan import (
    OpeningAssignmentIdentity as Assignment, OpeningAssignmentLineage as Lineage,
    OpeningSubstitutionIdentity as Substitution, resolve_opening_primary_staff,
)

DAY = date(2026, 10, 30)


def test_before_service_replacement_changes_principal():
    assignments = (Assignment(1, 10, 1, DAY), Assignment(2, 20, 1, DAY))
    assert resolve_opening_primary_staff(2, assignments, (Lineage(1, 2),), ()) == 20


def test_first_day_substitute_keeps_original_principal_across_date_rebuild():
    assignments = (Assignment(1, 10, 1, DAY), Assignment(2, 20, 1, DAY), Assignment(3, 20, 1, DAY))
    assert resolve_opening_primary_staff(3, assignments, (Lineage(2, 3),), (Substitution(1, DAY, 2, DAY),)) == 10


def test_repeated_daily_substitutions_trace_exact_committed_origins():
    assignments = (Assignment(1, 10, 1, DAY), Assignment(2, 20, 1, DAY), Assignment(3, 30, 1, DAY))
    assert resolve_opening_primary_staff(3, assignments, (), (Substitution(1, DAY, 2, DAY), Substitution(2, DAY, 3, DAY))) == 10


def test_later_handover_does_not_take_opening_credit():
    assignments = (Assignment(1, 10, 1, DAY), Assignment(2, 20, 2, date(2026, 11, 1)))
    assert resolve_opening_primary_staff(1, assignments, (), ()) == 10


def test_unrelated_outcome_does_not_change_principal():
    assignments = (Assignment(1, 10, 1, DAY), Assignment(2, 20, 1, DAY))
    assert resolve_opening_primary_staff(2, assignments, (), (Substitution(1, DAY, 2, date(2026, 11, 1)),)) == 20


def test_missing_or_cyclic_lineage_never_guesses_a_principal():
    assignments = (Assignment(1, 10, 1, DAY), Assignment(2, 10, 1, DAY))
    with pytest.raises(ValueError, match="lineage_invalid"):
        resolve_opening_primary_staff(2, assignments, (Lineage(1, 2), Lineage(2, 1)), ())
    with pytest.raises(ValueError, match="lineage_incomplete"):
        resolve_opening_primary_staff(2, assignments, (Lineage(99, 2),), ())
