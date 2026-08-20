"""
File: alert_workflow.py
Description: 編排 canonical current-state anomaly 查詢、投影與人工工作流。
"""

from dataclasses import dataclass, replace

from domains.anomalies.registry import (
    AlertWorkflowStatus,
    AnomalySeverity,
    claim_alert,
    reduce_current_alert,
    resolve_alert_workflow,
)


@dataclass(frozen=True, slots=True)
class StoredWorkflowEvent:
    fingerprint: object
    action: str
    expected_workflow_version: int
    resulting_workflow_version: int
    workflow_status: object
    actor: str
    reason: str


@dataclass(frozen=True, slots=True)
class AnomalySummary:
    projection: object
    source_domain: str
    severity: AnomalySeverity
    display_snapshot: object


@dataclass(frozen=True, slots=True)
class AnomalyDetail:
    summary: AnomalySummary
    timeline: tuple[object, ...]
    available_actions: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class AnomalyWorkflowReceipt:
    fingerprint: object
    action: str
    resulting_workflow_version: int
    workflow_status: object


@dataclass(frozen=True, slots=True)
class AnomalyWorkflowRequest:
    fingerprint: object
    expected_workflow_version: int
    idempotency_key: object
    actor: object
    reason: str
    correlation_id: object


@dataclass(frozen=True, slots=True)
class ProjectAlertRequest:
    desired: object
    source_event_identity: str
    consumer_identity: str
    partition_identity: str
    display_snapshot: object


class AnomalyWorkflowError(Exception):
    def __init__(self, error):
        super().__init__(error.message)
        self.error = error


class AnomalyApplication:
    def __init__(self, registry, repository, unit_of_work_factory):
        self._registry = registry
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query_summaries(self, *, active_only=True, limit=100, offset=0):
        stored = self._repository.query_summaries(
            active_only=active_only,
            limit=limit,
            offset=offset,
        )
        return tuple(self._enrich_summary(summary) for summary in stored)

    def query_detail(self, fingerprint):
        detail = self._repository.query_detail(fingerprint)
        if detail is None:
            raise ValueError("anomaly_not_found")
        return AnomalyDetail(
            self._enrich_summary(detail.summary),
            detail.timeline,
            self._registry.available_actions(detail.summary.projection.definition_code),
        )

    def _enrich_summary(self, summary: AnomalySummary) -> AnomalySummary:
        definition = self._registry.require(summary.projection.definition_code)
        if summary.source_domain != definition.source_domain:
            raise ValueError("anomaly_projection_data_integrity_violation")
        if not isinstance(summary.projection.workflow_status, AlertWorkflowStatus):
            raise ValueError("anomaly_projection_data_integrity_violation")
        return replace(
            summary,
            source_domain=definition.source_domain,
            severity=definition.severity,
        )

    def project(self, request):
        definition = self._registry.require(request.desired.definition_code)
        fingerprint = self._registry.fingerprint(request.desired)
        with self._unit_of_work_factory() as unit_of_work:
            loaded = self._repository.load_current(fingerprint, for_update=True)
            if self._repository.checkpoint_matches(request) and _projection_matches_desired(
                loaded, request.desired
            ):
                return None if loaded is None else loaded[0]
            previous = None if loaded is None else loaded[0]
            resulting = reduce_current_alert(self._registry, request.desired, previous)
            self._repository.save_projection(
                definition,
                previous,
                resulting,
                request.display_snapshot,
            )
            self._repository.append_projector_event(previous, resulting, request)
            self._repository.save_checkpoint(request)
            unit_of_work.commit()
        return resulting

    def claim(self, request):
        return self._change(request, "claim")

    def resolve(self, request):
        return self._change(request, "resolve")

    def _change(self, request, action):
        with self._unit_of_work_factory() as unit_of_work:
            loaded = self._repository.load_current(request.fingerprint, for_update=True)
            if loaded is None:
                raise ValueError("anomaly_not_found")
            previous = loaded[0]
            resulting = claim_alert(previous, request.expected_workflow_version) if action == "claim" else resolve_alert_workflow(previous, request.expected_workflow_version, request.reason)
            self._repository.save_workflow(previous, resulting, request, action)
            unit_of_work.commit()
        return _receipt(resulting, action)


def _receipt(projection, action):
    return AnomalyWorkflowReceipt(projection.fingerprint, action, projection.workflow_version, projection.workflow_status)


def _projection_matches_desired(loaded, desired) -> bool:
    if loaded is None:
        return not desired.active
    current = loaded[0]
    if current.source_version != desired.source_version:
        return False
    if current.predicate_active != desired.active:
        return False
    if desired.active:
        return str(current.workflow_status) != "resolved"
    return str(current.workflow_status) == "resolved"
