"""Build the read-only terminal aggregate for Order Workbench Beta."""

from __future__ import annotations

from dataclasses import dataclass

from subsystems.orders.core_stage_projection_query import (
    CoreStageProjection,
    OrderCoreStageTimeline,
)
from subsystems.orders.government_subsidy_projection_query import (
    OrderGovernmentSubsidyProjection,
)


_TERMINAL_SUBSIDY_SUBSTATUSES = frozenset({"paid", "offset_applied", "returned"})


class TerminalAggregateContractError(ValueError):
    """The terminal aggregate inputs do not describe the same order."""


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


def project_terminal_aggregate(
    timeline: OrderCoreStageTimeline,
    subsidy: OrderGovernmentSubsidyProjection,
) -> OrderTerminalAggregate:
    """Return a terminal aggregate without redefining any owner business rule."""
    if not isinstance(timeline, OrderCoreStageTimeline):
        raise TypeError("timeline must be an OrderCoreStageTimeline")
    if not isinstance(subsidy, OrderGovernmentSubsidyProjection):
        raise TypeError("subsidy must be an OrderGovernmentSubsidyProjection")
    if timeline.case_no.casefold() != subsidy.case_no.casefold():
        raise TerminalAggregateContractError("terminal aggregate case identity does not match")

    if timeline.branch_type != "normal":
        return OrderTerminalAggregate(
            case_no=timeline.case_no,
            applicable=False,
            fully_closed=False,
            components=(),
        )

    components = tuple(_core_component(stage) for stage in timeline.core_stages) + (
        _subsidy_component(subsidy),
    )
    return OrderTerminalAggregate(
        case_no=timeline.case_no,
        applicable=True,
        fully_closed=all(component.completed for component in components),
        components=components,
    )


def _core_component(stage: CoreStageProjection) -> TerminalCompletionComponent:
    completed = stage.status == "completed"
    reason = None if completed else _core_incomplete_reason(stage)
    return TerminalCompletionComponent(
        code=stage.code,
        owner=stage.owner,
        completed=completed,
        reason=reason,
    )


def _core_incomplete_reason(stage: CoreStageProjection) -> str:
    if stage.availability_reason is not None:
        return stage.availability_reason
    if stage.blockers:
        return stage.blockers[0].code
    return stage.substatus_code


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
    "TerminalAggregateContractError",
    "TerminalCompletionComponent",
    "project_terminal_aggregate",
]
