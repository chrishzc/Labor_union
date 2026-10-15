"""Focused tests for the Order Workbench Government Subsidy side-lane projection."""

from datetime import date, datetime, timezone
from dataclasses import replace

from domains.government_subsidy.ledger import GovernmentSubsidyBatchStatus
from domains.government_subsidy.overpayment import GovernmentSubsidyOverpaymentStatus
from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.government_subsidy_projection_query import (
    GovernmentSubsidyClaimItemProjectionFact,
    GovernmentSubsidyOrderProjectionFacts,
    GovernmentSubsidyOverpaymentProjectionFact,
    GovernmentSubsidyProjectionQuery,
    query_government_subsidy_projection_page,
)
from subsystems.orders.stage_projection_query import (
    AvailableAction,
    OrderOperationalTimeline,
    OrderOperationalTimelinePage,
    SettlementProjection,
    SopStepProjection,
    SourceLineage,
    StageProjection,
)


_AT = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
_DIGEST = "a" * 64
_STAGE_CODES = (
    "intake_terms",
    "matching_willingness",
    "client_review",
    "contract_deposit",
    "date_confirmation",
    "active_service",
    "settlement_payout",
)
_STEP_CODES = (
    "intake_validation",
    "matching_pool",
    "caregiver_line_delivery",
    "caregiver_willingness_reply",
    "formal_recommendation",
    "external_signing_dispatch",
    "external_signing_completion",
    "deposit_settlement",
    "confirmed_service_dates",
    "formal_service",
    "settlement_close",
)


def _source(owner: str, identity: str) -> SourceLineage:
    return SourceLineage(owner, identity, 1)


def _stage(ordinal: int, code: str, *, settlement=()) -> StageProjection:
    return StageProjection(
        ordinal=ordinal,
        code=code,
        label=code,
        owner=f"owner-{code}",
        status="completed",
        source=_source(f"source-{code}", f"{code}:1"),
        occurred_at=_AT,
        blockers=(),
        warnings=(),
        available_actions=(
            AvailableAction(f"read.{code}", "GET", f"/read/{code}"),
        ),
        availability_reason=None,
        settlement=settlement,
    )


def _step(ordinal: int, status: str = "completed") -> SopStepProjection:
    return SopStepProjection(
        ordinal=ordinal,
        code=_STEP_CODES[ordinal - 1],
        label=_STEP_CODES[ordinal - 1],
        owner=f"step-owner-{ordinal}",
        status=status,
        occurred_at=_AT,
        blockers=(),
        warnings=(),
        available_actions=(),
        availability_reason=None,
    )


def _timeline(
    case_no: str,
    lifecycle: OrderLifecycleStatus = OrderLifecycleStatus.IN_SERVICE,
) -> OrderOperationalTimeline:
    settlement = (
        SettlementProjection(
            "service_completion",
            "completed",
            _source("Orders", f"service-completion:{case_no}"),
            _AT,
            None,
        ),
        SettlementProjection(
            "client_settlement",
            "completed",
            _source("Client Finance", f"client-settlement:{case_no}"),
            _AT,
            None,
        ),
        SettlementProjection(
            "staff_payout",
            "completed",
            _source("Staff Payables", f"staff-payout:{case_no}"),
            _AT,
            None,
        ),
    )
    stages = tuple(
        _stage(index + 1, code, settlement=settlement if code == "settlement_payout" else ())
        for index, code in enumerate(_STAGE_CODES)
    )
    normal = lifecycle not in {
        OrderLifecycleStatus.CANCELLED,
        OrderLifecycleStatus.HISTORICAL_UNSERVED,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    }
    steps = tuple(
        _step(index, "in_progress" if normal and index == 10 else "completed")
        for index in range(1, 12)
    )
    return OrderOperationalTimeline(
        case_no=case_no,
        base_revision=1,
        lifecycle_status=lifecycle,
        replacement_resume_step_ordinal=None,
        current_stage_code="active_service" if normal else None,
        current_step_ordinal=10 if normal else None,
        stages=stages,
        sop_steps=steps,
        projection_digest=_DIGEST,
    )


class _Source:
    def __init__(self, *items: OrderOperationalTimeline) -> None:
        self.items = tuple(sorted(items, key=lambda item: item.case_no.casefold()))

    def query(self, request):
        assert request.after_case_no is None
        return OrderOperationalTimelinePage(
            items=tuple(self.items),
            stage_counts={code: 0 for code in _STAGE_CODES},
            next_cursor=None,
            etag="b" * 64,
        )


class _Repository:
    def __init__(self, facts: dict[str, GovernmentSubsidyOrderProjectionFacts]) -> None:
        self.facts = facts
        self.requests: list[tuple[str, ...]] = []

    def query_order_projection_facts(self, case_nos):
        self.requests.append(case_nos)
        return tuple(self.facts[case_no] for case_no in case_nos)


def _claim(
    case_no: str,
    *,
    item_id: int = 1,
    batch_id: int = 10,
    status: GovernmentSubsidyBatchStatus = GovernmentSubsidyBatchStatus.SUBMITTED,
    claimed_hours: int = 8,
    unit_price_ntd: int = 300,
    requested_amount_ntd: int = 2400,
    approved_amount_ntd: int = 0,
    net_allocated_ntd: int = 0,
) -> GovernmentSubsidyClaimItemProjectionFact:
    return GovernmentSubsidyClaimItemProjectionFact(
        item_id=item_id,
        batch_id=batch_id,
        batch_version=2,
        status=status,
        claimed_hours=claimed_hours,
        unit_price_ntd=unit_price_ntd,
        requested_amount_ntd=requested_amount_ntd,
        approved_amount_ntd=approved_amount_ntd,
        net_allocated_ntd=net_allocated_ntd,
        submitted_at=_AT if status is not GovernmentSubsidyBatchStatus.DRAFT else None,
        approved_at=_AT
        if status
        in {
            GovernmentSubsidyBatchStatus.APPROVED,
            GovernmentSubsidyBatchStatus.PARTIALLY_PAID,
            GovernmentSubsidyBatchStatus.PAID,
        }
        else None,
    )


def _facts(
    case_no: str,
    *,
    identity_status: str | None = "一般市民",
    actual_end_date: date | None = date(2026, 9, 30),
    claims=(),
    overpayments=(),
) -> GovernmentSubsidyOrderProjectionFacts:
    return GovernmentSubsidyOrderProjectionFacts(
        case_no=case_no,
        identity_status=identity_status,
        actual_end_date=actual_end_date,
        claim_items=tuple(claims),
        overpayments=tuple(overpayments),
    )


def test_every_normal_order_has_owner_projection_or_traceable_claim_gap() -> None:
    source = _Source(
        _timeline("CASE-GAP"),
        _timeline("CASE-SUBMITTED"),
        _timeline(
            "CASE-HIST",
            OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        ),
    )
    repository = _Repository(
        {
            "CASE-GAP": _facts("CASE-GAP", claims=()),
            "CASE-SUBMITTED": _facts(
                "CASE-SUBMITTED",
                claims=(_claim("CASE-SUBMITTED"),),
            ),
        }
    )

    page = query_government_subsidy_projection_page(
        source,
        repository,
        GovernmentSubsidyProjectionQuery(page_size=50),
    )

    assert [item.case_no for item in page.items] == ["CASE-GAP", "CASE-SUBMITTED"]
    assert page.substatus_counts["claim_lineage_missing"] == 1
    assert page.substatus_counts["submitted"] == 1
    assert repository.requests == [("CASE-GAP", "CASE-SUBMITTED")]
    gap = page.items[0]
    assert gap.source.owner == "Government Subsidy"
    assert gap.source.identity is None
    assert [notice.code for notice in gap.blockers] == [
        "government_subsidy_claim_lineage_missing"
    ]
    assert gap.claim_quarter == 3
    assert (gap.claim_application_year, gap.claim_application_month) == (2026, 10)
    assert gap.claim_submitted_at is None


def test_receivable_estimate_is_separate_from_unknown_approval_and_current_outstanding():
    facts = {
        "CASE-GAP": replace(_facts("CASE-GAP"), estimated_subsidy_amount_ntd=12000),
        "CASE-SUBMITTED": _facts("CASE-SUBMITTED", claims=(_claim("CASE-SUBMITTED"),)),
        "CASE-APPROVED": _facts("CASE-APPROVED", claims=(_claim("CASE-APPROVED", status=GovernmentSubsidyBatchStatus.PARTIALLY_PAID, approved_amount_ntd=2000, net_allocated_ntd=500),)),
    }
    page = query_government_subsidy_projection_page(_Source(*(_timeline(case) for case in facts)), _Repository(facts), GovernmentSubsidyProjectionQuery(50))
    rows = {item.case_no: item for item in page.items}
    assert rows["CASE-GAP"].estimated_subsidy_amount_ntd == 12000
    assert rows["CASE-GAP"].confirmed_approved_amount_ntd is None
    assert rows["CASE-GAP"].outstanding_amount_ntd is None
    assert rows["CASE-SUBMITTED"].estimated_subsidy_amount_ntd == 2400
    assert rows["CASE-SUBMITTED"].confirmed_approved_amount_ntd is None
    assert rows["CASE-SUBMITTED"].outstanding_amount_ntd is None
    assert rows["CASE-APPROVED"].confirmed_approved_amount_ntd == 2000
    assert rows["CASE-APPROVED"].outstanding_amount_ntd == 1500


def test_service_end_requires_completed_owner_evidence_not_a_date_or_claim():
    timeline = _timeline("CASE-PENDING")
    stages = tuple(replace(stage, settlement=tuple(replace(part, status="unavailable", source=SourceLineage("Orders", None, None)) if part.code == "service_completion" else part for part in stage.settlement)) for stage in timeline.stages)
    source = _Source(replace(timeline, stages=stages))
    facts = _facts("CASE-PENDING")  # recorded end date alone is insufficient
    first = query_government_subsidy_projection_page(source, _Repository({facts.case_no: facts}), GovernmentSubsidyProjectionQuery(50))
    assert first.items[0].service_end_confirmed is False
    second = query_government_subsidy_projection_page(_Source(timeline), _Repository({facts.case_no: facts}), GovernmentSubsidyProjectionQuery(50))
    assert second.items[0].service_end_confirmed is True
    assert second.etag != first.etag


def test_projection_api_preserves_null_amounts_and_exact_estimate_contract():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes.orders_stage_projection import router
    from api.dependencies.orders_stage_projection import get_orders_stage_projection_application
    from api.dependencies.order_government_subsidy_projection import get_order_government_subsidy_projection_repository
    from api.dependencies.admin_auth import require_system_admin
    from subsystems.access.authentication_session import AdminPrincipal
    api = FastAPI()
    api.include_router(router)
    api.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(1, "test-admin", "驗證", "system_admin")
    api.dependency_overrides[get_orders_stage_projection_application] = lambda: _Source(_timeline("CASE-GAP"))
    facts = replace(_facts("CASE-GAP"), estimated_subsidy_amount_ntd=12000)
    api.dependency_overrides[get_order_government_subsidy_projection_repository] = lambda: _Repository({facts.case_no: facts})
    result = TestClient(api).get('/api/orders/government-subsidy-projections')
    assert result.status_code == 200, result.text
    row = result.json()['data']['items'][0]
    assert row['estimated_subsidy_amount_ntd'] == 12000
    assert row['confirmed_approved_amount_ntd'] is None
    assert row['outstanding_amount_ntd'] is None
    assert row['service_end_confirmed'] is True


def test_substatus_filter_and_counts_are_server_side_and_counts_ignore_filter() -> None:
    source = _Source(_timeline("CASE-DRAFT"), _timeline("CASE-PAID"))
    repository = _Repository(
        {
            "CASE-DRAFT": _facts(
                "CASE-DRAFT",
                claims=(
                    _claim(
                        "CASE-DRAFT",
                        status=GovernmentSubsidyBatchStatus.DRAFT,
                    ),
                ),
            ),
            "CASE-PAID": _facts(
                "CASE-PAID",
                claims=(
                    _claim(
                        "CASE-PAID",
                        batch_id=20,
                        status=GovernmentSubsidyBatchStatus.PAID,
                        approved_amount_ntd=2400,
                        net_allocated_ntd=2400,
                    ),
                ),
            ),
        }
    )

    page = query_government_subsidy_projection_page(
        source,
        repository,
        GovernmentSubsidyProjectionQuery(page_size=50, substatus_code="paid"),
    )

    assert [item.case_no for item in page.items] == ["CASE-PAID"]
    assert page.substatus_counts["draft"] == 1
    assert page.substatus_counts["paid"] == 1


def test_open_overpayment_uses_existing_owner_status_and_read_action() -> None:
    overpayment = GovernmentSubsidyOverpaymentProjectionFact(
        identity="gov-overpayment:CASE-1",
        batch_id=10,
        status=GovernmentSubsidyOverpaymentStatus.PENDING_REVIEW,
        remaining_amount_ntd=600,
        version=4,
    )
    source = _Source(_timeline("CASE-1"))
    repository = _Repository(
        {
            "CASE-1": _facts(
                "CASE-1",
                claims=(
                    _claim(
                        "CASE-1",
                        status=GovernmentSubsidyBatchStatus.PAID,
                        approved_amount_ntd=2400,
                        net_allocated_ntd=2400,
                    ),
                ),
                overpayments=(overpayment,),
            )
        }
    )

    page = query_government_subsidy_projection_page(
        source,
        repository,
        GovernmentSubsidyProjectionQuery(page_size=50),
    )

    item = page.items[0]
    assert item.substatus_code == "pending_review"
    assert item.source.owner == "Government Subsidy Overpayment"
    assert item.source.identity == "gov-overpayment:CASE-1"
    assert item.overpayment_remaining_ntd == 600
    assert item.blockers[0].code == "government_subsidy_overpayment_pending_review"
    assert item.available_read_actions[0].path.endswith("/gov-overpayment:CASE-1")


def test_identity_limit_inputs_are_readback_only_and_not_recapped_in_workbench() -> None:
    source = _Source(_timeline("CASE-READBACK"))
    repository = _Repository(
        {
            "CASE-READBACK": _facts(
                "CASE-READBACK",
                identity_status="一般市民",
                claims=(
                    _claim(
                        "CASE-READBACK",
                        claimed_hours=77,
                        unit_price_ntd=300,
                        requested_amount_ntd=23100,
                    ),
                ),
            )
        }
    )

    item = query_government_subsidy_projection_page(
        source,
        repository,
        GovernmentSubsidyProjectionQuery(page_size=50),
    ).items[0]

    assert item.identity_status == "一般市民"
    assert item.claimed_hours == 77
    assert item.unit_price_ntd == 300
    assert item.requested_amount_ntd == 23100


def test_missing_identity_status_is_a_case_level_data_gap_not_a_page_failure() -> None:
    source = _Source(_timeline("CASE-NO-IDENTITY"))
    repository = _Repository(
        {
            "CASE-NO-IDENTITY": _facts(
                "CASE-NO-IDENTITY",
                identity_status=None,
                claims=(_claim("CASE-NO-IDENTITY"),),
            )
        }
    )

    item = query_government_subsidy_projection_page(
        source,
        repository,
        GovernmentSubsidyProjectionQuery(page_size=50),
    ).items[0]

    assert item.substatus_code == "submitted"
    assert item.blockers[0].code == "government_subsidy_identity_status_missing"
