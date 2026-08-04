"""Canonical current-state anomaly query and workflow orchestration."""

from dataclasses import dataclass

from domains.anomalies.registry import (
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
    severity: str
    display_snapshot: object


@dataclass(frozen=True, slots=True)
class AnomalyDetail:
    summary: AnomalySummary
    timeline: tuple[object, ...]
    available_actions: tuple[object, ...]


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
        return self._repository.query_summaries(active_only=active_only, limit=limit, offset=offset)

    def query_detail(self, fingerprint):
        detail = self._repository.query_detail(fingerprint)
        if detail is None:
            raise ValueError("anomaly_not_found")
        return AnomalyDetail(
            detail.summary,
            detail.timeline,
            self._registry.available_actions(detail.summary.projection.definition_code),
        )

    def project(self, request):
        definition = self._registry.require(request.desired.definition_code)
        fingerprint = self._registry.fingerprint(request.desired)
        with self._unit_of_work_factory() as unit_of_work:
            if self._repository.checkpoint_matches(request):
                current = self._repository.load_current(fingerprint, for_update=True)
                return None if current is None else current[0]
            loaded = self._repository.load_current(fingerprint, for_update=True)
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
    return type("AnomalyWorkflowReceipt", (), {"fingerprint": projection.fingerprint, "action": action, "resulting_workflow_version": projection.workflow_version, "workflow_status": projection.workflow_status})()
