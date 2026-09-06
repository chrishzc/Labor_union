"""Issue 218 adapter boundaries; mock-cursor tests, not MySQL/Chrome acceptance."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, Mock

import pytest

from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.order_intake_terms_bootstrap_repository import (
    MySqlOrderIntakeTermsBootstrapRepository,
)
from subsystems.orders.order_intake_client_name_repair import (
    OrderIntakeClientNameRepairApplication,
)
from subsystems.orders.order_intake_terms_bootstrap import (
    OrderIntakeTermsBootstrapApplication,
)


_CASE = "SYNTHETIC-ISSUE-218"
_START = date(2026, 9, 10)
_DAYS = 5
_VERSION = 7


@pytest.fixture
def connection():
    value = MagicMock()
    value.cursor.return_value.__enter__.return_value.rowcount = 1
    return value


def _case_row(**overrides):
    row = {
        "case_no": _CASE,
        "status": OrderLifecycleStatus.PENDING_COMPLETION.value,
        "lifecycle_version": _VERSION,
        "start_date": _START,
        "service_days": _DAYS,
        "actual_start_date": None,
        "client_name": "合成測試客戶",
        "service_data_locked": False,
        "client_finance_present": False,
        "payroll_present": False,
        "scheduling_case_no": None,
        "aggregate_version": None,
        "generation_counter": None,
        "effective_generation_id": None,
        "assignment_exists": False,
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("start_date", "service_days", "changed_fields"),
    [
        (None, _DAYS, ("start_date",)),
        (_START, None, ("service_days",)),
        (None, None, ("start_date", "service_days")),
        (None, 0, ("start_date", "service_days")),
    ],
    ids=["missing-start", "missing-days", "missing-both-terms", "legacy-zero-days"],
)
def test_terms_preview_uses_only_an_unlocked_owner_read(
    connection, start_date, service_days, changed_fields,
):
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = _case_row(
        start_date=start_date, service_days=service_days,
    )
    unit_of_work = Mock()
    application = OrderIntakeTermsBootstrapApplication(
        MySqlOrderIntakeTermsBootstrapRepository(connection), unit_of_work,
    )

    preview = application.preview(_CASE, _START, _DAYS)

    assert preview.before_start_date == start_date
    assert preview.before_service_days == service_days
    assert preview.after_start_date == _START
    assert preview.after_service_days == _DAYS
    assert preview.changed_fields == changed_fields
    assert preview.lifecycle_version == _VERSION
    assert preview.blockers == ()
    assert preview.apply_allowed is True
    cursor.execute.assert_called_once()
    sql, parameters = cursor.execute.call_args.args
    assert sql.startswith("SELECT ")
    assert "FOR UPDATE" not in sql
    assert parameters == (_CASE,)
    unit_of_work.assert_not_called()
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()


@pytest.mark.parametrize("stored_name", [None, "", "   "])
def test_name_preview_is_read_only_and_reports_normalized_missing_name(
    connection, stored_name,
):
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = _case_row(client_name=stored_name)
    unit_of_work = Mock()
    application = OrderIntakeClientNameRepairApplication(
        MySqlOrderIntakeTermsBootstrapRepository(connection), unit_of_work,
    )

    preview = application.preview(_CASE, "合成補件姓名")

    assert preview.before_client_name is None
    assert preview.after_client_name == "合成補件姓名"
    assert preview.lifecycle_version == _VERSION
    assert preview.blockers == ()
    assert preview.apply_allowed is True
    cursor.execute.assert_called_once()
    sql, parameters = cursor.execute.call_args.args
    assert sql.startswith("SELECT ")
    assert "FOR UPDATE" not in sql
    assert parameters == (_CASE,)
    unit_of_work.assert_not_called()
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()


@pytest.mark.parametrize(
    ("overrides", "missing_fields"),
    [
        ({"client_name": None}, ("client_name",)),
        ({"start_date": None}, ("start_date",)),
        ({"service_days": None}, ("service_days",)),
        ({"start_date": None, "service_days": None}, ("start_date", "service_days")),
        ({}, ()),
    ],
    ids=["missing-name", "missing-start", "missing-days", "missing-both-terms", "complete"],
)
def test_completion_preview_does_not_complete_or_write_the_order(
    connection, overrides, missing_fields,
):
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = _case_row(**overrides)
    unit_of_work = Mock()
    application = OrderIntakeTermsBootstrapApplication(
        MySqlOrderIntakeTermsBootstrapRepository(connection), unit_of_work,
    )

    preview = application.preview_completion(_CASE)

    assert preview.missing_fields == missing_fields
    assert preview.apply_allowed is (not missing_fields)
    assert preview.current_status is OrderLifecycleStatus.PENDING_COMPLETION
    assert preview.target_status is OrderLifecycleStatus.DISCUSSION
    assert preview.lifecycle_version == _VERSION
    cursor.execute.assert_called_once()
    sql, parameters = cursor.execute.call_args.args
    assert sql.startswith("SELECT ")
    assert "FOR UPDATE" not in sql
    assert parameters == (_CASE,)
    unit_of_work.assert_not_called()
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()


@pytest.mark.parametrize(
    ("fill_start", "fill_days", "assignments", "values"),
    [
        (True, False, "start_date=%s", (_START,)),
        (False, True, "service_days=%s", (_DAYS,)),
        (True, True, "start_date=%s,service_days=%s", (_START, _DAYS)),
    ],
    ids=["start-only", "days-only", "both-terms"],
)
def test_terms_writer_updates_only_selected_terms_and_version(
    connection, fill_start, fill_days, assignments, values,
):
    repository = MySqlOrderIntakeTermsBootstrapRepository(connection)

    resulting_version = repository.update_missing_terms(
        _CASE, _VERSION, _START, _DAYS,
        fill_start_date=fill_start, fill_service_days=fill_days,
    )

    # Exact write-set assertion includes absence of end_date, status and other roots.
    connection.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
        "UPDATE orders SET " + assignments
        + ",lifecycle_version=lifecycle_version+1 WHERE case_no=%s AND lifecycle_version=%s",
        values + (_CASE, _VERSION),
    )
    assert resulting_version == _VERSION + 1
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()


def test_terms_writer_with_no_missing_fields_issues_no_sql(connection):
    repository = MySqlOrderIntakeTermsBootstrapRepository(connection)

    with pytest.raises(RuntimeError, match="order_intake_terms_bootstrap_nothing_to_write"):
        repository.update_missing_terms(
            _CASE, _VERSION, _START, _DAYS,
            fill_start_date=False, fill_service_days=False,
        )

    connection.cursor.assert_not_called()
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()


def test_name_writer_only_fills_blank_client_name_without_writing_orders(connection):
    repository = MySqlOrderIntakeTermsBootstrapRepository(connection)

    repository.update_missing_client_name(_CASE, "合成補件姓名")

    connection.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
        "UPDATE clients SET name=%s WHERE case_no=%s "
        "AND (name IS NULL OR TRIM(name)='')",
        ("合成補件姓名", _CASE),
    )
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()


def test_completion_is_a_separate_versioned_status_write(connection):
    repository = MySqlOrderIntakeTermsBootstrapRepository(connection)

    resulting_version = repository.complete_intake(_CASE, _VERSION)

    connection.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
        "UPDATE orders SET status=%s,lifecycle_version=lifecycle_version+1 "
        "WHERE case_no=%s AND lifecycle_version=%s AND status=%s",
        (
            OrderLifecycleStatus.DISCUSSION.value, _CASE, _VERSION,
            OrderLifecycleStatus.PENDING_COMPLETION.value,
        ),
    )
    assert resulting_version == _VERSION + 1
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()
