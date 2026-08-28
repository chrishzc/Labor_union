"""
File: alert_workflow.py
Description: 編排 current anomaly 查詢、owner 處理動作、投影與人工工作流。
"""

from dataclasses import dataclass, replace
from typing import Mapping

from domains.anomalies.recovery_context import bind_recovery_actions
from domains.anomalies.registry import (
    AlertWorkflowStatus,
    AnomalySeverity,
    auto_resolution_blocked,
    claim_alert,
    reduce_current_alert,
    resolve_alert_workflow,
)
from shared_kernel.validation import require_canonical_text, require_positive_integer


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
    display_fields: tuple[str, ...] = ()


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
        summary = self._enrich_summary(detail.summary)
        return AnomalyDetail(
            summary,
            detail.timeline,
            _detail_actions(
                self._registry.available_actions(summary.projection.definition_code),
                summary,
            ),
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
            display_fields=definition.display_fields,
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
            display_snapshot = request.display_snapshot
            if previous is not None and auto_resolution_blocked(
                self._registry,
                previous,
                request.desired,
            ):
                display_snapshot = loaded[1]
            resulting = reduce_current_alert(self._registry, request.desired, previous)
            self._repository.save_projection(
                definition,
                previous,
                resulting,
                display_snapshot,
            )
            self._repository.append_projector_event(previous, resulting, request)
            self._repository.save_checkpoint(request)
            unit_of_work.commit()
        return resulting

    def claim(self, request):
        return self._change(request, "claim")

    def resolve(self, request):
        del request
        raise ValueError("anomaly_manual_resolve_forbidden")

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


_CLIENT_SETTLEMENT_REMINDER_CODES = frozenset(
    {"RECEIVABLE-001", "CLIENTPAYABLE-001", "RETURN-001"}
)
_FINANCE_RECOVERY_CODES = frozenset(
    {
        "GOVSUB-006",
        "client_over_refund_recovery_open",
        "staff_overpayment_recovery_open",
    }
)
_PAYOUT_OVERDUE_CODE = "PAYOUT-001"
_PAYOUT_OVERDUE_ACTION = "reconcile_overdue_staff_payable"


def _detail_actions(descriptors, summary) -> tuple[object, ...]:
    """依 owning Domain snapshot fail-closed 綁定 current-alert 處理動作。"""
    if summary.projection.definition_code == _PAYOUT_OVERDUE_CODE:
        return _bind_payout_overdue_action(descriptors, summary)
    if summary.projection.definition_code in _FINANCE_RECOVERY_CODES:
        snapshot = summary.display_snapshot
        if not isinstance(snapshot, Mapping):
            return ()
        return bind_recovery_actions(descriptors, snapshot)
    if summary.projection.definition_code not in _CLIENT_SETTLEMENT_REMINDER_CODES:
        return descriptors
    snapshot = summary.display_snapshot
    if not isinstance(snapshot, Mapping):
        return ()
    case_no = snapshot.get("case_no")
    account_version = snapshot.get("account_version")
    if (
        not isinstance(case_no, str)
        or not case_no.strip()
        or case_no != summary.projection.source_identity
        or isinstance(account_version, bool)
        or not isinstance(account_version, int)
        or account_version < 0
    ):
        return ()
    bindings = {"account_version": account_version, "case_no": case_no}
    return tuple(replace(descriptor, source_bindings=bindings) for descriptor in descriptors)


def _bind_payout_overdue_action(descriptors, summary) -> tuple[object, ...]:
    """只以同一 current snapshot 綁定 PAYOUT-001 的兩個 owner identities。"""
    if summary.source_domain != "staff_payables":
        return ()
    snapshot = summary.display_snapshot
    if not isinstance(snapshot, Mapping):
        return ()
    obligation_identity = snapshot.get("obligation_identity")
    staff_id = snapshot.get("staff_id")
    try:
        obligation_identity = require_canonical_text(
            obligation_identity, "obligation identity", 191
        )
        require_canonical_text(summary.projection.source_identity, "source identity", 191)
        staff_id = require_positive_integer(staff_id, "staff id")
    except (TypeError, ValueError):
        return ()
    if obligation_identity != summary.projection.source_identity:
        return ()
    bound: list[object] = []
    for descriptor in descriptors:
        if (
            descriptor.action_key != _PAYOUT_OVERDUE_ACTION
            or descriptor.owning_domain != "staff_payables"
            or descriptor.source_binding_keys != ("obligation_identity", "staff_id")
        ):
            continue
        bound.append(
            replace(
                descriptor,
                source_bindings={
                    "obligation_identity": obligation_identity,
                    "staff_id": staff_id,
                },
            )
        )
    return tuple(bound)
