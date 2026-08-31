"""LINE-owned typed current facts for the LINE-006 notification predicate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from domains.anomalies.current_issue import (
    RecheckIntent,
    RecheckScope,
    build_owner_lock_key,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN = "line"
LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE = "notification_failure"


class LineNotificationFailureReason(str, Enum):
    RECIPIENT_UNAVAILABLE = "recipient_unavailable"
    TEMPLATE_OR_SCHEDULE_INVALID = "template_or_schedule_invalid"


class LineNotificationUnresolvedReason(str, Enum):
    EXACT_REPLAY_SUCCESSOR_MISSING = "exact_replay_successor_missing"
    REPLAY_IN_PROGRESS = "replay_in_progress"
    REPLAY_TERMINAL_FAILED = "replay_terminal_failed"
    DELIVERY_OUTCOME_UNKNOWN = "delivery_outcome_unknown"
    REPLAY_LINEAGE_AMBIGUOUS = "replay_lineage_ambiguous"
    FRESH_VALIDATION_FAILED = "fresh_validation_failed"
    OWNER_READBACK_INCOMPLETE = "owner_readback_incomplete"


@dataclass(frozen=True, slots=True)
class LineNotificationFailureCurrentFactQuery:
    case_no: str
    notification_reason: LineNotificationFailureReason

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 191)
        if not isinstance(self.notification_reason, LineNotificationFailureReason):
            raise TypeError("LINE notification failure reason is invalid")


@dataclass(frozen=True, slots=True)
class LineNotificationReplaySuccessorFact:
    source_event_id: int
    exact_lineage: bool
    fresh_validation_valid: bool | None
    delivery_statuses: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.source_event_id <= 0:
            raise ValueError("LINE replay source event ID is invalid")
        if not isinstance(self.exact_lineage, bool):
            raise TypeError("LINE replay lineage state is invalid")
        if self.fresh_validation_valid not in {True, False, None}:
            raise TypeError("LINE replay validation state is invalid")
        if not isinstance(self.delivery_statuses, tuple):
            raise TypeError("LINE replay delivery statuses must be a tuple")


@dataclass(frozen=True, slots=True)
class LineNotificationFailedSourceFact:
    source_event_id: int
    currently_applicable: bool
    applicability_complete: bool
    replay_successors: tuple[LineNotificationReplaySuccessorFact, ...]

    def __post_init__(self) -> None:
        if self.source_event_id <= 0:
            raise ValueError("LINE failed source event ID is invalid")
        if not isinstance(self.currently_applicable, bool):
            raise TypeError("LINE source applicability is invalid")
        if not isinstance(self.applicability_complete, bool):
            raise TypeError("LINE source applicability completeness is invalid")
        if not isinstance(self.replay_successors, tuple):
            raise TypeError("LINE replay successors must be a tuple")


@dataclass(frozen=True, slots=True)
class LineNotificationFailureCurrentFactReadback:
    case_no: str
    notification_reason: LineNotificationFailureReason
    owner_snapshot_token: str
    owner_version: int
    authoritative_complete: bool
    applicable_source_count: int
    unresolved_source_count: int
    unresolved_reason_codes: tuple[LineNotificationUnresolvedReason, ...]
    predicate_active: bool

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 191)
        if not isinstance(self.notification_reason, LineNotificationFailureReason):
            raise TypeError("LINE notification failure reason is invalid")
        require_canonical_text(self.owner_snapshot_token, "owner snapshot token", 191)
        require_nonnegative_integer(self.owner_version, "owner version")
        require_nonnegative_integer(self.applicable_source_count, "applicable source count")
        require_nonnegative_integer(self.unresolved_source_count, "unresolved source count")
        if not isinstance(self.authoritative_complete, bool):
            raise TypeError("LINE current-fact completeness is invalid")
        if not isinstance(self.predicate_active, bool):
            raise TypeError("LINE current-fact predicate is invalid")
        if tuple(sorted(set(self.unresolved_reason_codes), key=lambda item: item.value)) != self.unresolved_reason_codes:
            raise ValueError("LINE unresolved reason codes must be sorted and unique")


@dataclass(frozen=True, slots=True)
class LineNotificationFailureRecheckTarget:
    case_no: str
    notification_reason: LineNotificationFailureReason


def evaluate_line_notification_failure_current_fact(
    query: LineNotificationFailureCurrentFactQuery,
    sources: tuple[LineNotificationFailedSourceFact, ...],
    *,
    owner_version: int,
    authoritative_complete: bool,
) -> LineNotificationFailureCurrentFactReadback:
    """Evaluate one logical case/reason group without persisting an aggregate."""

    applicable = tuple(source for source in sources if source.currently_applicable)
    complete = authoritative_complete and all(
        source.applicability_complete for source in sources
    )
    unresolved: list[LineNotificationUnresolvedReason] = []
    unresolved_count = 0
    for source in applicable:
        reason = _unresolved_reason(source)
        if reason is not None:
            unresolved_count += 1
            unresolved.append(reason)
    if not complete:
        unresolved.append(LineNotificationUnresolvedReason.OWNER_READBACK_INCOMPLETE)
    reasons = tuple(sorted(set(unresolved), key=lambda item: item.value))
    # Temporary readback incompleteness is operational health, not a new
    # business issue. Existing rows remain fail-closed through the authoritative
    # snapshot gate in the current-issue repository.
    predicate_active = unresolved_count > 0
    payload = {
        "case_no": query.case_no,
        "notification_reason": query.notification_reason.value,
        "owner_version": owner_version,
        "authoritative_complete": complete,
        "applicable_source_count": len(applicable),
        "unresolved_source_count": unresolved_count,
        "unresolved_reason_codes": [item.value for item in reasons],
        "predicate_active": predicate_active,
        "source_state": [
            {
                "source_event_id": source.source_event_id,
                "currently_applicable": source.currently_applicable,
                "applicability_complete": source.applicability_complete,
                "replay_successors": [
                    {
                        "source_event_id": replay.source_event_id,
                        "exact_lineage": replay.exact_lineage,
                        "fresh_validation_valid": replay.fresh_validation_valid,
                        "delivery_statuses": list(replay.delivery_statuses),
                    }
                    for replay in source.replay_successors
                ],
            }
            for source in sources
        ],
    }
    return LineNotificationFailureCurrentFactReadback(
        case_no=query.case_no,
        notification_reason=query.notification_reason,
        owner_snapshot_token=fingerprint_payload(payload).value,
        owner_version=owner_version,
        authoritative_complete=complete,
        applicable_source_count=len(applicable),
        unresolved_source_count=unresolved_count,
        unresolved_reason_codes=reasons,
        predicate_active=predicate_active,
    )


def build_line_notification_failure_recheck_intent(
    readback: LineNotificationFailureCurrentFactReadback,
    *,
    cause_identity: str,
) -> RecheckIntent:
    """Build the existing bounded anomaly.recheck contract for one LINE group."""

    require_canonical_text(cause_identity, "LINE recheck cause identity", 191)
    scope = RecheckScope(
        LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN,
        LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE,
        readback.notification_reason.value,
        (readback.case_no,),
        (
            build_owner_lock_key(
                LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN,
                LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE,
                f"{readback.case_no}:{readback.notification_reason.value}",
            ),
        ),
    )
    payload_fingerprint = fingerprint_payload(
        {
            "cause_identity": cause_identity,
            "scope": {
                "owner_domain": scope.owner_domain,
                "owner_root_type": scope.owner_root_type,
                "subject_type": scope.subject_type,
                "subject_ids": list(scope.subject_ids),
                "owner_lock_keys": list(scope.owner_lock_keys),
            },
            "owner_version": readback.owner_version,
        }
    )
    return RecheckIntent(
        "line006-recheck:" + payload_fingerprint.value[:48],
        scope,
        readback.owner_version,
        payload_fingerprint,
    )


def append_line_notification_failure_rechecks(
    unit_of_work: object,
    targets: tuple[LineNotificationFailureRecheckTarget, ...],
    *,
    cause_identity: str,
) -> None:
    """Append only LINE-006 intents, inside the caller's existing outer UoW."""

    if not targets:
        return
    notification_rules = getattr(unit_of_work, "notification_rules")
    anomaly_rechecks = getattr(unit_of_work, "anomaly_rechecks")
    for target in targets:
        readback = notification_rules.current_failure_fact(
            LineNotificationFailureCurrentFactQuery(
                target.case_no, target.notification_reason
            )
        )
        anomaly_rechecks.append_recheck_intent(
            build_line_notification_failure_recheck_intent(
                readback, cause_identity=cause_identity
            )
        )


def _unresolved_reason(
    source: LineNotificationFailedSourceFact,
) -> LineNotificationUnresolvedReason | None:
    if not source.replay_successors:
        return LineNotificationUnresolvedReason.EXACT_REPLAY_SUCCESSOR_MISSING
    latest = max(source.replay_successors, key=lambda item: item.source_event_id)
    if not latest.exact_lineage:
        return LineNotificationUnresolvedReason.REPLAY_LINEAGE_AMBIGUOUS
    if latest.fresh_validation_valid is not True:
        return LineNotificationUnresolvedReason.FRESH_VALIDATION_FAILED
    statuses = latest.delivery_statuses
    if not statuses or any(status in {"cancelled", "unknown"} for status in statuses):
        return LineNotificationUnresolvedReason.DELIVERY_OUTCOME_UNKNOWN
    if any(status == "failed" for status in statuses):
        return LineNotificationUnresolvedReason.REPLAY_TERMINAL_FAILED
    if any(status in {"pending", "processing", "retryable_failed"} for status in statuses):
        return None
    if all(status == "sent" for status in statuses):
        return None
    return LineNotificationUnresolvedReason.DELIVERY_OUTCOME_UNKNOWN


__all__ = [
    "LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN",
    "LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE",
    "LineNotificationFailedSourceFact",
    "LineNotificationFailureCurrentFactQuery",
    "LineNotificationFailureCurrentFactReadback",
    "LineNotificationFailureReason",
    "LineNotificationFailureRecheckTarget",
    "LineNotificationReplaySuccessorFact",
    "LineNotificationUnresolvedReason",
    "append_line_notification_failure_rechecks",
    "build_line_notification_failure_recheck_intent",
    "evaluate_line_notification_failure_current_fact",
]
