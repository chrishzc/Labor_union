"""Transactional root-fact projection and human recovery queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.anomalies.recovery_context import RecoveryContextFacts, assemble_recovery_action
from domains.anomalies.registry import AnomalyDefinition, AnomalyDefinitionRegistry, CurrentAlertProjection, RecoveryActionDescriptor, reduce_current_alert
from domains.anomalies.root_fact_projection import FinanceAnomalyOccurrence, FinanceManualReviewRootFact, RecoveryActionLink, RecoveryContext, RootFactEventOrigin, build_finance_manual_review_candidate, finance_manual_review_recovery_actions
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion
from shared_kernel.ports import UnitOfWork


@dataclass(frozen=True, slots=True)
class RootFactProjectionReceipt:
    source_event_identity: str
    event_payload_fingerprint: PreviewFingerprint
    alert_fingerprint: PreviewFingerprint
    source_version: int
    predicate_active: bool
    workflow_version: int | None
    occurrence_recorded: bool


@dataclass(frozen=True, slots=True)
class StoredRecoveryProjection:
    projection: CurrentAlertProjection
    root_fact_snapshot: dict[str, object]
    projection_freshness: str
    occurrence_timeline: tuple[FinanceAnomalyOccurrence, ...]
    workflow_timeline: tuple[dict[str, object], ...]


class RootFactProjectionRepository(Protocol):
    def find_receipt(self, source_event_identity: str, *, for_update: bool) -> RootFactProjectionReceipt | None: ...
    def load_current(self, fingerprint: PreviewFingerprint, *, for_update: bool) -> CurrentAlertProjection | None: ...
    def save_current(self, previous: CurrentAlertProjection | None, resulting: CurrentAlertProjection | None, candidate) -> None: ...
    def append_occurrence(self, occurrence: FinanceAnomalyOccurrence) -> None: ...
    def save_receipt(self, receipt: RootFactProjectionReceipt) -> None: ...
    def save_checkpoint(self, root_fact: FinanceManualReviewRootFact) -> None: ...
    def query_recovery(self, fingerprint: PreviewFingerprint) -> StoredRecoveryProjection | None: ...


class ProjectionStorageUnavailable(RuntimeError):
    """Signals a transient projector storage failure."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class RootFactProjectionError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class RootFactProjectionApplication:
    def __init__(self, registry: AnomalyDefinitionRegistry, repository: RootFactProjectionRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._registry = registry
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def project(self, root_fact: FinanceManualReviewRootFact, correlation_id: CorrelationId) -> RootFactProjectionReceipt:
        try:
            candidate = build_finance_manual_review_candidate(self._registry, root_fact)
            return self._project(root_fact, candidate, correlation_id)
        except RootFactProjectionError:
            raise
        except ProjectionStorageUnavailable as error:
            raise _storage_projection_error(correlation_id, error) from error
        except ValueError as error:
            raise _value_projection_error(correlation_id, error) from error

    def query_recovery(self, fingerprint: PreviewFingerprint, correlation_id: CorrelationId) -> RecoveryContext:
        try:
            stored = self._repository.query_recovery(fingerprint)
        except ProjectionStorageUnavailable as error:
            raise _storage_projection_error(correlation_id, error) from error
        except ValueError as error:
            raise _value_projection_error(correlation_id, error) from error
        if stored is None:
            raise _projection_error(correlation_id, "anomaly_not_found")
        try:
            definition = self._registry.require(stored.projection.definition_code)
        except ValueError as error:
            raise _value_projection_error(correlation_id, error) from error
        return RecoveryContext(projection=stored.projection, source_domain=definition.source_domain, severity=definition.severity.value, root_fact_snapshot=stored.root_fact_snapshot, domain_blocker_active=_domain_blocker_active(stored), projection_freshness=stored.projection_freshness, occurrence_timeline=stored.occurrence_timeline, workflow_timeline=stored.workflow_timeline, available_actions=_recovery_actions(definition, stored))

    def query_recovery_preview_link(self, fingerprint: PreviewFingerprint, action_key: str, correlation_id: CorrelationId) -> RecoveryActionLink:
        context = self.query_recovery(fingerprint, correlation_id)
        for action in context.available_actions:
            if action.action_key == action_key:
                return action
        raise _projection_error(correlation_id, "recovery_action_not_available")

    def _project(self, root_fact, candidate, correlation_id) -> RootFactProjectionReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            replay = self._repository.find_receipt(root_fact.source_event_identity, for_update=True)
            if replay is not None:
                _validate_replay(replay, candidate, correlation_id)
                unit_of_work.commit()
                return replay
            previous = self._repository.load_current(candidate.alert_fingerprint, for_update=True)
            _validate_source_version(previous, root_fact, correlation_id)
            resulting = reduce_current_alert(self._registry, candidate.desired, previous)
            self._repository.save_current(previous, resulting, candidate)
            if candidate.occurrence is not None:
                self._repository.append_occurrence(candidate.occurrence)
            receipt = _projection_receipt(root_fact, candidate, resulting)
            self._repository.save_receipt(receipt)
            self._repository.save_checkpoint(root_fact)
            unit_of_work.commit()
            return receipt


def _validate_replay(replay, candidate, correlation_id) -> None:
    if replay.event_payload_fingerprint != candidate.event_payload_fingerprint:
        raise _projection_error(correlation_id, "anomaly_projection_data_integrity_violation")


def _validate_source_version(previous, root_fact, correlation_id) -> None:
    if previous is None:
        return
    if root_fact.source_version < previous.source_version:
        raise _projection_error(correlation_id, "anomaly_projection_stale", current_version=previous.source_version)
    if root_fact.origin is not RootFactEventOrigin.HISTORICAL_RESCAN and root_fact.source_version == previous.source_version:
        raise _projection_error(correlation_id, "anomaly_projection_data_integrity_violation")


def _projection_receipt(root_fact, candidate, resulting):
    return RootFactProjectionReceipt(root_fact.source_event_identity, candidate.event_payload_fingerprint, candidate.alert_fingerprint, root_fact.source_version, root_fact.active, None if resulting is None else resulting.workflow_version, candidate.occurrence is not None)


def _domain_blocker_active(stored: StoredRecoveryProjection) -> bool:
    return stored.root_fact_snapshot.get("root_condition_active") is True and isinstance(stored.root_fact_snapshot.get("domain_blockers"), list) and bool(stored.root_fact_snapshot.get("domain_blockers"))


def _recovery_actions(
    definition: AnomalyDefinition,
    stored: StoredRecoveryProjection,
) -> tuple[RecoveryActionLink, ...]:
    projection = stored.projection
    if definition.code == "CLIENTREFUND-001":
        return (
            RecoveryActionLink(
                action_key="classify_client_refund_return",
                label="處理客戶退款退匯",
                owning_domain="finance_import",
                preview_operation="PreviewCorrectAndPostClientRefundReturn",
                apply_operation="CorrectAndPostClientRefundReturn",
                requires_preview=True,
                form_schema_key="finance_import.correction.v1",
                source_binding_keys=("finance_import_row_identity", "source_version"),
                source_bindings={
                    "finance_import_row_identity": projection.source_identity,
                    "source_version": projection.source_version,
                },
                required_operator_inputs=("evidence", "reason", "refund_ledger_entry_identity", "target_obligation_identities"),
                required_capability="finance_import.correct_and_post",
                completion_predicate="client_refund_return_cleared",
            ),
        )
    if definition.code == "finance_import_manual_review":
        return finance_manual_review_recovery_actions(
            projection.source_identity,
            projection.source_version,
        )
    return _bound_registry_actions(definition.available_actions, stored.root_fact_snapshot)


def _bound_registry_actions(
    descriptors: tuple[RecoveryActionDescriptor, ...],
    root_fact_snapshot: dict[str, object],
) -> tuple[RecoveryActionLink, ...]:
    bindings = root_fact_snapshot.get("recovery_bindings")
    if not isinstance(bindings, dict):
        return ()
    aggregate_versions = _aggregate_versions(bindings, root_fact_snapshot)
    if not aggregate_versions:
        return ()
    actions: list[RecoveryActionLink] = []
    for descriptor in descriptors:
        action = _assemble_registry_action(
            descriptor,
            bindings,
            aggregate_versions,
        )
        if action is not None:
            actions.append(action)
    return tuple(actions)


def _aggregate_versions(
    bindings: dict[object, object],
    root_fact_snapshot: dict[str, object],
) -> dict[str, int]:
    versions = {
        str(key): value
        for key, value in bindings.items()
        if isinstance(key, str)
        and key.endswith("_version")
        and not isinstance(value, bool)
        and isinstance(value, int)
        and value >= 0
    }
    source_version = root_fact_snapshot.get("source_version")
    if isinstance(source_version, int) and not isinstance(source_version, bool) and source_version >= 0:
        versions.setdefault("source_version", source_version)
    return versions


def _assemble_registry_action(
    descriptor: RecoveryActionDescriptor,
    bindings: dict[object, object],
    aggregate_versions: dict[str, int],
) -> RecoveryActionLink | None:
    if not all(isinstance(key, str) for key in bindings):
        return None
    try:
        facts = RecoveryContextFacts(
            descriptor.action_key,
            {str(key): value for key, value in bindings.items()},
            aggregate_versions,
        )
    except (TypeError, ValueError):
        return None
    return assemble_recovery_action(descriptor, facts)


def _projection_error(correlation_id, code, *, current_version=None) -> RootFactProjectionError:
    return RootFactProjectionError(TypedError(category=_error_category(code), code=code, message=_error_message(code), correlation_id=correlation_id, retryable=code == "projector_unavailable", current_version=_expected_version(current_version)))


def _storage_projection_error(correlation_id, error):
    return _projection_error(correlation_id, "projector_unavailable" if error.retryable else "transaction_failed")


def _value_projection_error(correlation_id, error):
    code = str(error)
    if code not in {"anomaly_definition_not_found", "anomaly_projection_data_integrity_violation", "anomaly_projection_stale", "anomaly_source_fact_invalid"}:
        code = "anomaly_source_fact_invalid"
    return _projection_error(correlation_id, code)


def _expected_version(current_version):
    return None if current_version is None else ExpectedVersion(current_version)


def _error_category(code):
    if code in {"anomaly_not_found", "anomaly_definition_not_found"}:
        return ErrorCategory.NOT_FOUND
    if code == "projector_unavailable":
        return ErrorCategory.UNAVAILABLE
    if code == "transaction_failed":
        return ErrorCategory.INTERNAL
    if code.startswith("anomaly_projection_"):
        return ErrorCategory.CONFLICT
    return ErrorCategory.VALIDATION


def _error_message(code):
    return {"anomaly_not_found": "找不到異常 recovery context。", "anomaly_definition_not_found": "找不到異常定義。", "anomaly_source_fact_invalid": "來源根事實格式不正確。", "anomaly_projection_stale": "來源事件版本已過期。", "anomaly_projection_data_integrity_violation": "來源事件重播內容不一致。", "recovery_action_not_available": "此異常沒有要求的修復入口。", "projector_unavailable": "異常 projector 暫時無法寫入，請重試同一事件。", "transaction_failed": "異常 projector 交易失敗。"}[code]


__all__ = ["ProjectionStorageUnavailable", "RootFactProjectionApplication", "RootFactProjectionError", "RootFactProjectionReceipt", "StoredRecoveryProjection"]
