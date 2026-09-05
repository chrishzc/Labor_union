"""Build the read-only terminal aggregate from current Orders owner projections."""

from __future__ import annotations

from dataclasses import dataclass

from domains.orders.lifecycle import OrderLifecycleScope, OrderLifecycleStatus
from shared_kernel.validation import require_canonical_text, require_positive_integer
from subsystems.orders.government_subsidy_projection_query import (
    GovernmentSubsidyOrderProjectionRepository,
    GovernmentSubsidyProjectionQuery,
    OperationalTimelineQueryPort,
    OrderGovernmentSubsidyProjection,
    query_government_subsidy_projection_page,
)
from subsystems.orders.stage_projection_query import (
    MAXIMUM_PAGE_SIZE,
    OrderOperationalTimeline,
    OrderOperationalTimelinePage,
    SettlementProjection,
    SopStepProjection,
    StageProjection,
    StageProjectionQuery,
)


_TERMINAL_SUBSIDY_SUBSTATUSES = frozenset({"paid", "offset_applied", "returned"})
_NON_NORMAL_LIFECYCLE_STATUSES = frozenset(
    {
        OrderLifecycleStatus.CANCELLED,
        OrderLifecycleStatus.HISTORICAL_UNSERVED,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    }
)
_SETTLEMENT_COMPONENT_CODES = (
    "service_completion",
    "client_settlement",
    "staff_payout",
)


class TerminalAggregateContractError(ValueError):
    """The terminal aggregate inputs do not describe one canonical order page."""


@dataclass(frozen=True, slots=True)
class TerminalAggregateQuery:
    page_size: int
    after_case_no: str | None = None
    case_no_search: str | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.page_size, "page_size")
        if self.page_size > MAXIMUM_PAGE_SIZE:
            raise ValueError("page_size must not exceed 200")
        if self.after_case_no is not None:
            require_canonical_text(self.after_case_no, "after_case_no", 50)
        if self.case_no_search is not None:
            require_canonical_text(self.case_no_search, "case_no_search", 50)


@dataclass(frozen=True, slots=True)
class TerminalCompletionComponent:
    code: str
    owner: str
    completed: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class OrderTerminalAggregate:
    case_no: str
    applicable: bool
    fully_closed: bool
    components: tuple[TerminalCompletionComponent, ...]


@dataclass(frozen=True, slots=True)
class OrderTerminalAggregatePage:
    items: tuple[OrderTerminalAggregate, ...]
    next_cursor: str | None


def query_terminal_aggregate_page(
    source: OperationalTimelineQueryPort,
    repository: GovernmentSubsidyOrderProjectionRepository,
    request: TerminalAggregateQuery,
) -> OrderTerminalAggregatePage:
    """Return a bounded terminal page from the same current owner read models."""
    if not isinstance(request, TerminalAggregateQuery):
        raise TypeError("request must be a TerminalAggregateQuery")

    timeline_items, next_cursor = _query_normal_timeline_items(source, request)
    subsidy_page = query_government_subsidy_projection_page(
        source,
        repository,
        GovernmentSubsidyProjectionQuery(
            page_size=request.page_size,
            after_case_no=request.after_case_no,
            case_no_search=request.case_no_search,
        ),
    )
    timeline_keys = tuple(item.case_no.casefold() for item in timeline_items)
    subsidy_keys = tuple(item.case_no.casefold() for item in subsidy_page.items)
    if timeline_keys != subsidy_keys or next_cursor != subsidy_page.next_cursor:
        raise TerminalAggregateContractError(
            "terminal aggregate source pages do not identify the same normal orders"
        )
    return OrderTerminalAggregatePage(
        items=tuple(
            project_terminal_aggregate(timeline, subsidy)
            for timeline, subsidy in zip(timeline_items, subsidy_page.items, strict=True)
        ),
        next_cursor=next_cursor,
    )


def project_terminal_aggregate(
    timeline: OrderOperationalTimeline,
    subsidy: OrderGovernmentSubsidyProjection,
) -> OrderTerminalAggregate:
    """Return terminal state without redefining any owner completion rule."""
    if not isinstance(timeline, OrderOperationalTimeline):
        raise TypeError("timeline must be an OrderOperationalTimeline")
    if not isinstance(subsidy, OrderGovernmentSubsidyProjection):
        raise TypeError("subsidy must be an OrderGovernmentSubsidyProjection")
    if timeline.case_no.casefold() != subsidy.case_no.casefold():
        raise TerminalAggregateContractError("terminal aggregate case identity does not match")

    if timeline.lifecycle_status in _NON_NORMAL_LIFECYCLE_STATUSES:
        return OrderTerminalAggregate(
            case_no=timeline.case_no,
            applicable=False,
            fully_closed=False,
            components=(),
        )

    if len(timeline.sop_steps) != 11 or len(timeline.stages) != 7:
        raise TerminalAggregateContractError("operational timeline shape is not canonical")
    first_ten = timeline.sop_steps[:10]
    if tuple(step.ordinal for step in first_ten) != tuple(range(1, 11)):
        raise TerminalAggregateContractError("terminal SOP step ordinals are not canonical")

    settlement_stage = _settlement_stage(timeline.stages)
    components = (
        *(_step_component(step) for step in first_ten),
        *(
            _settlement_component(settlement_stage, code)
            for code in _SETTLEMENT_COMPONENT_CODES
        ),
        _subsidy_component(subsidy),
    )
    return OrderTerminalAggregate(
        case_no=timeline.case_no,
        applicable=True,
        fully_closed=all(component.completed for component in components),
        components=components,
    )


def _query_normal_timeline_items(
    source: OperationalTimelineQueryPort,
    request: TerminalAggregateQuery,
) -> tuple[tuple[OrderOperationalTimeline, ...], str | None]:
    selected: list[OrderOperationalTimeline] = []
    has_more = False
    source_cursor: str | None = None
    last_source_key: str | None = None
    requested_cursor_key = request.after_case_no.casefold() if request.after_case_no else None

    while True:
        page = source.query(
            StageProjectionQuery(
                page_size=MAXIMUM_PAGE_SIZE,
                after_case_no=source_cursor,
                lifecycle_scope=OrderLifecycleScope.ALL,
            )
        )
        _validate_source_page(page, source_cursor)
        for item in page.items:
            identity_key = item.case_no.casefold()
            if last_source_key is not None and identity_key <= last_source_key:
                raise TerminalAggregateContractError("source pages are duplicate or unordered")
            last_source_key = identity_key
            if item.lifecycle_status in _NON_NORMAL_LIFECYCLE_STATUSES:
                continue
            if (
                request.case_no_search is not None
                and request.case_no_search.casefold() not in identity_key
            ):
                continue
            if requested_cursor_key is not None and identity_key <= requested_cursor_key:
                continue
            if len(selected) < request.page_size:
                selected.append(item)
            else:
                has_more = True
        if page.next_cursor is None:
            break
        source_cursor = page.next_cursor

    items = tuple(selected)
    next_cursor = items[-1].case_no if has_more and items else None
    return items, next_cursor


def _validate_source_page(page: object, previous_cursor: str | None) -> None:
    if not isinstance(page, OrderOperationalTimelinePage):
        raise TerminalAggregateContractError(
            "source query did not return an operational timeline page"
        )
    if len(page.items) > MAXIMUM_PAGE_SIZE:
        raise TerminalAggregateContractError("source page is not bounded")
    if page.next_cursor is None:
        return
    if not page.items or page.next_cursor.casefold() != page.items[-1].case_no.casefold():
        raise TerminalAggregateContractError("source page cursor is invalid")
    if (
        previous_cursor is not None
        and page.next_cursor.casefold() <= previous_cursor.casefold()
    ):
        raise TerminalAggregateContractError("source page cursor did not advance")


def _step_component(step: SopStepProjection) -> TerminalCompletionComponent:
    completed = step.status == "completed"
    return TerminalCompletionComponent(
        code=step.code,
        owner=step.owner,
        completed=completed,
        reason=None if completed else _step_incomplete_reason(step),
    )


def _step_incomplete_reason(step: SopStepProjection) -> str:
    if step.availability_reason is not None:
        return step.availability_reason
    if step.blockers:
        return step.blockers[0].code
    return f"{step.code}_{step.status}"


def _settlement_stage(stages: tuple[StageProjection, ...]) -> StageProjection:
    matches = tuple(stage for stage in stages if stage.code == "settlement_payout")
    if len(matches) != 1:
        raise TerminalAggregateContractError("settlement_payout source stage is not canonical")
    parts = matches[0].settlement
    if len(parts) != 3 or {part.code for part in parts} != set(_SETTLEMENT_COMPONENT_CODES):
        raise TerminalAggregateContractError("settlement owner components are not canonical")
    return matches[0]


def _settlement_component(
    stage: StageProjection,
    code: str,
) -> TerminalCompletionComponent:
    part = next(item for item in stage.settlement if item.code == code)
    completed = part.status == "completed"
    return TerminalCompletionComponent(
        code=part.code,
        owner=part.source.owner,
        completed=completed,
        reason=None if completed else _settlement_incomplete_reason(stage, part),
    )


def _settlement_incomplete_reason(
    stage: StageProjection,
    part: SettlementProjection,
) -> str:
    if part.availability_reason is not None:
        return part.availability_reason
    blocker = next(
        (notice for notice in stage.blockers if notice.code.startswith(f"{part.code}_")),
        None,
    )
    if blocker is not None:
        return blocker.code
    return f"{part.code}_{part.status}"


def _subsidy_component(
    subsidy: OrderGovernmentSubsidyProjection,
) -> TerminalCompletionComponent:
    completed = subsidy.substatus_code in _TERMINAL_SUBSIDY_SUBSTATUSES
    reason = None
    if not completed:
        reason = subsidy.blockers[0].code if subsidy.blockers else subsidy.substatus_code
    return TerminalCompletionComponent(
        code="government_subsidy",
        owner=subsidy.source.owner,
        completed=completed,
        reason=reason,
    )


__all__ = [
    "OrderTerminalAggregate",
    "OrderTerminalAggregatePage",
    "TerminalAggregateContractError",
    "TerminalAggregateQuery",
    "TerminalCompletionComponent",
    "project_terminal_aggregate",
    "query_terminal_aggregate_page",
]
