"""Independent worker orchestration for replayable Global commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from shared_kernel.durable_job_queue import (
    DurableJobLease,
    RetryableDurableJobError,
)

JobHandler = Callable[[dict[str, Any]], tuple[dict[str, Any], str]]


class DurableJobWorker:
    def __init__(
        self,
        repository: BackgroundJobRepository,
        handlers: dict[str, JobHandler],
        worker_id: str,
        lease_seconds: int = 60,
        retry_delay_seconds: int = 15,
    ):
        self._repository = repository
        self._handlers = handlers
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._retry_delay_seconds = retry_delay_seconds

    def recover_and_run_once(self) -> bool:
        self._repository.requeue_expired_leases(self._retry_delay_seconds)
        lease = self._repository.claim_next_command(
            self._worker_id,
            self._lease_seconds,
        )
        if lease is None:
            return False
        self._execute_lease(lease)
        return True

    def _execute_lease(self, lease: DurableJobLease) -> None:
        handler = self._handlers.get(lease.command.command_type)
        if handler is None:
            self._fail_unknown_command(lease)
            return
        try:
            receipt, reference = handler(lease.command.payload)
            self._repository.complete_claimed_job(lease, receipt, reference)
        except RetryableDurableJobError as error:
            self._repository.fail_claimed_job(
                lease,
                _error_payload(error.code, error.message, "UNAVAILABLE"),
                self._retry_delay_seconds,
            )
        except Exception as error:
            self._repository.fail_claimed_job(
                lease,
                _error_payload("durable_job_execution_failed", str(error), "INTERNAL"),
            )

    def _fail_unknown_command(self, lease: DurableJobLease) -> None:
        self._repository.fail_claimed_job(
            lease,
            _error_payload(
                "durable_job_handler_not_registered",
                "No durable worker handler is registered for this command.",
                "INTERNAL",
            ),
        )


def finance_import_batch_apply_handler(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Reconstruct the existing Finance Import command with a fresh outer UoW."""
    from api.dependencies.finance_import import build_finance_import_application
    from infrastructure.mysql.finance_import_owning_domain_composite import (
        MySqlFinanceImportOwningDomainComposite,
    )
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest

    connection = get_connection()
    try:
        application = build_finance_import_application(
            connection,
            MySqlFinanceImportOwningDomainComposite(connection),
        )
        request = FinanceImportApplyRequest(
            payload["batch_identity"],
            ExpectedVersion(payload["expected_batch_version"]),
            PreviewFingerprint(payload["preview_fingerprint"]),
            IdempotencyKey(payload["idempotency_key"]),
            ActorContext(payload["actor"]),
            payload["reason"],
            CorrelationId(payload["correlation_id"]),
        )
        receipt = _materialize(application.apply_batch(request))
        reference = "finance_import_batch:" + receipt["batch_identity"]
        return receipt, reference
    finally:
        connection.close()


def default_job_handlers() -> dict[str, JobHandler]:
    return {
        "finance_import_batch_apply": finance_import_batch_apply_handler,
        "finance_import_correction_apply": finance_import_correction_apply_handler,
    }


def finance_import_correction_apply_handler(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Reconstruct one Finance Import correction with a fresh owning-domain UoW."""
    from api.dependencies.finance_import import build_finance_import_application
    from domains.finance_import.correction import FinanceImportCorrectionSelection
    from domains.finance_import.planning import FinanceClassificationType
    from infrastructure.mysql.finance_import_owning_domain_composite import (
        MySqlFinanceImportOwningDomainComposite,
    )
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.correction_workflow import FinanceImportCorrectionApplyRequest

    connection = get_connection()
    try:
        application = build_finance_import_application(
            connection,
            MySqlFinanceImportOwningDomainComposite(connection),
        )
        selection = FinanceImportCorrectionSelection(
            payload["row_identity"],
            FinanceClassificationType(payload["classification_type"]),
            tuple(payload["target_obligation_identities"]),
            payload["reason"],
            tuple(payload["evidence"]),
            payload.get("refund_ledger_entry_identity"),
        )
        request = FinanceImportCorrectionApplyRequest(
            selection,
            ExpectedVersion(payload["expected_batch_version"]),
            ExpectedVersion(payload["expected_canonical_fact_version"]),
            ExpectedVersion(payload["expected_alert_version"]),
            PreviewFingerprint(payload["preview_fingerprint"]),
            IdempotencyKey(payload["idempotency_key"]),
            ActorContext(payload["actor"]),
            CorrelationId(payload["correlation_id"]),
        )
        receipt = _materialize(application.correct_and_post(request))
        reference = "finance_import_correction:" + receipt["row_identity"]
        return receipt, reference
    finally:
        connection.close()


def _error_payload(code: str, message: str, category: str) -> dict[str, Any]:
    return {"error": {"category": category, "code": code, "message": message}}


def _materialize(value: Any) -> Any:
    if is_dataclass(value):
        return _materialize(asdict(value))
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_materialize(item) for item in value]
    if isinstance(value, (date, datetime, Enum)):
        return value.isoformat() if not isinstance(value, Enum) else value.value
    return value
