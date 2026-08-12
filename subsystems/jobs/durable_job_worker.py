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
    TerminalDurableJobError,
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
        except TerminalDurableJobError as error:
            self._repository.fail_claimed_job(
                lease,
                _typed_error_payload(error.error),
            )
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
        "assignment_plan_apply": assignment_plan_apply_handler,
        "finance_import_batch_apply": finance_import_batch_apply_handler,
        "finance_import_correction_apply": finance_import_correction_apply_handler,
        "finance_import_historical_reprocess_apply": historical_reprocess_apply_handler,
        "government_subsidy_apply": government_subsidy_apply_handler,
        "orders_auto_completion_apply": order_auto_completion_handler,
        "payroll_rebuild_apply": payroll_rebuild_apply_handler,
        "staff_payout_apply": staff_payout_apply_handler,
    }


def historical_reprocess_apply_handler(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Run one historical reprocess under a fresh typed Finance Import UoW."""
    from api.dependencies.finance_import import HistoricalReprocessApplication
    from infrastructure.mysql.finance_import_owning_domain_composite import (
        MySqlFinanceImportOwningDomainComposite,
    )
    from infrastructure.mysql.finance_import_repository import FinanceImportMySqlUnitOfWork
    from infrastructure.mysql.historical_reprocess_repository import MySqlHistoricalReprocessRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.historical_reprocess_workflow import (
        HistoricalOwnerSelection,
        HistoricalReprocessApplyRequest,
        HistoricalReprocessWorkflow,
    )

    connection = get_connection()
    try:
        posting_port = MySqlFinanceImportOwningDomainComposite(connection)
        application = HistoricalReprocessApplication(
            HistoricalReprocessWorkflow(
                MySqlHistoricalReprocessRepository(connection),
                posting_port,
                lambda: FinanceImportMySqlUnitOfWork(connection),
            ),
            posting_port,
        )
        request = HistoricalReprocessApplyRequest(
            payload["batch_identity"],
            ExpectedVersion(payload["expected_batch_version"]),
            PreviewFingerprint(payload["preview_fingerprint"]),
            IdempotencyKey(payload["idempotency_key"]),
            ActorContext(payload["actor"]),
            payload["reason"],
            CorrelationId(payload["correlation_id"]),
            tuple(
                HistoricalOwnerSelection(
                    item["row_identity"],
                    item["case_no"],
                    item["obligation_identity"],
                    item["reason"],
                    tuple(item["evidence_references"]),
                )
                for item in payload.get("owner_selections", ())
            ),
        )
        receipt = _materialize(application.apply(request))
        return receipt, "finance_import_historical_reprocess:" + receipt["batch_identity"]
    finally:
        connection.close()


def government_subsidy_apply_handler(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Run a Government Subsidy Apply action through its existing owning UoW."""
    from api.dependencies.government_subsidy import build_government_subsidy_application
    from infrastructure.mysql.mysql_adapter import get_connection
    from pymysql.err import OperationalError
    from shared_kernel.errors import ErrorCategory, TypedError
    from shared_kernel.identities import CorrelationId
    from subsystems.government_subsidy.claim_workflow import GovernmentSubsidyClaimWorkflowError
    from subsystems.government_subsidy.ledger_workflow import GovernmentSubsidyWorkflowError

    connection = get_connection()
    try:
        receipt = _apply_government_subsidy_action(
            build_government_subsidy_application(connection), payload
        )
        materialized = _materialize(receipt)
        return materialized, f"government_subsidy:{materialized['batch_id']}"
    except (GovernmentSubsidyWorkflowError, GovernmentSubsidyClaimWorkflowError) as error:
        if error.error.category is ErrorCategory.UNAVAILABLE and error.error.retryable:
            raise RetryableDurableJobError(error.error.code, error.error.message) from error
        raise TerminalDurableJobError(error.error) from error
    except OperationalError as error:
        if _is_retryable_mysql_error(error):
            raise RetryableDurableJobError(
                "government_subsidy_transaction_temporarily_unavailable",
                "Government Subsidy transaction is temporarily unavailable.",
            ) from error
        raise
    except ValueError as error:
        raise TerminalDurableJobError(
            TypedError(
                ErrorCategory.VALIDATION,
                str(error) or "invalid_government_subsidy_intent",
                "Government Subsidy command is invalid.",
                CorrelationId(payload["correlation_id"]),
            )
        ) from error
    finally:
        connection.close()


def _apply_government_subsidy_action(application, payload):
    request = _government_subsidy_request(payload)
    action = payload["action"]
    if action == "claim_plan":
        return application.apply_claim_plan(request)
    if action == "claim_submission":
        return application.apply_claim_submission(request)
    if action == "claim_approval":
        return application.apply_claim_approval(request)
    if action == "receipt":
        return application.apply_receipt(request)
    if action == "reversal":
        return application.apply_reversal(request)
    raise ValueError("invalid_government_subsidy_action")


def _government_subsidy_request(payload):
    from domains.government_subsidy.claims import ClaimApprovalIntent, ClaimPlanningIntent
    from domains.government_subsidy.ledger import AllocationIntent, ClaimBatchIdentity, ReceiptIntent, ReversalIntent
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from shared_kernel.money import MoneyNTD
    from subsystems.government_subsidy.claim_workflow import ClaimApprovalApplyRequest, ClaimPlanningApplyRequest, ClaimSubmissionApplyRequest, ClaimSubmissionIntent
    from subsystems.government_subsidy.ledger_workflow import GovernmentSubsidyReceiptApplyRequest, GovernmentSubsidyReversalApplyRequest

    action = payload["action"]
    intent_data = payload["intent"]
    allocations = tuple(AllocationIntent(item.get("target_identity", item.get("item_id")), MoneyNTD(item.get("amount_ntd", item.get("approved_amount_ntd")))) for item in intent_data.get("allocations", intent_data.get("item_approvals", [])))
    arguments = (ExpectedVersion(payload["expected_batch_version"]), PreviewFingerprint(payload["preview_fingerprint"]), IdempotencyKey(payload["idempotency_key"]), ActorContext(payload["actor"]), payload["reason"], CorrelationId(payload["correlation_id"]))
    if action == "claim_plan":
        intent = ClaimPlanningIntent(ClaimBatchIdentity(intent_data["application_year"], intent_data["quarter"], intent_data["revision"]))
        return ClaimPlanningApplyRequest(intent, *arguments)
    if action == "claim_submission":
        return ClaimSubmissionApplyRequest(ClaimSubmissionIntent(intent_data["batch_id"]), *arguments)
    if action == "claim_approval":
        return ClaimApprovalApplyRequest(ClaimApprovalIntent(intent_data["batch_id"], allocations), *arguments)
    if action == "receipt":
        return GovernmentSubsidyReceiptApplyRequest(ReceiptIntent(intent_data["finance_import_row_id"], intent_data["batch_id"], allocations), *arguments)
    if action == "reversal":
        return GovernmentSubsidyReversalApplyRequest(ReversalIntent(intent_data["finance_import_row_id"], intent_data["source_receipt_id"], allocations), *arguments)
    raise ValueError("invalid_government_subsidy_action")


def assignment_plan_apply_handler(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Reconstruct Assignment Plan Apply through its existing owning UoW."""
    from api.dependencies.assignment_plan import build_assignment_plan_application
    from infrastructure.mysql.mysql_adapter import get_connection
    from pymysql.err import OperationalError, ProgrammingError
    from shared_kernel.errors import ErrorCategory
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.scheduling.assignment_plan_workflow import AssignmentPlanWorkflowError

    connection = get_connection()
    try:
        receipt = _materialize(build_assignment_plan_application(connection).apply(_assignment_plan_request(payload)))
        return receipt, "assignment_plan:" + receipt["case_no"]
    except AssignmentPlanWorkflowError as error:
        if error.error.category is ErrorCategory.UNAVAILABLE and error.error.retryable:
            raise RetryableDurableJobError(error.error.code, error.error.message) from error
        raise TerminalDurableJobError(error.error) from error
    except (OperationalError, ProgrammingError) as error:
        if _is_retryable_mysql_error(error):
            raise RetryableDurableJobError("assignment_plan_transaction_temporarily_unavailable", "Assignment Plan transaction is temporarily unavailable.") from error
        raise
    finally:
        connection.close()


def _assignment_plan_request(payload: dict[str, Any]):
    from domains.scheduling.assignment_plan import AssignmentPlanIntent, AssignmentPlanSegmentIntent
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.scheduling.assignment_plan_workflow import AssignmentPlanApplyRequest

    segments = tuple(
        AssignmentPlanSegmentIntent(
            item["staff_id"],
            date.fromisoformat(item["assigned_start_date"]),
            date.fromisoformat(item["assigned_end_date"]),
            tuple(date.fromisoformat(value) for value in item["official_service_dates"]),
        )
        for item in payload["segments"]
    )
    return AssignmentPlanApplyRequest(
        payload["case_no"], AssignmentPlanIntent(segments),
        ExpectedVersion(payload["expected_order_version"]),
        ExpectedVersion(payload["expected_scheduling_version"]),
        ExpectedVersion(payload["expected_client_finance_version"]),
        ExpectedVersion(payload["expected_payroll_version"]),
        PreviewFingerprint(payload["preview_fingerprint"]),
        IdempotencyKey(payload["idempotency_key"]), ActorContext(payload["actor"]),
        payload["reason"], CorrelationId(payload["correlation_id"]),
    )


def payroll_rebuild_apply_handler(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Run Payroll Rebuild using a fresh connection and its existing owning UoW."""
    from api.dependencies.payroll_rebuild import build_payroll_rebuild_application
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.payroll_rebuild_repository import PayrollRebuildRepositoryUnavailable
    from pymysql.err import OperationalError
    from shared_kernel.errors import ErrorCategory, TypedError
    from shared_kernel.identities import CorrelationId
    from subsystems.payroll.rebuild_workflow import PayrollRebuildError

    connection = get_connection()
    try:
        receipt = build_payroll_rebuild_application(connection).apply(
            _payroll_rebuild_request(payload)
        )
        return _payroll_rebuild_receipt_payload(receipt), f"payroll_rebuild:{receipt.case_no}"
    except PayrollRebuildError as error:
        if error.error.category is ErrorCategory.UNAVAILABLE and error.error.retryable:
            raise RetryableDurableJobError(error.error.code, error.error.message) from error
        raise TerminalDurableJobError(error.error) from error
    except PayrollRebuildRepositoryUnavailable as error:
        typed_error = TypedError(
            ErrorCategory.UNAVAILABLE if error.retryable else ErrorCategory.INTERNAL,
            "payroll_rebuild_transaction_unavailable",
            "Payroll rebuild transaction is temporarily unavailable." if error.retryable else "Payroll rebuild transaction failed.",
            CorrelationId(payload["correlation_id"]),
            retryable=error.retryable,
        )
        if error.retryable:
            raise RetryableDurableJobError(typed_error.code, typed_error.message) from error
        raise TerminalDurableJobError(typed_error) from error
    except OperationalError as error:
        if _is_retryable_mysql_error(error):
            raise RetryableDurableJobError(
                "payroll_rebuild_transaction_temporarily_unavailable",
                "Payroll rebuild transaction is temporarily unavailable.",
            ) from error
        raise
    finally:
        connection.close()


def _payroll_rebuild_request(payload: dict[str, Any]):
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.payroll.rebuild_workflow import PayrollRebuildRequest

    return PayrollRebuildRequest(
        payload["case_no"],
        ExpectedVersion(payload["expected_payroll_version"]),
        PreviewFingerprint(payload["preview_fingerprint"]),
        IdempotencyKey(payload["idempotency_key"]),
        ActorContext(payload["actor"]),
        payload["reason"],
        CorrelationId(payload["correlation_id"]),
    )


def _payroll_rebuild_receipt_payload(receipt) -> dict[str, Any]:
    return {
        "case_no": receipt.case_no,
        "payroll_version": receipt.payroll_version,
        "action_count": receipt.action_count,
        "total_payable_ntd": receipt.total_payable.amount,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def staff_payout_apply_handler(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Run all Staff Payout event types through the existing owning UoW."""
    from api.dependencies.staff_payout import build_staff_payout_application
    from infrastructure.mysql.mysql_adapter import get_connection
    from pymysql.err import OperationalError
    from shared_kernel.errors import ErrorCategory, TypedError
    from shared_kernel.identities import CorrelationId
    from subsystems.staff_payables.payout_reconciliation import StaffPayoutReconciliationError

    connection = get_connection()
    try:
        receipt = build_staff_payout_application(connection).apply(
            _staff_payout_request(payload)
        )
        return _staff_payout_receipt_payload(receipt), f"staff_payout:{receipt.staff_id}"
    except StaffPayoutReconciliationError as error:
        if error.error.category is ErrorCategory.UNAVAILABLE and error.error.retryable:
            raise RetryableDurableJobError(error.error.code, error.error.message) from error
        raise TerminalDurableJobError(error.error) from error
    except OperationalError as error:
        if _is_retryable_mysql_error(error):
            raise RetryableDurableJobError(
                "staff_payout_transaction_temporarily_unavailable",
                "Staff payout transaction is temporarily unavailable.",
            ) from error
        raise
    except ValueError as error:
        raise TerminalDurableJobError(
            TypedError(
                ErrorCategory.VALIDATION,
                str(error) or "invalid_staff_payout_intent",
                "Staff payout command is invalid.",
                CorrelationId(payload["correlation_id"]),
            )
        ) from error
    finally:
        connection.close()


def _staff_payout_request(payload: dict[str, Any]):
    from domains.staff_payables.reconciliation import StaffPayoutDifferenceMode, StaffPayoutEventType
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.staff_payables.payout_reconciliation import StaffPayoutApplyRequest, StaffPayoutSelection

    selection = payload["selection"]
    return StaffPayoutApplyRequest(
        StaffPayoutSelection(
            StaffPayoutEventType(selection["event_type"]),
            tuple(selection["bank_fact_identities"]),
            tuple(selection["obligation_identities"]),
            selection["reopen_fact_identity"],
            None if selection.get("difference_mode") is None else StaffPayoutDifferenceMode(selection["difference_mode"]),
        ),
        ExpectedVersion(payload["expected_staff_payables_version"]),
        ExpectedVersion(payload["expected_bank_facts_version"]),
        PreviewFingerprint(payload["preview_fingerprint"]),
        IdempotencyKey(payload["idempotency_key"]),
        ActorContext(payload["actor"]),
        payload["reason"],
        CorrelationId(payload["correlation_id"]),
    )


def _staff_payout_receipt_payload(receipt) -> dict[str, Any]:
    status = receipt.resulting_status
    return {
        "event_type": receipt.event_type.value,
        "staff_id": receipt.staff_id,
        "staff_payables_version": receipt.staff_payables_version,
        "bank_facts_version": receipt.bank_facts_version,
        "resulting_status": status.value if isinstance(status, Enum) else status,
        "event_count": receipt.event_count,
        "obligation_link_count": receipt.obligation_link_count,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def order_auto_completion_handler(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Run a discovered Orders completion through its sole canonical command."""
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.order_auto_completion_repository import MySqlOrderAutoCompletionRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from pymysql.err import OperationalError
    from shared_kernel.errors import ErrorCategory
    from subsystems.orders.auto_completion_workflow import (
        AutoCompleteOrderService,
        AutoCompletionWorkflowError,
    )

    request = _auto_completion_request(payload)
    connection = get_connection()
    try:
        workflow = AutoCompleteOrderService(
            MySqlOrderAutoCompletionRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
        receipt = _materialize(workflow.apply(request))
        return receipt, "orders_auto_completion:" + receipt["case_no"]
    except AutoCompletionWorkflowError as error:
        if error.error.category is ErrorCategory.UNAVAILABLE and error.error.retryable:
            raise RetryableDurableJobError(error.error.code, error.error.message) from error
        raise TerminalDurableJobError(error.error) from error
    except OperationalError as error:
        if _is_retryable_mysql_error(error):
            raise RetryableDurableJobError(
                "auto_completion_transaction_temporarily_unavailable",
                "Orders service completion transaction is temporarily unavailable.",
            ) from error
        raise
    finally:
        connection.close()


def _auto_completion_request(payload: dict[str, Any]):
    from datetime import datetime
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.orders.auto_completion_workflow import AutoCompletionApplyRequest

    return AutoCompletionApplyRequest(
        payload["case_no"],
        ExpectedVersion(payload["expected_order_version"]),
        datetime.fromisoformat(payload["evaluation_at"]),
        IdempotencyKey(payload["idempotency_key"]),
        ActorContext(payload["actor"]),
        payload["reason"],
        CorrelationId(payload["correlation_id"]),
    )


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
            bool(payload.get("allow_partial_refund_recovery", False)),
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


def _typed_error_payload(error) -> dict[str, Any]:
    return {
        "error": {
            "category": error.category.value,
            "code": error.code,
            "correlation_id": error.correlation_id.value,
            "domain_blockers": list(error.domain_blockers),
            "message": error.message,
            "retryable": error.retryable,
        }
    }


def _is_retryable_mysql_error(error: Exception) -> bool:
    return bool(error.args) and error.args[0] in {1205, 1213}


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
