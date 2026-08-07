"""Canonical GOVSUB-003 projection from Government Subsidy root facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domains.anomalies.registry import CurrentAlertProjection, DesiredAlertState
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest


_CONSUMER_IDENTITY = "govsub-integrity-v1"
_MAXIMUM_SCAN_SIZE = 100
_TEXT_MAXIMUM_LENGTH = 191


@dataclass(frozen=True)
class GovernmentSubsidyIntegrityRootFact:
    batch_id: int
    integrity_revision: int
    integrity_blockers: tuple[str, ...]
    previous_integrity_revisions: tuple[int, ...]
    source_version: int
    source_event_identity: str

    def __post_init__(self) -> None:
        require_positive_integer(self.batch_id, "claim batch id")
        require_positive_integer(self.integrity_revision, "integrity revision")
        _validate_blockers(self.integrity_blockers)
        _validate_revisions(self.previous_integrity_revisions)
        require_nonnegative_integer(self.source_version, "source version")
        require_canonical_text(self.source_event_identity, "source event identity", _TEXT_MAXIMUM_LENGTH)


@dataclass(frozen=True)
class GovernmentSubsidyIntegrityScanRequest:
    limit: int
    after_batch_id: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise TypeError("scan limit must be an integer")
        if not 1 <= self.limit <= _MAXIMUM_SCAN_SIZE:
            raise ValueError("scan limit must be between 1 and 100")
        require_nonnegative_integer(self.after_batch_id, "batch scan cursor")


@dataclass(frozen=True)
class GovernmentSubsidyIntegrityScanPage:
    facts: tuple[GovernmentSubsidyIntegrityRootFact, ...]
    next_batch_id: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.facts, tuple):
            raise TypeError("scan facts must be a tuple")
        if any(not isinstance(fact, GovernmentSubsidyIntegrityRootFact) for fact in self.facts):
            raise TypeError("scan facts contain an invalid root fact")
        if self.next_batch_id is not None:
            require_positive_integer(self.next_batch_id, "next batch cursor")


@dataclass(frozen=True)
class GovernmentSubsidyIntegrityScanResult:
    projections: tuple[CurrentAlertProjection | None, ...]
    next_batch_id: int | None


class GovernmentSubsidyIntegrityRootFactSource(Protocol):
    def load_page(self, request: GovernmentSubsidyIntegrityScanRequest) -> GovernmentSubsidyIntegrityScanPage: ...


class GovernmentSubsidyIntegrityAnomalyConsumer:
    def __init__(self, source: GovernmentSubsidyIntegrityRootFactSource, anomaly_application: AnomalyApplication) -> None:
        self._source = source
        self._anomaly_application = anomaly_application

    def scan_page(self, request: GovernmentSubsidyIntegrityScanRequest) -> GovernmentSubsidyIntegrityScanResult:
        page = self._source.load_page(request)
        if len(page.facts) > request.limit:
            raise ValueError("root-fact source exceeded the bounded scan limit")
        projections = tuple(
            self._anomaly_application.project(alert_request)
            for fact in page.facts
            for alert_request in build_integrity_alert_requests(fact)
        )
        return GovernmentSubsidyIntegrityScanResult(projections, page.next_batch_id)


def build_integrity_alert_requests(root_fact: GovernmentSubsidyIntegrityRootFact) -> tuple[ProjectAlertRequest, ...]:
    revisions = set(root_fact.previous_integrity_revisions)
    revisions.add(root_fact.integrity_revision)
    return tuple(
        _project_request(
            root_fact,
            revision,
            revision == root_fact.integrity_revision and bool(root_fact.integrity_blockers),
        )
        for revision in sorted(revisions)
    )


def _project_request(root_fact, target_revision, active):
    source_identity = f"government-subsidy-batch:{root_fact.batch_id}"
    snapshot = {
        "batch_id": root_fact.batch_id,
        "integrity_blockers": root_fact.integrity_blockers if active else (),
        "integrity_revision": target_revision,
    }
    desired = DesiredAlertState(
        "GOVSUB-003", source_identity, root_fact.source_version, active,
        {"batch_id": str(root_fact.batch_id), "integrity_revision": str(target_revision)},
    )
    return ProjectAlertRequest(
        desired,
        _projector_event_identity(root_fact, target_revision, active, snapshot),
        _CONSUMER_IDENTITY,
        f"gsi:{root_fact.batch_id}:{target_revision}",
        snapshot,
    )


def _projector_event_identity(root_fact, target_revision, active, snapshot):
    digest = fingerprint_payload({"active": active, "current_root_event": root_fact.source_event_identity, "snapshot": snapshot, "target_revision": target_revision}).value
    return f"government-subsidy-integrity:{digest}"


def _validate_blockers(blockers) -> None:
    if not isinstance(blockers, tuple):
        raise TypeError("integrity blockers must be a tuple")
    if blockers != tuple(sorted(set(blockers))):
        raise ValueError("integrity blockers must be sorted and unique")
    for blocker in blockers:
        require_canonical_text(blocker, "integrity blocker", _TEXT_MAXIMUM_LENGTH)


def _validate_revisions(revisions) -> None:
    if not isinstance(revisions, tuple):
        raise TypeError("previous integrity revisions must be a tuple")
    if revisions != tuple(sorted(set(revisions))):
        raise ValueError("previous integrity revisions must be sorted and unique")
    for revision in revisions:
        require_positive_integer(revision, "integrity revision")


__all__ = [
    "GovernmentSubsidyIntegrityAnomalyConsumer", "GovernmentSubsidyIntegrityRootFact",
    "GovernmentSubsidyIntegrityRootFactSource", "GovernmentSubsidyIntegrityScanPage",
    "GovernmentSubsidyIntegrityScanRequest", "GovernmentSubsidyIntegrityScanResult",
    "build_integrity_alert_requests",
]
