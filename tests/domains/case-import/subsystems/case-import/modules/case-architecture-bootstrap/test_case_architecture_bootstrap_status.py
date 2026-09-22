from datetime import date, datetime

from api.routes.case_architecture_bootstrap import _http_error
from api.schemas.errors import GlobalTypedErrorView
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from subsystems.bootstrap.case_architecture_status import (
    CaseArchitectureBootstrapStatusService,
)


class _Cursor:
    def __init__(self, row):
        self._row = row
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _parameters):
        self.sql = sql

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, row):
        self.cursor_instance = _Cursor(row)

    def cursor(self):
        return self.cursor_instance


def _bootstrap_required_row(**overrides):
    row = {
        "case_no": "CASE-HISTORICAL",
        "start_date": date(2026, 9, 15),
        "service_days": 0,
        "service_start_time": None,
        "service_end_time": None,
        "service_end_day_offset": None,
        "identity_status": "一般市民",
        "client_created_at": datetime(2026, 9, 1),
        "client_finance_case": None,
        "client_terms_case": None,
        "payroll_account_case": None,
        "payroll_policy_case": None,
        "bootstrap_event_case": None,
        "scheduling_case": "CASE-HISTORICAL",
        "scheduling_version": 1,
        "scheduling_generation": 1,
    }
    row.update(overrides)
    return row


def test_status_requires_service_days_before_offering_bootstrap_preview():
    connection = _Connection(_bootstrap_required_row())

    status = CaseArchitectureBootstrapStatusService(connection).query(
        "CASE-HISTORICAL"
    )

    assert "o.service_days" in connection.cursor_instance.sql
    assert status.recommendation is not None
    assert status.domain_blockers == ("missing_service_days",)


def test_case_bootstrap_http_error_keeps_typed_blocker_contract():
    error = TypedError(
        ErrorCategory.DOMAIN_BLOCKED,
        "invalid_case_architecture_root_facts",
        "正式訂單條件尚未完整。",
        CorrelationId("case-bootstrap-test"),
        domain_blockers=("invalid_case_architecture_root_facts",),
    )

    exception = _http_error(409, error)
    parsed = GlobalTypedErrorView.model_validate(exception.detail["error"])

    assert parsed.code == "invalid_case_architecture_root_facts"
    assert parsed.field_errors == []
    assert parsed.domain_blockers == ["invalid_case_architecture_root_facts"]
