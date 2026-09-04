"""Read-only Government Subsidy side-lane projection for Order Workbench Beta."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Literal, Mapping, Protocol, cast

from domains.government_subsidy.ledger import GovernmentSubsidyBatchStatus
from domains.government_subsidy.overpayment import GovernmentSubsidyOverpaymentStatus
from domains.orders.lifecycle import OrderLifecycleScope, OrderLifecycleStatus
from shared_kernel.validation import require_canonical_text, require_positive_integer
from subsystems.orders.stage_projection_query import (
    AvailableAction,
    MAXIMUM_PAGE_SIZE,
    OrderOperationalTimelinePage,
    ProjectionNotice,
    SourceLineage,
    StageProjectionQuery,
)


GovernmentSubsidySubstatusCode = Literal[
    "claim_lineage_missing",
    "draft",
    "submitted",
    "approved",
    "partially_paid",
    "paid",
    "pending_review",
    "offset_reserved",
    "offset_applied",
    "return_payable",
    "partially_returned",
    "returned",
]
_SUBSTATUS_CODES: tuple[GovernmentSubsidySubstatusCode, ...] = (
    "claim_lineage_missing",
    "draft",
    "submitted",
    "approved",
    "partially_paid",
    "paid",
    "pending_review",
    "offset_reserved",
    "offset_applied",
    "return_payable",
    "partially_returned",
    "returned",
)
_ACTIVE_OVERPAYMENT_STATUSES = frozenset(
    {
        GovernmentSubsidyOverpaymentStatus.PENDING_REVIEW,
        GovernmentSubsidyOverpaymentStatus.OFFSET_RESERVED,
        GovernmentSubsidyOverpaymentStatus.RETURN_PAYABLE,
        GovernmentSubsidyOverpaymentStatus.PARTIALLY_RETURNED,
    }
)
_OVERPAYMENT_PRIORITY = {
    GovernmentSubsidyOverpaymentStatus.PENDING_REVIEW: 0,
    GovernmentSubsidyOverpaymentStatus.OFFSET_RESERVED: 1,
    GovernmentSubsidyOverpaymentStatus.RETURN_PAYABLE: 1,
    GovernmentSubsidyOverpaymentStatus.PARTIALLY_RETURNED: 2,
}
_CLAIM_PRIORITY = {
    GovernmentSubsidyBatchStatus.DRAFT: 0,
    GovernmentSubsidyBatchStatus.SUBMITTED: 1,
    GovernmentSubsidyBatchStatus.APPROVED: 2,
    GovernmentSubsidyBatchStatus.PARTIALLY_PAID: 3,
    GovernmentSubsidyBatchStatus.PAID: 4,
}
_NON_NORMAL_LIFECYCLE_STATUSES = frozenset(
    {
        OrderLifecycleStatus.CANCELLED,
        OrderLifecycleStatus.HISTORICAL_UNSERVED,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    }
)


class GovernmentSubsidyProjectionContractError(ValueError):
    """Government Subsidy owner facts cannot form a deterministic order projection."""


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyClaimItemProjectionFact:
    item_id: int
    batch_id: int
    batch_version: int
    status: GovernmentSubsidyBatchStatus
    claimed_hours: int
    unit_price_ntd: int
    requested_amount_ntd: int
    approved_amount_ntd: int
    net_allocated_ntd: int
    submitted_at: datetime | None
    approved_at: datetime | None


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyOverpaymentProjectionFact:
    identity: str
    batch_id: int
    status: GovernmentSubsidyOverpaymentStatus
    remaining_amount_ntd: int
    version: int


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyOrderProjectionFacts:
    case_no: str
    identity_status: str | None
    claim_items: tuple[GovernmentSubsidyClaimItemProjectionFact, ...]
    overpayments: tuple[GovernmentSubsidyOverpaymentProjectionFact, ...]


class GovernmentSubsidyOrderProjectionRepository(Protocol):
    def query_order_projection_facts(
        self,
        case_nos: tuple[str, ...],
    ) -> tuple[GovernmentSubsidyOrderProjectionFacts, ...]: ...


class OperationalTimelineQueryPort(Protocol):
    def query(self, request: StageProjectionQuery) -> OrderOperationalTimelinePage: ...


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyProjectionQuery:
    page_size: int
    after_case_no: str | None = None
    case_no_search: str | None = None
    substatus_code: GovernmentSubsidySubstatusCode | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.page_size, "page_size")
        if self.page_size > MAXIMUM_PAGE_SIZE:
            raise ValueError("page_size must not exceed 200")
        if self.after_case_no is not None:
            require_canonical_text(self.after_case_no, "after_case_no", 50)
        if self.case_no_search is not None:
            require_canonical_text(self.case_no_search, "case_no_search", 50)
        if self.substatus_code is not None and self.substatus_code not in _SUBSTATUS_CODES:
            raise ValueError("substatus_code is outside the Government Subsidy projection contract")


@dataclass(frozen=True, slots=True)
class OrderGovernmentSubsidyProjection:
    case_no: str
    substatus_code: GovernmentSubsidySubstatusCode
    identity_status: str | None
    source: SourceLineage
    occurred_at: datetime | None
    blockers: tuple[ProjectionNotice, ...]
    warnings: tuple[ProjectionNotice, ...]
    available_read_actions: tuple[AvailableAction, ...]
    claim_batch_id: int | None
    claim_item_count: int
    claimed_hours: int
    unit_price_ntd: int | None
    requested_amount_ntd: int
    approved_amount_ntd: int
    net_allocated_ntd: int
    overpayment_identity: str | None
    overpayment_remaining_ntd: int | None


@dataclass(frozen=True, slots=True)
class OrderGovernmentSubsidyProjectionPage:
    items: tuple[OrderGovernmentSubsidyProjection, ...]
    substatus_counts: Mapping[GovernmentSubsidySubstatusCode, int]
    next_cursor: str | None
    etag: str


def query_government_subsidy_projection_page(
    source: OperationalTimelineQueryPort,
    repository: GovernmentSubsidyOrderProjectionRepository,
    request: GovernmentSubsidyProjectionQuery,
) -> OrderGovernmentSubsidyProjectionPage:
    if not isinstance(request, GovernmentSubsidyProjectionQuery):
        raise TypeError("request must be a GovernmentSubsidyProjectionQuery")

    counts: dict[GovernmentSubsidySubstatusCode, int] = {
        code: 0 for code in _SUBSTATUS_CODES
    }
    selected: list[OrderGovernmentSubsidyProjection] = []
    has_more = False
    source_cursor: str | None = None
    last_source_key: str | None = None
    requested_cursor_key = request.after_case_no.casefold() if request.after_case_no else None

    while True:
        source_page = source.query(
            StageProjectionQuery(
                page_size=MAXIMUM_PAGE_SIZE,
                after_case_no=source_cursor,
                lifecycle_scope=OrderLifecycleScope.ALL,
            )
        )
        _validate_source_page(source_page, source_cursor)

        normal_case_nos: list[str] = []
        for source_item in source_page.items:
            identity_key = source_item.case_no.casefold()
            if last_source_key is not None and identity_key <= last_source_key:
                raise GovernmentSubsidyProjectionContractError(
                    "source pages are duplicate or unordered"
                )
            last_source_key = identity_key
            if source_item.lifecycle_status not in _NON_NORMAL_LIFECYCLE_STATUSES:
                normal_case_nos.append(source_item.case_no)

        facts_by_case = _facts_by_case(
            repository.query_order_projection_facts(tuple(normal_case_nos))
            if normal_case_nos
            else (),
            tuple(normal_case_nos),
        )
        for case_no in normal_case_nos:
            projection = _project(facts_by_case[case_no.casefold()])
            if (
                request.case_no_search is not None
                and request.case_no_search.casefold() not in projection.case_no.casefold()
            ):
                continue
            counts[projection.substatus_code] += 1
            identity_key = projection.case_no.casefold()
            if requested_cursor_key is not None and identity_key <= requested_cursor_key:
                continue
            if (
                request.substatus_code is not None
                and projection.substatus_code != request.substatus_code
            ):
                continue
            if len(selected) < request.page_size:
                selected.append(projection)
            else:
                has_more = True

        if source_page.next_cursor is None:
            break
        source_cursor = source_page.next_cursor

    items = tuple(selected)
    next_cursor = items[-1].case_no if has_more and items else None
    return OrderGovernmentSubsidyProjectionPage(
        items=items,
        substatus_counts=counts,
        next_cursor=next_cursor,
        etag=_response_etag(items, counts, next_cursor),
    )


def _validate_source_page(
    page: object,
    previous_cursor: str | None,
) -> None:
    if not isinstance(page, OrderOperationalTimelinePage):
        raise GovernmentSubsidyProjectionContractError(
            "source query did not return an operational timeline page"
        )
    if len(page.items) > MAXIMUM_PAGE_SIZE:
        raise GovernmentSubsidyProjectionContractError("source page is not bounded")
    if page.next_cursor is None:
        return
    if not page.items or page.next_cursor.casefold() != page.items[-1].case_no.casefold():
        raise GovernmentSubsidyProjectionContractError("source page cursor is invalid")
    if (
        previous_cursor is not None
        and page.next_cursor.casefold() <= previous_cursor.casefold()
    ):
        raise GovernmentSubsidyProjectionContractError("source page cursor did not advance")


def _facts_by_case(
    facts: tuple[GovernmentSubsidyOrderProjectionFacts, ...],
    case_nos: tuple[str, ...],
) -> dict[str, GovernmentSubsidyOrderProjectionFacts]:
    result: dict[str, GovernmentSubsidyOrderProjectionFacts] = {}
    for fact in facts:
        key = fact.case_no.casefold()
        if key in result:
            raise GovernmentSubsidyProjectionContractError(
                "Government Subsidy facts contain duplicate case identity"
            )
        result[key] = fact
    expected = {case_no.casefold() for case_no in case_nos}
    if set(result) != expected:
        raise GovernmentSubsidyProjectionContractError(
            "Government Subsidy facts do not cover the requested normal orders"
        )
    return result


def _project(
    facts: GovernmentSubsidyOrderProjectionFacts,
) -> OrderGovernmentSubsidyProjection:
    identity_blockers = _identity_blockers(facts)
    if not facts.claim_items:
        return OrderGovernmentSubsidyProjection(
            case_no=facts.case_no,
            substatus_code="claim_lineage_missing",
            identity_status=facts.identity_status,
            source=SourceLineage("Government Subsidy", None, None),
            occurred_at=None,
            blockers=(
                ProjectionNotice(
                    "government_subsidy_claim_lineage_missing",
                    "正常訂單尚未找到正式 Government Subsidy claim 關聯。",
                ),
                *identity_blockers,
            ),
            warnings=(),
            available_read_actions=(
                AvailableAction(
                    "government_subsidy.claim_batches.query",
                    "GET",
                    "/api/v1/government-subsidy/claim-batches",
                ),
            ),
            claim_batch_id=None,
            claim_item_count=0,
            claimed_hours=0,
            unit_price_ntd=None,
            requested_amount_ntd=0,
            approved_amount_ntd=0,
            net_allocated_ntd=0,
            overpayment_identity=None,
            overpayment_remaining_ntd=None,
        )

    batches = _claim_batches(facts.claim_items)
    active_overpayments = tuple(
        item for item in facts.overpayments if item.status in _ACTIVE_OVERPAYMENT_STATUSES
    )
    warnings: tuple[ProjectionNotice, ...] = ()
    if len(active_overpayments) > 1:
        warnings = (
            ProjectionNotice(
                "government_subsidy_multiple_open_overpayments",
                f"此訂單關聯 {len(active_overpayments)} 筆尚未完成的 Government Subsidy 溢撥處置。",
            ),
        )

    if active_overpayments:
        selected_overpayment = min(
            active_overpayments,
            key=lambda item: (
                _OVERPAYMENT_PRIORITY[item.status],
                item.batch_id,
                item.identity.casefold(),
            ),
        )
        selected_batch_id = selected_overpayment.batch_id
        selected_items = batches.get(selected_batch_id)
        if selected_items is None:
            raise GovernmentSubsidyProjectionContractError(
                "overpayment batch is not linked to the order claim facts"
            )
        return _projection_from_items(
            facts,
            selected_items,
            cast(GovernmentSubsidySubstatusCode, selected_overpayment.status.value),
            SourceLineage(
                "Government Subsidy Overpayment",
                selected_overpayment.identity,
                selected_overpayment.version,
            ),
            None,
            blockers=(
                ProjectionNotice(
                    f"government_subsidy_overpayment_{selected_overpayment.status.value}",
                    "Government Subsidy 溢撥／退款 owner 尚有未完成處置。",
                ),
                *identity_blockers,
            ),
            warnings=warnings,
            read_actions=(
                AvailableAction(
                    "government_subsidy.overpayment.query",
                    "GET",
                    f"/api/v1/government-subsidy/overpayments/{selected_overpayment.identity}",
                ),
                AvailableAction(
                    "government_subsidy.claim_batch.query",
                    "GET",
                    f"/api/v1/government-subsidy/claim-batches/{selected_batch_id}",
                ),
            ),
            overpayment=selected_overpayment,
        )

    incomplete_batches = tuple(
        (batch_id, items)
        for batch_id, items in batches.items()
        if items[0].status is not GovernmentSubsidyBatchStatus.PAID
    )
    if incomplete_batches:
        selected_batch_id, selected_items = min(
            incomplete_batches,
            key=lambda entry: (_CLAIM_PRIORITY[entry[1][0].status], entry[0]),
        )
        return _claim_projection(
            facts,
            selected_batch_id,
            selected_items,
            warnings,
        )

    terminal_overpayments = tuple(
        item
        for item in facts.overpayments
        if item.status
        in {
            GovernmentSubsidyOverpaymentStatus.OFFSET_APPLIED,
            GovernmentSubsidyOverpaymentStatus.RETURNED,
        }
    )
    if terminal_overpayments:
        selected_overpayment = max(
            terminal_overpayments,
            key=lambda item: (item.batch_id, item.version, item.identity.casefold()),
        )
        selected_items = batches.get(selected_overpayment.batch_id)
        if selected_items is not None:
            return _projection_from_items(
                facts,
                selected_items,
                cast(GovernmentSubsidySubstatusCode, selected_overpayment.status.value),
                SourceLineage(
                    "Government Subsidy Overpayment",
                    selected_overpayment.identity,
                    selected_overpayment.version,
                ),
                None,
                blockers=identity_blockers,
                warnings=warnings,
                read_actions=(
                    AvailableAction(
                        "government_subsidy.overpayment.query",
                        "GET",
                        f"/api/v1/government-subsidy/overpayments/{selected_overpayment.identity}",
                    ),
                    AvailableAction(
                        "government_subsidy.claim_batch.query",
                        "GET",
                        f"/api/v1/government-subsidy/claim-batches/{selected_overpayment.batch_id}",
                    ),
                ),
                overpayment=selected_overpayment,
            )

    selected_batch_id = max(batches)
    return _claim_projection(
        facts,
        selected_batch_id,
        batches[selected_batch_id],
        warnings,
    )


def _identity_blockers(
    facts: GovernmentSubsidyOrderProjectionFacts,
) -> tuple[ProjectionNotice, ...]:
    if facts.identity_status is not None:
        return ()
    return (
        ProjectionNotice(
            "government_subsidy_identity_status_missing",
            "Government Subsidy 補助上限所需身分類別尚未由 owner facts 提供。",
        ),
    )


def _claim_batches(
    claim_items: tuple[GovernmentSubsidyClaimItemProjectionFact, ...],
) -> dict[int, tuple[GovernmentSubsidyClaimItemProjectionFact, ...]]:
    grouped: dict[int, list[GovernmentSubsidyClaimItemProjectionFact]] = {}
    for item in claim_items:
        grouped.setdefault(item.batch_id, []).append(item)
    result: dict[int, tuple[GovernmentSubsidyClaimItemProjectionFact, ...]] = {}
    for batch_id, mutable_items in grouped.items():
        items = tuple(sorted(mutable_items, key=lambda item: item.item_id))
        first = items[0]
        if any(
            item.batch_version != first.batch_version
            or item.status is not first.status
            or item.submitted_at != first.submitted_at
            or item.approved_at != first.approved_at
            for item in items
        ):
            raise GovernmentSubsidyProjectionContractError(
                "claim batch facts are inconsistent for one order"
            )
        result[batch_id] = items
    return result


def _claim_projection(
    facts: GovernmentSubsidyOrderProjectionFacts,
    batch_id: int,
    items: tuple[GovernmentSubsidyClaimItemProjectionFact, ...],
    warnings: tuple[ProjectionNotice, ...],
) -> OrderGovernmentSubsidyProjection:
    first = items[0]
    occurred_at = (
        first.submitted_at
        if first.status is GovernmentSubsidyBatchStatus.SUBMITTED
        else first.approved_at
        if first.status is GovernmentSubsidyBatchStatus.APPROVED
        else None
    )
    return _projection_from_items(
        facts,
        items,
        cast(GovernmentSubsidySubstatusCode, first.status.value),
        SourceLineage("Government Subsidy", f"claim-batch:{batch_id}", first.batch_version),
        occurred_at,
        blockers=_identity_blockers(facts),
        warnings=warnings,
        read_actions=(
            AvailableAction(
                "government_subsidy.claim_batch.query",
                "GET",
                f"/api/v1/government-subsidy/claim-batches/{batch_id}",
            ),
        ),
        overpayment=None,
    )


def _projection_from_items(
    facts: GovernmentSubsidyOrderProjectionFacts,
    items: tuple[GovernmentSubsidyClaimItemProjectionFact, ...],
    substatus_code: GovernmentSubsidySubstatusCode,
    source: SourceLineage,
    occurred_at: datetime | None,
    *,
    blockers: tuple[ProjectionNotice, ...],
    warnings: tuple[ProjectionNotice, ...],
    read_actions: tuple[AvailableAction, ...],
    overpayment: GovernmentSubsidyOverpaymentProjectionFact | None,
) -> OrderGovernmentSubsidyProjection:
    batch_id = items[0].batch_id
    unit_prices = {item.unit_price_ntd for item in items}
    return OrderGovernmentSubsidyProjection(
        case_no=facts.case_no,
        substatus_code=substatus_code,
        identity_status=facts.identity_status,
        source=source,
        occurred_at=occurred_at,
        blockers=blockers,
        warnings=warnings,
        available_read_actions=read_actions,
        claim_batch_id=batch_id,
        claim_item_count=len(items),
        claimed_hours=sum(item.claimed_hours for item in items),
        unit_price_ntd=next(iter(unit_prices)) if len(unit_prices) == 1 else None,
        requested_amount_ntd=sum(item.requested_amount_ntd for item in items),
        approved_amount_ntd=sum(item.approved_amount_ntd for item in items),
        net_allocated_ntd=sum(item.net_allocated_ntd for item in items),
        overpayment_identity=None if overpayment is None else overpayment.identity,
        overpayment_remaining_ntd=(
            None if overpayment is None else overpayment.remaining_amount_ntd
        ),
    )


def _response_etag(
    items: tuple[OrderGovernmentSubsidyProjection, ...],
    counts: Mapping[GovernmentSubsidySubstatusCode, int],
    next_cursor: str | None,
) -> str:
    payload = {
        "items": [
            {
                "case_no": item.case_no,
                "substatus_code": item.substatus_code,
                "source": (
                    item.source.owner,
                    item.source.identity,
                    item.source.version,
                ),
                "claim_batch_id": item.claim_batch_id,
                "claim_item_count": item.claim_item_count,
                "claimed_hours": item.claimed_hours,
                "unit_price_ntd": item.unit_price_ntd,
                "requested_amount_ntd": item.requested_amount_ntd,
                "approved_amount_ntd": item.approved_amount_ntd,
                "net_allocated_ntd": item.net_allocated_ntd,
                "overpayment_identity": item.overpayment_identity,
                "overpayment_remaining_ntd": item.overpayment_remaining_ntd,
            }
            for item in items
        ],
        "substatus_counts": counts,
        "next_cursor": next_cursor,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "GovernmentSubsidyClaimItemProjectionFact",
    "GovernmentSubsidyOrderProjectionFacts",
    "GovernmentSubsidyOrderProjectionRepository",
    "GovernmentSubsidyOverpaymentProjectionFact",
    "GovernmentSubsidyProjectionContractError",
    "GovernmentSubsidyProjectionQuery",
    "GovernmentSubsidySubstatusCode",
    "OrderGovernmentSubsidyProjection",
    "OrderGovernmentSubsidyProjectionPage",
    "query_government_subsidy_projection_page",
]
