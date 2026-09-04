"""Focused API contract tests for the Order Workbench Government Subsidy side lane."""

from fastapi import Response

import api.routes.orders_stage_projection as route_module
from subsystems.orders.government_subsidy_projection_query import (
    GovernmentSubsidyProjectionQuery,
    OrderGovernmentSubsidyProjection,
    OrderGovernmentSubsidyProjectionPage,
)
from subsystems.orders.stage_projection_query import (
    AvailableAction,
    ProjectionNotice,
    SourceLineage,
)


def _counts(**overrides):
    result = {
        "claim_lineage_missing": 0,
        "draft": 0,
        "submitted": 0,
        "approved": 0,
        "partially_paid": 0,
        "paid": 0,
        "pending_review": 0,
        "offset_reserved": 0,
        "offset_applied": 0,
        "return_payable": 0,
        "partially_returned": 0,
        "returned": 0,
    }
    result.update(overrides)
    return result


def test_government_subsidy_route_returns_strict_owner_projection_and_etag(monkeypatch):
    captured = {}

    def fake_query(source, repository, request):
        captured["source"] = source
        captured["repository"] = repository
        captured["request"] = request
        return OrderGovernmentSubsidyProjectionPage(
            items=(
                OrderGovernmentSubsidyProjection(
                    case_no="CASE-1",
                    substatus_code="submitted",
                    identity_status="一般市民",
                    source=SourceLineage("Government Subsidy", "claim-batch:8", 2),
                    occurred_at=None,
                    blockers=(),
                    warnings=(
                        ProjectionNotice("owner_warning", "owner warning"),
                    ),
                    available_read_actions=(
                        AvailableAction(
                            "government_subsidy.claim_batch.query",
                            "GET",
                            "/api/v1/government-subsidy/claim-batches/8",
                        ),
                    ),
                    claim_batch_id=8,
                    claim_item_count=1,
                    claimed_hours=10,
                    unit_price_ntd=300,
                    requested_amount_ntd=3000,
                    approved_amount_ntd=0,
                    net_allocated_ntd=0,
                    overpayment_identity=None,
                    overpayment_remaining_ntd=None,
                ),
            ),
            substatus_counts=_counts(submitted=1),
            next_cursor=None,
            etag="a" * 64,
        )

    monkeypatch.setattr(
        route_module,
        "query_government_subsidy_projection_page",
        fake_query,
    )
    response = Response()
    source = object()
    repository = object()

    result = route_module.get_order_government_subsidy_projections(
        response=response,
        page_size=50,
        after_case_no=None,
        case_no_search="CASE",
        substatus_code="submitted",
        if_none_match=None,
        principal=None,
        application=source,
        repository=repository,
    )

    assert captured["source"] is source
    assert captured["repository"] is repository
    assert captured["request"] == GovernmentSubsidyProjectionQuery(
        page_size=50,
        case_no_search="CASE",
        substatus_code="submitted",
    )
    assert result.data.items[0].substatus_code == "submitted"
    assert result.data.items[0].source.identity == "claim-batch:8"
    assert result.data.substatus_counts.submitted == 1
    assert response.headers["etag"] == f'"{"a" * 64}"'
    assert response.headers["cache-control"] == "private, no-cache"
