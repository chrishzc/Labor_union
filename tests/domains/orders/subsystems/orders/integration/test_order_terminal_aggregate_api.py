"""Focused API contract test for the Order Workbench terminal aggregate."""

from types import SimpleNamespace

import api.routes.orders_core_stage_projection as route_module
from subsystems.orders.core_stage_filter_query import (
    CoreStageProjectionFilterQuery,
    OrderCoreStageTimelineFilteredPage,
)
from subsystems.orders.government_subsidy_projection_query import (
    GovernmentSubsidyProjectionQuery,
    OrderGovernmentSubsidyProjectionPage,
)
from subsystems.orders.terminal_aggregate_query import (
    OrderTerminalAggregate,
    TerminalCompletionComponent,
)


def test_terminal_aggregate_route_returns_server_owner_and_reason(monkeypatch):
    captured = {}
    core_item = SimpleNamespace(case_no="CASE-OPEN")
    subsidy_item = SimpleNamespace(case_no="CASE-OPEN")

    def fake_core(source, request):
        captured["core_source"] = source
        captured["core_request"] = request
        return OrderCoreStageTimelineFilteredPage(
            items=(core_item,),
            stage_counts={},
            substatus_counts={},
            historical_lifecycle_counts={},
            next_cursor=None,
            etag="a" * 64,
        )

    def fake_subsidy(source, repository, request):
        captured["subsidy_source"] = source
        captured["repository"] = repository
        captured["subsidy_request"] = request
        return OrderGovernmentSubsidyProjectionPage(
            items=(subsidy_item,),
            substatus_counts={},
            next_cursor=None,
            etag="b" * 64,
        )

    def fake_project(timeline, subsidy):
        assert timeline is core_item
        assert subsidy is subsidy_item
        return OrderTerminalAggregate(
            case_no="CASE-OPEN",
            applicable=True,
            fully_closed=False,
            components=(
                TerminalCompletionComponent(
                    code="client_settlement",
                    owner="Client Finance",
                    completed=False,
                    reason="client_balance_open",
                ),
            ),
        )

    monkeypatch.setattr(route_module, "query_core_stage_page", fake_core)
    monkeypatch.setattr(route_module, "query_government_subsidy_projection_page", fake_subsidy)
    monkeypatch.setattr(route_module, "project_terminal_aggregate", fake_project)

    source = object()
    repository = object()
    result = route_module.get_order_terminal_aggregates(
        page_size=50,
        after_case_no=None,
        case_no_search="CASE",
        principal=None,
        application=source,
        repository=repository,
    )

    assert captured["core_source"] is source
    assert captured["subsidy_source"] is source
    assert captured["repository"] is repository
    assert captured["core_request"] == CoreStageProjectionFilterQuery(
        page_size=50,
        case_no_search="CASE",
        branch_type="normal",
    )
    assert captured["subsidy_request"] == GovernmentSubsidyProjectionQuery(
        page_size=50,
        case_no_search="CASE",
    )
    assert result.data.items[0].case_no == "CASE-OPEN"
    assert result.data.items[0].fully_closed is False
    assert result.data.items[0].components[0].owner == "Client Finance"
    assert result.data.items[0].components[0].reason == "client_balance_open"
