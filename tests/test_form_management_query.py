"""Contracts for the Form Management read-only query boundary."""

from datetime import date

import pytest

from subsystems.orders.form_management_query import (
    FormManagementCaseContext,
    FormManagementQueryContractError,
    FormManagementQueryService,
    FormManagementStatistics,
)


class _Repository:
    def fetch_case_context(self, case_no):
        assert case_no == "CASE-001"
        return {
            "case_no": case_no,
            "city": "Taipei",
            "delivery_type": "hospital",
            "identity_status": "citizen",
            "residence_type": "home",
            "service_time": "09:00-17:00",
            "service_type": "postpartum",
        }

    def fetch_statistics(self):
        return {
            "global_active_orders_count": 2,
            "global_active_staff_count": 1,
            "global_govt_claim_count": 1,
            "global_subsidy_orders_count": 1,
            "global_total_receivable_sum": 2400,
        }


def test_form_management_query_returns_only_the_existing_template_facts():
    service = FormManagementQueryService(_Repository())

    assert service.statistics() == FormManagementStatistics(2, 1, 1, 2400, 1)
    assert service.case_context("CASE-001") == FormManagementCaseContext(
        "CASE-001", "09:00-17:00", "postpartum", "hospital", "home", "Taipei", "citizen"
    )


@pytest.mark.parametrize(
    "statistics",
    (
        {"global_active_orders_count": 1},
        {
            "global_active_orders_count": -1,
            "global_active_staff_count": 0,
            "global_govt_claim_count": 0,
            "global_subsidy_orders_count": 0,
            "global_total_receivable_sum": 0,
        },
    ),
)
def test_form_management_statistics_rejects_incomplete_or_negative_projection(statistics):
    class _InvalidRepository(_Repository):
        def fetch_statistics(self):
            return statistics

    with pytest.raises(FormManagementQueryContractError):
        FormManagementQueryService(_InvalidRepository()).statistics()


def test_form_management_context_rejects_noncanonical_or_extra_projection_fields():
    class _InvalidRepository(_Repository):
        def fetch_case_context(self, case_no):
            row = super().fetch_case_context(case_no)
            row["unexpected"] = date(2026, 8, 8)
            return row

    with pytest.raises(FormManagementQueryContractError):
        FormManagementQueryService(_InvalidRepository()).case_context("CASE-001")


def test_orders_router_exposes_typed_form_management_statistics_and_context():
    from api.routes.orders import (
        get_form_management_case_context,
        get_form_management_statistics,
    )
    from subsystems.access.authentication_session import AdminPrincipal

    class _Application:
        def statistics(self):
            return FormManagementStatistics(2, 1, 1, 2400, 1)

        def case_context(self, case_no):
            return FormManagementCaseContext(
                case_no, "09:00-17:00", "postpartum", "hospital", "home", "Taipei", "citizen"
            )

    principal = AdminPrincipal(1, "admin", "Admin", "system_admin")
    statistics = get_form_management_statistics(principal, _Application())
    context = get_form_management_case_context("CASE-001", principal, _Application())

    assert statistics.data.global_total_receivable_sum == 2400
    assert context.data.case_no == "CASE-001"
