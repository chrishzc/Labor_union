"""Regression contract for historical pairing evidence column ownership."""

from infrastructure.mysql.historical_precision_restart_repository import (
    _ASSIGNMENTS_SQL,
)
from pathlib import Path


def test_restart_reads_canonical_caregiver_ordinal_column() -> None:
    assert "evidence.caregiver_ordinal AS pairing_ordinal" in _ASSIGNMENTS_SQL
    assert "ORDER BY evidence.caregiver_ordinal" in _ASSIGNMENTS_SQL
    assert "evidence.pairing_ordinal" not in _ASSIGNMENTS_SQL
    assert "assignment.assignment_sequence" in _ASSIGNMENTS_SQL
    assert "assignment.sequence" not in _ASSIGNMENTS_SQL


def test_restart_emits_supported_orders_lifecycle_outbox_intent() -> None:
    repository_source = Path(
        "infrastructure/mysql/historical_precision_restart_repository.py"
    ).read_text(encoding="utf-8")

    assert "'lifecycle_projection_changed'" in repository_source
    assert "'historical_precision_restart_applied'" not in repository_source


def test_restart_revokes_current_service_roots_without_creating_new_dates_or_money() -> None:
    repository_source = Path(
        "infrastructure/mysql/historical_precision_restart_repository.py"
    ).read_text(encoding="utf-8")

    assert "_invalidate_confirmed_dates(cursor, domain.facts.case_no)" in repository_source
    assert "actual_start_date=NULL,actual_end_date=NULL" in repository_source
    assert "client_finance_writer" not in repository_source
    assert "staff_payables_writer" not in repository_source
