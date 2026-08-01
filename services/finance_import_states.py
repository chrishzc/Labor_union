"""Canonical state contract for the finance import workflow.

The five workflow axes are intentionally independent.  In particular, an
occurrence outcome never changes the canonical classification or
reconciliation state of an imported row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


BATCH_STATUSES = frozenset({"staged", "completed", "failed"})
OCCURRENCE_OUTCOMES = frozenset({"inserted", "skipped_existing"})
CLASSIFICATION_TYPES = frozenset(
    {
        "pending",
        "client_receipt",
        "government_subsidy",
        "client_subsidy_return",
        "staff_salary",
        "staff_legacy_subsidy",
        "non_business_review",
    }
)
BUSINESS_CLASSIFICATION_TYPES = CLASSIFICATION_TYPES - {
    "pending",
    "non_business_review",
}
RECONCILIATION_STATUSES = frozenset({"pending", "reconciled"})
ALERT_STATUSES = frozenset({"open", "claimed", "resolved"})
TRANSITION_EVENTS = frozenset(
    {
        "stage",
        "classify",
        "reclassify",
        "reconcile",
        "duplicate_occurrence",
        "claim",
        "resolve",
        "reopen",
    }
)

INVALID_AXES = "invalid_axes"
UNKNOWN_TRANSITION_EVENT = "unknown_transition_event"
TARGET_REQUIRED = "target_required"
INVALID_TARGET = "invalid_target"
ILLEGAL_TRANSITION = "illegal_transition"


@dataclass(frozen=True, slots=True)
class FinanceImportAxes:
    """The four persisted canonical row/batch/alert axes.

    ``occurrence_outcome`` is deliberately absent because it describes one
    import attempt rather than canonical row state.
    """

    batch_status: str
    classification_type: str
    reconciliation_status: str
    alert_status: str


@dataclass(frozen=True, slots=True)
class FinanceImportTransitionDecision:
    """Deterministic result of evaluating one finance import transition."""

    allowed: bool
    validated_axes: FinanceImportAxes | None
    occurrence_outcome: str | None = None
    refusal_reason: str | None = None


def _coerce_axes(
    current_axes: FinanceImportAxes | Mapping[str, object],
) -> FinanceImportAxes | None:
    if isinstance(current_axes, FinanceImportAxes):
        axes = current_axes
    elif isinstance(current_axes, Mapping):
        required = {
            "batch_status",
            "classification_type",
            "reconciliation_status",
            "alert_status",
        }
        if set(current_axes) != required:
            return None
        if not all(isinstance(current_axes[key], str) for key in required):
            return None
        axes = FinanceImportAxes(
            batch_status=current_axes["batch_status"],
            classification_type=current_axes["classification_type"],
            reconciliation_status=current_axes["reconciliation_status"],
            alert_status=current_axes["alert_status"],
        )
    else:
        return None

    if (
        axes.batch_status not in BATCH_STATUSES
        or axes.classification_type not in CLASSIFICATION_TYPES
        or axes.reconciliation_status not in RECONCILIATION_STATUSES
        or axes.alert_status not in ALERT_STATUSES
    ):
        return None
    return axes


def _allowed(axes: FinanceImportAxes, **changes: str) -> FinanceImportTransitionDecision:
    values = {
        "batch_status": axes.batch_status,
        "classification_type": axes.classification_type,
        "reconciliation_status": axes.reconciliation_status,
        "alert_status": axes.alert_status,
    }
    values.update(changes)
    return FinanceImportTransitionDecision(
        allowed=True,
        validated_axes=FinanceImportAxes(**values),
    )


def _refused(
    reason: str,
    axes: FinanceImportAxes | None,
) -> FinanceImportTransitionDecision:
    return FinanceImportTransitionDecision(
        allowed=False,
        validated_axes=axes,
        refusal_reason=reason,
    )


def evaluate_finance_import_transition(
    current_axes: FinanceImportAxes | Mapping[str, object],
    transition_event: str,
    target_value: str | None = None,
) -> FinanceImportTransitionDecision:
    """Validate and evaluate one IMP-01 transition without side effects.

    ``target_value`` is required only for ``stage``, ``classify`` and
    ``reclassify``.  All other events have one canonical destination.
    """

    axes = _coerce_axes(current_axes)
    if axes is None:
        return _refused(INVALID_AXES, None)
    if transition_event not in TRANSITION_EVENTS:
        return _refused(UNKNOWN_TRANSITION_EVENT, axes)

    if transition_event == "duplicate_occurrence":
        if target_value not in (None, "skipped_existing"):
            return _refused(INVALID_TARGET, axes)
        return FinanceImportTransitionDecision(
            allowed=True,
            validated_axes=axes,
            occurrence_outcome="skipped_existing",
        )

    if transition_event == "stage":
        if target_value is None:
            return _refused(TARGET_REQUIRED, axes)
        if target_value not in BATCH_STATUSES - {"staged"}:
            return _refused(INVALID_TARGET, axes)
        if axes.batch_status != "staged":
            return _refused(ILLEGAL_TRANSITION, axes)
        return _allowed(axes, batch_status=target_value)

    if transition_event == "classify":
        if target_value is None:
            return _refused(TARGET_REQUIRED, axes)
        if target_value not in CLASSIFICATION_TYPES - {"pending"}:
            return _refused(INVALID_TARGET, axes)
        if axes.classification_type != "pending":
            return _refused(ILLEGAL_TRANSITION, axes)
        return _allowed(axes, classification_type=target_value)

    if transition_event == "reclassify":
        if target_value is None:
            return _refused(TARGET_REQUIRED, axes)
        if target_value not in CLASSIFICATION_TYPES - {"pending"}:
            return _refused(INVALID_TARGET, axes)
        current = axes.classification_type
        unchanged = target_value == current
        review_to_business = (
            current == "non_business_review"
            and target_value in BUSINESS_CLASSIFICATION_TYPES
        )
        if not (unchanged or review_to_business):
            return _refused(ILLEGAL_TRANSITION, axes)
        return _allowed(axes, classification_type=target_value)

    if target_value is not None:
        return _refused(INVALID_TARGET, axes)

    if transition_event == "reconcile":
        if axes.reconciliation_status != "pending":
            return _refused(ILLEGAL_TRANSITION, axes)
        return _allowed(axes, reconciliation_status="reconciled")

    alert_transitions = {
        "claim": ("open", "claimed"),
        "resolve": ("claimed", "resolved"),
        "reopen": ("resolved", "open"),
    }
    expected_current, destination = alert_transitions[transition_event]
    if axes.alert_status != expected_current:
        return _refused(ILLEGAL_TRANSITION, axes)
    return _allowed(axes, alert_status=destination)
