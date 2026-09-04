"""Focused API contract test for the Orders terminal aggregate."""

import api.routes.orders_stage_projection as route_module
from subsystems.orders.terminal_aggregate_query import (
    OrderTerminalAggregate,
    OrderTerminalAggregatePage,
    TerminalAggregateQuery,
    TerminalCompletionComponent,
)


def test_terminal_aggregate_route_returns_server_owner_and_reason(monkeypatch):
    captured = {}

    def fake_query(source, repository, request):
        captured["source"] = source
        captured["repository"] = repository
        captured["request"] = request
        return OrderTerminalAggregatePage(
            items=(
                OrderTerminalAggregate(
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
                ),
            ),
            next_cursor=None,
        )

    monkeypatch.setattr(route_module, "query_terminal_aggregate_page", fake_query)

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

    assert captured["source"] is source
    assert captured["repository"] is repository
    assert captured["request"] == TerminalAggregateQuery(
        page_size=50,
        case_no_search="CASE",
    )
    assert result.data.items[0].case_no == "CASE-OPEN"
    assert result.data.items[0].fully_closed is False
    assert result.data.items[0].components[0].owner == "Client Finance"
    assert result.data.items[0].components[0].reason == "client_balance_open"
