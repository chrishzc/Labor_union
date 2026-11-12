"""
File: finance_import_owning_domain_composite.py
Description: 在單一借用交易中透過各責任 Domain 執行 Finance Import 核對與入帳。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json

from domains.client_finance.reconciliation import (
    PaymentStage,
    ReconciliationStatus,
)
from domains.client_finance.client_refund_reversal import (
    ClientFinanceCorrectionType,
    ClientRefundPurpose,
)
from domains.finance_import.correction import (
    ClientRefundCorrectionPreview,
    CorrectionAllocation,
    FinanceImportCorrectionCandidate,
    FinanceImportCorrectionSelection,
)
from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
    ClientReceiptReviewCandidate,
    ClientReceiptReviewDiagnostic,
    FinanceClassificationType,
    FinanceImportDisposition,
)
from domains.government_subsidy.ledger import (
    GovernmentSubsidyDomainError,
    GovernmentSubsidyErrorCode,
    ReceiptIntent,
)
from domains.staff_payables.reconciliation import StaffPayoutEventType
from infrastructure.mysql.client_receipt_reconciliation_repository import (
    ClientReceiptRepositoryUnavailable,
    MySqlClientReceiptReconciliationRepository,
)
from infrastructure.mysql.client_refund_reversal_repository import (
    MySqlClientRefundReversalRepository,
)
from infrastructure.mysql.government_subsidy_repository import (
    MySqlGovernmentSubsidyRepository,
)
from infrastructure.mysql.staff_payout_repository import (
    MySqlStaffPayoutRepository,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.money import MoneyNTD
from domains.finance_import.cancellation_code import (
    resolve_finance_cancellation_code,
    sinopac_memo_case_suffixes,
)
from domains.finance_import.transaction_classifier import TAISHIN_CLIENT_SUBSIDY_MEMO_REASON, _is_same_month
from subsystems.client_finance.virtual_account_resolution import (
    resolve_client_virtual_account,
    resolve_client_virtual_account_suffix,
)
from subsystems.client_finance.reconciliation_workflow import (
    ClientReconciliationApplyRequest,
    ClientReconciliationError,
    ClientReconciliationWorkflow,
    ReconciliationSelection,
)
from subsystems.client_finance.client_refund_reversal_workflow import (
    ClientRefundReversalApplyRequest,
    ClientRefundReversalError,
    ClientRefundReversalSelection,
    ClientRefundReversalWorkflow,
)
from subsystems.finance_import.import_workflow import (
    FinanceDispatchOutcome,
    FinanceImportDispatchResult,
    FinanceImportRepositoryUnavailable,
)
from subsystems.finance_import.correction_workflow import FinanceImportCorrectionWorkflowError
from subsystems.government_subsidy.ledger_workflow import (
    GovernmentSubsidyLedgerWorkflow,
    GovernmentSubsidyReceiptApplyRequest,
    GovernmentSubsidyWorkflowError,
)
from subsystems.staff_payables.payout_reconciliation import (
    StaffPayoutApplyRequest,
    StaffPayoutReconciliationError,
    StaffPayoutRepositoryUnavailable,
    StaffPayoutReconciliationWorkflow,
    StaffPayoutSelection,
)

_CLIENT_RECEIPT = FinanceClassificationType.CLIENT_RECEIPT
_CLIENT_REFUND = FinanceClassificationType.CLIENT_REFUND
_CLIENT_REFUND_RETURN = FinanceClassificationType.CLIENT_REFUND_RETURN
_GOVERNMENT_SUBSIDY = FinanceClassificationType.GOVERNMENT_SUBSIDY
_STAFF_PAYOUT = FinanceClassificationType.STAFF_PAYOUT
_CLIENT_SUBSIDY_RETURN = FinanceClassificationType.CLIENT_SUBSIDY_RETURN
_VERIFIED_OUTGOING_NAME_EVIDENCE = frozenset({
    "unique_staff_payout_name_and_month_matched",
    "staff_payout_disambiguated_by_month_and_amount",
    "unique_staff_payout_name_month_fee_matched",
    "outgoing_staff_payout_multiple_fee_matches",
    "unique_client_refund_name_and_month_matched",
    "client_refund_disambiguated_by_month_and_amount",
    "unique_client_refund_name_month_fee_matched",
    "outgoing_client_refund_multiple_fee_matches",
})


@dataclass(frozen=True, slots=True)
class _PostingContext:
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId


class BorrowedTransactionUnitOfWork:
    """Marks a child workflow complete while the outer owner controls commit."""

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class MySqlFinanceImportOwningDomainComposite:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._context: _PostingContext | None = None

    def bind_request(self, request) -> None:
        self._context = _PostingContext(
            request.idempotency_key,
            request.actor,
            _request_reason(request),
            request.correlation_id,
        )

    def clear_request(self) -> None:
        self._context = None

    def validate_client_refund(self, candidate, correlation_id) -> None:
        self._preview_client_refund_owner(candidate, correlation_id)

    def preview_client_refund(self, selection, facts, correlation_id) -> ClientRefundCorrectionPreview:
        preview = self._preview_client_refund_owner(selection, correlation_id)
        if preview.candidate.amount != facts.bank_amount:
            raise ValueError('refund_owner_preview_mismatch')
        allocations = tuple(
            CorrectionAllocation(item.obligation_identity, item.amount)
            for item in preview.candidate.allocations
        )
        total_due = sum(
            item.remaining_amount.amount for item in facts.target_obligations
            if item.obligation_identity in selection.target_obligation_identities
        )
        return ClientRefundCorrectionPreview(
            selection.target_obligation_identities, allocations, preview.candidate.transfer_fee,
            MoneyNTD(total_due - sum(item.amount.amount for item in allocations)), preview.fingerprint,
        )

    def _preview_client_refund_owner(self, candidate, correlation_id):
        """Preview the planned classification with the same owner as formal posting."""
        selection = (
            _client_subsidy_return_selection(self._connection, candidate)
            if candidate.classification_type is _CLIENT_SUBSIDY_RETURN
            else _client_refund_selection(self._connection, candidate)
        )
        repository = MySqlClientRefundReversalRepository(
            self._connection, preview_refund_classification=candidate.classification_type.value,
        )
        try:
            return ClientRefundReversalWorkflow(repository, BorrowedTransactionUnitOfWork).preview(selection, correlation_id)
        except ClientRefundReversalError as error:
            raise ValueError(error.error.code) from error

    def resolve(self, candidate):
        if not isinstance(candidate, CanonicalFinanceImportRow):
            raise TypeError("unsupported Finance Import resolution candidate")
        if candidate.disposition is not FinanceImportDisposition.BUSINESS_PENDING:
            return candidate
        from infrastructure.mysql.subsidy_confirmation_repository import resolve_subsidy_confirmation
        subsidy = resolve_subsidy_confirmation(self._connection, candidate, for_update=self._context is not None)
        if subsidy is not None:
            return subsidy
        if candidate.classification_type is _CLIENT_RECEIPT:
            return _resolve_client_receipt(self._connection, candidate)
        if candidate.classification_type is _CLIENT_REFUND:
            return _resolve_client_refund(self._connection, candidate)
        if candidate.classification_type is _CLIENT_SUBSIDY_RETURN:
            return _resolve_client_subsidy_return(self._connection, candidate)
        if candidate.classification_type is _GOVERNMENT_SUBSIDY:
            return _resolve_government_subsidy(self._connection, candidate)
        if candidate.classification_type is _STAFF_PAYOUT:
            return _resolve_staff_payout(self._connection, candidate)
        return candidate

    def resolve_pending_government(self, candidate):
        if candidate.disposition is not FinanceImportDisposition.BUSINESS_PENDING:
            return candidate
        from subsystems.government_subsidy.period_reconciliation import period_rematch_targets

        period = self._government_period_application().unique_bank_period(_row_id(candidate.row_identity))
        if period is None:
            return candidate
        return _ready_candidate(candidate, period_rematch_targets(period), "unique-exact-government-period")

    def _government_period_application(self):
        from infrastructure.mysql.government_subsidy_period_repository import MySqlGovernmentSubsidyPeriodRepository
        from subsystems.government_subsidy.period_reconciliation import PeriodReconciliationApplication

        return PeriodReconciliationApplication(
            MySqlGovernmentSubsidyPeriodRepository(self._connection), BorrowedTransactionUnitOfWork,
        )

    def post(self, candidate):
        try:
            return self._post(candidate, self._require_context())
        except (
            ClientReceiptRepositoryUnavailable,
            StaffPayoutRepositoryUnavailable,
        ) as error:
            raise FinanceImportRepositoryUnavailable(str(error)) from error
        except (
            ClientReconciliationError,
            ClientRefundReversalError,
            GovernmentSubsidyWorkflowError,
            StaffPayoutReconciliationError,
        ) as error:
            if getattr(candidate, 'subsidy_preflight', None) is not None:
                if error.error.category not in {ErrorCategory.DOMAIN_BLOCKED, ErrorCategory.CONFLICT}:
                    from subsystems.finance_import.import_workflow import FinanceImportWorkflowError
                    raise FinanceImportWorkflowError(error.error) from error
                return FinanceImportDispatchResult(candidate.row_identity, FinanceDispatchOutcome.CONFLICT,
                    reason_code=error.error.code)
            return _typed_domain_result(candidate, error.error)
        except GovernmentSubsidyDomainError as error:
            return _government_subsidy_domain_result(candidate, error)
        except ValueError as error:
            if getattr(candidate, 'subsidy_preflight', None) is not None:
                return FinanceImportDispatchResult(candidate.row_identity, FinanceDispatchOutcome.CONFLICT,
                    reason_code=str(error))
            raise

    def _post(self, candidate, context):
        if isinstance(candidate, CanonicalFinanceImportRow) and candidate.subsidy_preflight is not None:
            from infrastructure.mysql.subsidy_confirmation_repository import apply_subsidy_confirmation
            apply_subsidy_confirmation(self._connection, candidate, context)
            if candidate.subsidy_preflight.confirmation_only:
                return FinanceImportDispatchResult(candidate.row_identity, FinanceDispatchOutcome.PENDING,
                    reason_code='subsidy_scheme_confirmed_service_not_completed')
        if candidate.classification_type is _CLIENT_RECEIPT:
            return self._post_client_receipt(candidate, context)
        if candidate.classification_type is _CLIENT_REFUND:
            return self._post_client_refund(candidate, context)
        if candidate.classification_type is _CLIENT_REFUND_RETURN:
            return self._post_client_refund_return(candidate, context)
        if candidate.classification_type is _CLIENT_SUBSIDY_RETURN:
            return self._post_client_subsidy_return(candidate, context)
        if candidate.classification_type is _GOVERNMENT_SUBSIDY:
            return self._post_government_subsidy(candidate, context)
        if candidate.classification_type is _STAFF_PAYOUT:
            return self._post_staff_payout(candidate, context)
        return _unsupported_result(candidate)

    def _post_client_receipt(self, candidate, context):
        selection = _client_selection(self._connection, candidate)
        repository = MySqlClientReceiptReconciliationRepository(self._connection)
        workflow = ClientReconciliationWorkflow(
            repository,
            BorrowedTransactionUnitOfWork,
        )
        preview = workflow.preview(selection)
        request = _client_request(candidate, selection, preview, context)
        repository.bind_apply_request(request)
        try:
            receipt = workflow.apply(request)
        finally:
            repository.clear_apply_request()
        return _client_result(candidate, receipt)

    def _post_staff_payout(self, candidate, context):
        selection = StaffPayoutSelection(
            StaffPayoutEventType.PAYOUT,
            (_row_id(candidate.row_identity),),
            _target_identities(candidate),
            confirm_subsidy_split=bool(getattr(candidate, 'subsidy_preflight', None)
                                      and candidate.subsidy_preflight.staff_confirm_split),
        )
        repository = MySqlStaffPayoutRepository(self._connection)
        workflow = StaffPayoutReconciliationWorkflow(
            repository,
            BorrowedTransactionUnitOfWork,
        )
        preview = workflow.preview(selection, context.correlation_id)
        request = _staff_request(candidate, selection, preview, context)
        repository.bind_apply_request(request)
        try:
            receipt = workflow.apply(request)
        finally:
            repository.clear_apply_request()
        return _staff_result(candidate, receipt)

    # Kept cohesive so the child receipt and repository binding share the outer UoW.
    def _post_client_subsidy_return(self, candidate, context):
        selection = _client_subsidy_return_selection(
            self._connection,
            candidate,
        )
        repository = MySqlClientRefundReversalRepository(self._connection)
        workflow = ClientRefundReversalWorkflow(
            repository,
            BorrowedTransactionUnitOfWork,
        )
        preview = workflow.preview(selection, context.correlation_id)
        if (
            isinstance(candidate, FinanceImportCorrectionCandidate)
            and candidate.refund_preview is not None
            and preview.fingerprint != candidate.refund_preview.fingerprint
        ):
            raise FinanceImportCorrectionWorkflowError(TypedError(
                ErrorCategory.CONFLICT, 'stale_preview',
                'Client subsidy refund facts changed after Preview.', context.correlation_id,
            ))
        request = _client_subsidy_return_request(
            candidate,
            selection,
            preview,
            context,
        )
        repository.bind_apply_request(request)
        try:
            receipt = workflow.apply(request)
        finally:
            repository.clear_apply_request()
        return _client_subsidy_return_result(candidate, receipt)

    def _post_client_refund(self, candidate, context):
        selection = _client_refund_selection(self._connection, candidate)
        repository = MySqlClientRefundReversalRepository(self._connection)
        workflow = ClientRefundReversalWorkflow(
            repository,
            BorrowedTransactionUnitOfWork,
        )
        try:
            preview = workflow.preview(selection, context.correlation_id)
            if (
                isinstance(candidate, FinanceImportCorrectionCandidate)
                and candidate.refund_preview is not None
                and preview.fingerprint != candidate.refund_preview.fingerprint
            ):
                raise FinanceImportCorrectionWorkflowError(TypedError(
                    ErrorCategory.CONFLICT, 'stale_preview',
                    'Client refund facts changed after Preview.', context.correlation_id,
                ))
            request = _client_refund_request(candidate, selection, preview, context)
            repository.bind_apply_request(request)
            receipt = workflow.apply(request)
        except ClientRefundReversalError as error:
            if error.error.code == "bank_fact_not_eligible" and repository.refund_account_matches is False:
                return _typed_domain_result(candidate, error.error, reason_code="client_refund_recipient_account_mismatch")
            raise
        finally:
            repository.clear_apply_request()
        return _client_subsidy_return_result(candidate, receipt)

    def _post_client_refund_return(self, candidate, context):
        selection = _client_refund_return_selection(self._connection, candidate)
        repository = MySqlClientRefundReversalRepository(self._connection)
        workflow = ClientRefundReversalWorkflow(repository, BorrowedTransactionUnitOfWork)
        preview = workflow.preview(selection, context.correlation_id)
        request = _client_refund_return_request(candidate, selection, preview, context)
        repository.bind_apply_request(request)
        try:
            receipt = workflow.apply(request)
        finally:
            repository.clear_apply_request()
        return _client_subsidy_return_result(candidate, receipt)

    def _post_government_subsidy(self, candidate, context):
        if isinstance(candidate, CanonicalFinanceImportRow) and "unique-exact-government-period" in candidate.evidence:
            receipt = self._government_period_application().reconcile_unique(
                _row_id(candidate.row_identity), candidate.target_identities,
                _child_key(context, candidate, "government-period-rematch").value, context.actor.actor_id,
            )
            if receipt is None:
                return FinanceImportDispatchResult(candidate.row_identity, FinanceDispatchOutcome.PENDING,
                                                   reason_code="government_period_rematch_unresolved")
            return FinanceImportDispatchResult(candidate.row_identity, FinanceDispatchOutcome.RECONCILED,
                                               f"government-subsidy-period:{receipt}")
        raise ValueError('government_subsidy_period_entry_required')

    def _require_context(self) -> _PostingContext:
        if self._context is None:
            raise RuntimeError("Finance Import posting request is not bound")
        return self._context


def _resolve_client_receipt(connection, candidate):
    client_id = _single_prefixed_identity(candidate, "client:")
    case_no, trans_date, source_blocker = (
        (None, None, None)
        if client_id is not None
        else _virtual_account_case_info(
            connection,
            candidate.row_identity,
        )
    )
    if client_id is None and case_no is None:
        return candidate
    if source_blocker is not None:
        return replace(candidate, client_receipt_review=ClientReceiptReviewDiagnostic(source_blocker))
    with connection.cursor() as cursor:
        statement, parameters = _client_receipt_target_query(
            client_id,
            case_no,
            candidate.amount.amount,
        )
        cursor.execute(statement, parameters)
        rows = tuple(cursor.fetchall())
    if len(rows) == 1:
        target = str(rows[0]["obligation_identity"])
        if _is_same_month(trans_date, rows[0].get("due_date")):
            candidate = _ready_candidate(candidate, (target,), "exact-open-client-obligation-in-transaction-month")
    if len(rows) == 1 and ("due_date" not in rows[0] or trans_date is None or _is_same_month(trans_date, rows[0].get("due_date"))):
        target = str(rows[0]["obligation_identity"])
        return _ready_candidate(
            candidate,
            (target,),
            "exact-open-client-obligation",
        )
    # 2026-11-05 人工裁決：非精確匹配（未完全相符）時比對月份
    if trans_date is None:
        if case_no is not None:
            return replace(candidate, client_receipt_review=ClientReceiptReviewDiagnostic(
                "bank_transaction_date_missing",
            ))
        return candidate
    try:
        with connection.cursor() as cursor:
            statement, parameters = _client_receipt_open_obligations_query(
                client_id,
                case_no,
            )
            cursor.execute(statement, parameters)
            open_rows = _without_redundant_historical_baseline(tuple(cursor.fetchall()))
    except StopIteration:
        if len(rows) == 1:
            return _ready_candidate(candidate, (str(rows[0]["obligation_identity"]),), "exact-open-client-obligation")
        return candidate
    if not open_rows:
        return replace(candidate, client_receipt_review=ClientReceiptReviewDiagnostic(
            "sinopac_client_receipt_no_open_obligation",
        ))
    if any(row.get('due_date') is None for row in open_rows):
        return replace(candidate, client_receipt_review=ClientReceiptReviewDiagnostic(
            'due_date_missing', tuple(ClientReceiptReviewCandidate(
                str(row['obligation_identity']), str(row['obligation_type']), None,
            ) for row in open_rows if row.get('due_date') is None),
        ))
    month_matched = [
        row for row in open_rows
        if _is_same_month(trans_date, row.get("due_date"))
    ]
    month_exact = [
        row for row in month_matched if int(row["amount_due_ntd"]) == candidate.amount.amount
    ]
    if len(month_exact) == 1:
        return _ready_candidate(
            candidate,
            (str(month_exact[0]["obligation_identity"]),),
            "exact-open-client-obligation-in-transaction-month",
        )
    if len(month_matched) == 1:
        target = str(month_matched[0]["obligation_identity"])
        due_amount = int(month_matched[0]["amount_due_ntd"])
        diff = candidate.amount.amount - due_amount
        diff_tag = f"diff_over:{diff}" if diff > 0 else f"diff_under:{abs(diff)}"
        evidence = tuple(
            sorted(
                set((
                    *candidate.evidence,
                    "month-matched-client-obligation",
                    diff_tag,
                ))
            )
        )
        reason = "client_receipt_overpaid" if diff > 0 else "client_receipt_underpaid"
        return replace(candidate, target_identities=(target,), evidence=evidence,
                       client_receipt_review=ClientReceiptReviewDiagnostic(reason))
    if len(month_matched) > 1:
        targets = tuple(
            sorted(str(row["obligation_identity"]) for row in month_matched)
        )
        evidence = tuple(
            sorted(set((*candidate.evidence, "month-matched-client-obligations")))
        )
        if len(month_exact) > 1:
            diagnostic = ClientReceiptReviewDiagnostic(
                "sinopac_client_receipt_multiple_month_candidates",
                tuple(ClientReceiptReviewCandidate(
                    str(row["obligation_identity"]), str(row["obligation_type"]), str(row["due_date"]),
                ) for row in month_exact),
            )
        else:
            diagnostic = ClientReceiptReviewDiagnostic("sinopac_client_receipt_multiple_month_candidates")
        return replace(candidate, target_identities=targets, evidence=evidence, client_receipt_review=diagnostic)
    if len(rows) == 1:
        return _ready_candidate(candidate, (str(rows[0]["obligation_identity"]),), "exact-open-client-obligation")
    return replace(candidate, client_receipt_review=ClientReceiptReviewDiagnostic(
        "sinopac_client_receipt_month_no_match",
    ))


def _virtual_account_case_info(connection, row_identity):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT format_id,cancellation_code,bank_references,transaction_date,currency "
            "FROM finance_import_rows WHERE id=%s",
            (_row_id(row_identity),),
        )
        row = cursor.fetchone()
        if row is None:
            return None, None, None
        source = dict(row)
        source["bank_references"] = _json_object(source.get("bank_references"))
        cancellation_code = resolve_finance_cancellation_code(source)[
            "cancellation_code"
        ]
        resolution = resolve_client_virtual_account(cursor, cancellation_code)
    if resolution["result"] != "resolved":
        return None, row.get("transaction_date"), None
    blocker = ('bank_transaction_date_missing' if row.get('transaction_date') is None
               else 'bank_currency_not_twd' if row.get('currency') is not None and str(row['currency']).upper() not in {'TWD','NTD'}
               else None)
    return str(resolution["case_no"]), row.get("transaction_date"), blocker


def _without_redundant_historical_baseline(rows):
    has_stage_or_formal = any(
        not str(row.get("obligation_identity", "")).startswith("historical-service:")
        for row in rows
    )
    if not has_stage_or_formal:
        return rows
    return tuple(
        row
        for row in rows
        if not str(row.get("obligation_identity", "")).startswith("historical-service:")
    )


def _client_receipt_open_obligations_query(client_id, case_no):
    base = (
        "SELECT obligation.obligation_identity,obligation.due_date,obligation.amount_due_ntd,obligation.obligation_type "
        "FROM client_obligations obligation "
    )
    predicates = (
        "AND obligation.direction='receivable_from_client' "
        "AND obligation.status='open' "
        "ORDER BY obligation.due_date,obligation.obligation_identity"
    )
    if client_id is not None:
        return (
            base
            + "JOIN orders order_row ON order_row.case_no=obligation.case_no "
            + "WHERE order_row.client_id=%s "
            + predicates,
            (client_id,),
        )
    return (
        base + "WHERE obligation.case_no=%s " + predicates,
        (case_no,),
    )


def _virtual_account_case_no(connection, row_identity):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT format_id,cancellation_code,bank_references "
            "FROM finance_import_rows WHERE id=%s",
            (_row_id(row_identity),),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        source = dict(row)
        source["bank_references"] = _json_object(source.get("bank_references"))
        cancellation_code = resolve_finance_cancellation_code(source)[
            "cancellation_code"
        ]
        resolution = resolve_client_virtual_account(cursor, cancellation_code)
    if resolution["result"] != "resolved":
        return None
    return str(resolution["case_no"])


def _client_receipt_target_query(client_id, case_no, amount_ntd):
    base = (
        "SELECT obligation.obligation_identity,obligation.due_date "
        "FROM client_obligations obligation "
    )
    predicates = (
        "AND obligation.direction='receivable_from_client' "
        "AND obligation.status='open' "
        "AND obligation.amount_due_ntd=%s "
        "AND NOT ("
        "obligation.obligation_identity LIKE 'historical-service:%%:client:receivable_from_client' "
        "AND EXISTS ("
        "SELECT 1 FROM client_obligations stage_obligation "
        "WHERE stage_obligation.case_no=obligation.case_no "
        "AND stage_obligation.direction='receivable_from_client' "
        "AND stage_obligation.status='open' "
        "AND stage_obligation.obligation_type IN ('deposit','first','second')"
        ")"
        ") "
        "ORDER BY obligation.obligation_identity"
    )
    if client_id is not None:
        return (
            base
            + "JOIN orders order_row ON order_row.case_no=obligation.case_no "
            + "WHERE order_row.client_id=%s "
            + predicates,
            (client_id, amount_ntd),
        )
    return (
        base + "WHERE obligation.case_no=%s " + predicates,
        (case_no, amount_ntd),
    )


def _resolve_client_subsidy_return(connection, candidate):
    client_id = _single_prefixed_identity(candidate, "client:")
    memo_identified = TAISHIN_CLIENT_SUBSIDY_MEMO_REASON in candidate.evidence
    if not memo_identified and (client_id is None or _VERIFIED_OUTGOING_NAME_EVIDENCE.isdisjoint(candidate.evidence)):
        return candidate
    memo_scoped, case_no, trans_date = _sinopac_outgoing_case_info(
        connection, candidate.row_identity
    )
    with connection.cursor() as cursor:
        cursor.execute('SELECT format_id,currency FROM finance_import_rows WHERE id=%s', (_row_id(candidate.row_identity),))
        source = cursor.fetchone() or {}
    is_taishin = source.get('format_id') == 'taishin'
    pending = replace(candidate, disposition=FinanceImportDisposition.BUSINESS_PENDING, available_actions=('resolve_owning_domain_target',)) if is_taishin else candidate
    if is_taishin:
        if candidate.disposition in {FinanceImportDisposition.EXISTING, FinanceImportDisposition.BLOCKED}:
            return candidate
        if trans_date is None:
            return replace(pending, pending_reason='bank_transaction_date_missing')
        if source.get('currency') is not None and str(source['currency']).upper() not in {'TWD','NTD'}:
            return replace(pending, pending_reason='bank_currency_not_twd')
    if (memo_identified or memo_scoped) and case_no is None:
        return replace(pending, pending_reason='client_subsidy_memo_recipient_unconfirmed')
    if is_taishin:
        from infrastructure.mysql.client_refund_reversal_repository import _verify_taishin_subsidy_cases
        with connection.cursor() as cursor:
            cursor.execute('SELECT id,format_id,memo FROM finance_import_rows WHERE id=%s', (_row_id(candidate.row_identity),))
            memo_source = cursor.fetchone()
            try:
                if memo_source is None:
                    raise ValueError('bank_fact_not_eligible')
                _verify_taishin_subsidy_cases(cursor, ({**memo_source, 'effective_classification_type':'client_subsidy_return'},), expected_case_no=case_no)
            except ValueError as error:
                return replace(pending, pending_reason=str(error))
    rows = _load_client_refund_targets(
        connection, client_id, case_no, subsidy_return=True
    )
    if trans_date is None:
        return replace(candidate, pending_reason='bank_transaction_date_missing')
    if not rows:
        return replace(pending, pending_reason='outgoing_client_refund_no_open_obligation')
    if is_taishin and any(row['due_date'] is None for row in rows):
        return replace(pending, pending_reason='due_date_missing')
    if not any(_is_same_month(trans_date, row['due_date']) for row in rows):
        reason = 'due_date_missing' if any(row['due_date'] is None for row in rows) else 'outgoing_client_refund_month_no_match'
        return replace(pending, pending_reason=reason)
    matches = _monthly_payout_target_candidates(rows, trans_date, candidate.amount.amount, by_case=True)
    if len(matches) != 1:
        reason = 'outgoing_client_refund_multiple_fee_matches' if matches else 'outgoing_client_refund_amount_mismatch'
        return replace(pending, pending_reason=reason)
    targets = matches[0]
    ready = _ready_candidate(
        candidate,
        targets,
        "unique-monthly-client-subsidy-return-obligations",
    )
    workflow = ClientRefundReversalWorkflow(
        MySqlClientRefundReversalRepository(connection), BorrowedTransactionUnitOfWork,
    )
    try:
        preview = workflow.preview(
            _client_subsidy_return_selection(connection, ready),
            CorrelationId(f"finance-import-subsidy-preview:{candidate.row_identity}"),
        )
    except ClientRefundReversalError as error:
        if error.error.category is not ErrorCategory.DOMAIN_BLOCKED:
            raise
        # Funding/eligibility is owned by Client Finance. Leave this bank fact
        # pending so unrelated valid candidates can still post in the same batch.
        return replace(pending, pending_reason=error.error.code)
    total = sum(
        int(row["amount_due_ntd"])
        for row in rows
        if str(row["obligation_identity"]) in targets
    )
    if preview.candidate.transfer_fee.amount != total - candidate.amount.amount:
        return replace(pending,pending_reason='outgoing_client_refund_amount_mismatch') if is_taishin else candidate
    return replace(ready,pending_reason=None) if is_taishin else ready


def _resolve_client_refund(connection, candidate):
    client_id = _single_prefixed_identity(candidate, "client:")
    if client_id is None:
        return candidate
    memo_scoped, case_no, trans_date = _sinopac_outgoing_case_info(connection, candidate.row_identity)
    with connection.cursor() as cursor:
        cursor.execute("SELECT format_id,currency FROM finance_import_rows WHERE id=%s", (_row_id(candidate.row_identity),))
        source = cursor.fetchone() or {}
    is_sinopac = source.get("format_id") == "sinopac"
    if is_sinopac and candidate.disposition in {FinanceImportDisposition.EXISTING, FinanceImportDisposition.BLOCKED}:
        return candidate
    if not is_sinopac and _VERIFIED_OUTGOING_NAME_EVIDENCE.isdisjoint(candidate.evidence):
        return candidate
    if memo_scoped and case_no is None:
        return candidate
    rows = _load_client_refund_targets(
        connection, client_id, case_no
    )
    if is_sinopac:
        pending = replace(candidate, disposition=FinanceImportDisposition.BUSINESS_PENDING,
                          available_actions=("resolve_owning_domain_target",), pending_reason=None)
        if trans_date is None:
            return replace(pending, pending_reason="bank_transaction_date_missing")
        if source.get("currency") is not None and str(source["currency"]).upper() not in {"TWD", "NTD"}:
            return replace(pending, pending_reason="bank_currency_not_twd")
        if not rows:
            return replace(pending, pending_reason="outgoing_client_refund_no_open_obligation")
        if any(row.get("due_date") is None for row in rows):
            return replace(pending, pending_reason="due_date_missing")
        if not any(_is_same_month(trans_date, row["due_date"]) for row in rows):
            return replace(pending, pending_reason="outgoing_client_refund_month_no_match")
        matches = _monthly_payout_target_candidates(rows, trans_date, candidate.amount.amount, by_case=True)
        if len(matches) != 1:
            reason = "outgoing_client_refund_multiple_fee_matches" if matches else "outgoing_client_refund_amount_mismatch"
            return replace(pending, pending_reason=reason)
        targets = matches[0]
    else:
        targets = _unique_monthly_payout_targets(rows, trans_date, candidate.amount.amount, by_case=True)
    if targets is None:
        return candidate
    selected_total = sum(
        int(row["amount_due_ntd"])
        for row in rows
        if str(row["obligation_identity"]) in targets
    )
    diff = selected_total - candidate.amount.amount

    evidence = (
        "unique-client-refund-obligation-balance"
        if diff == 0
        else "unique-client-refund-transfer-fee-reconciled"
    )
    ready = _ready_candidate(candidate, targets, evidence)
    if is_sinopac:
        workflow = ClientRefundReversalWorkflow(MySqlClientRefundReversalRepository(connection), BorrowedTransactionUnitOfWork)
        try:
            workflow.preview(_client_refund_selection(connection, ready),
                             CorrelationId(f"finance-import-refund-preview:{candidate.row_identity}"))
        except ClientRefundReversalError as error:
            if error.error.category is not ErrorCategory.DOMAIN_BLOCKED:
                raise
            return replace(pending, pending_reason=error.error.code)
    return replace(ready, pending_reason=None) if is_sinopac else ready


def _json_object(value):
    decoded = json.loads(value) if isinstance(value, str) else value
    return decoded if isinstance(decoded, dict) else {}


def _sinopac_outgoing_case_info(connection, row_identity, *, taishin_staff=False):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT format_id,direction,memo,transaction_date FROM finance_import_rows WHERE id=%s",
            (_row_id(row_identity),),
        )
        row = cursor.fetchone()
        if row is None:
            return True, None, None
        trans_date = row.get("transaction_date")
        if row["format_id"] not in {"sinopac", "taishin"}:
            return False, None, trans_date
        if row["direction"] != "outgoing":
            return True, None, trans_date
        if taishin_staff and row["format_id"] == "taishin":
            return False, None, trans_date
        suffixes = sinopac_memo_case_suffixes(row["memo"])
        if not suffixes:
            return False, None, trans_date
        if len(suffixes) > 1:
            return True, None, trans_date
        resolution = resolve_client_virtual_account_suffix(cursor, next(iter(suffixes)))
    if resolution["result"] != "resolved":
        return True, None, trans_date
    return True, str(resolution["case_no"]), trans_date


def _load_client_refund_targets(
    connection, client_id, case_no=None, *, subsidy_return=False
):
    scope_predicates = []
    parameters = []
    if client_id is not None:
        scope_predicates.append("AND order_row.client_id=%s ")
        parameters.append(client_id)
    if case_no is not None:
        scope_predicates.append("AND obligation.case_no=%s ")
        parameters.append(case_no)
    if not parameters:
        return ()
    type_predicate = (
        "AND obligation.obligation_type='subsidy_return' "
        if subsidy_return
        else "AND obligation.obligation_type IN ('refund','adjustment') "
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT obligation.case_no,obligation.obligation_identity,"
            "obligation.due_date,obligation.amount_due_ntd FROM client_obligations obligation "
            "JOIN orders order_row ON order_row.case_no=obligation.case_no "
            "WHERE obligation.direction='payable_to_client' "
            "AND obligation.status='open' AND obligation.amount_due_ntd>0 "
            + type_predicate
            + "".join(scope_predicates)
            + "ORDER BY obligation.case_no,obligation.due_date,obligation.obligation_identity",
            tuple(parameters),
        )
        return tuple(cursor.fetchall())


def _unique_monthly_payout_targets(rows, trans_date, amount, *, by_case=False):
    eligible = _monthly_payout_target_candidates(rows, trans_date, amount, by_case=by_case)
    return eligible[0] if len(eligible) == 1 else None


def _monthly_payout_target_candidates(rows, trans_date, amount, *, by_case=False):
    groups = {}
    for row in rows:
        if _is_same_month(trans_date, row["due_date"]):
            group = row["case_no"] if by_case else None
            groups.setdefault(group, []).append(row)

    eligible = []
    for group in groups.values():
        selections = [(row,) for row in group]
        if len(group) > 1:
            selections.append(tuple(group))
        for selection in selections:
            total = sum(int(row["amount_due_ntd"]) for row in selection)
            if 0 <= total - amount <= 100:
                eligible.append(tuple(str(row["obligation_identity"]) for row in selection))
    return tuple(eligible)


def _resolve_staff_payout(connection, candidate):
    from infrastructure.mysql.staff_payable_correction_sql import effective_staff_obligation_amount
    staff_id = _single_prefixed_identity(candidate, "staff:")
    if staff_id is None:
        return candidate
    memo_scoped, case_no, trans_date = _sinopac_outgoing_case_info(
        connection, candidate.row_identity, taishin_staff=True
    )
    if candidate.subsidy_preflight is not None:
        case_no = candidate.subsidy_preflight.case_no
    with connection.cursor() as cursor:
        cursor.execute('SELECT format_id,currency FROM finance_import_rows WHERE id=%s', (_row_id(candidate.row_identity),))
        source = cursor.fetchone() or {}
    is_sinopac = source.get('format_id') == 'sinopac'
    is_taishin = source.get('format_id') == 'taishin'
    if (is_sinopac or is_taishin) and candidate.disposition in {FinanceImportDisposition.EXISTING,FinanceImportDisposition.BLOCKED}:
        return candidate
    if not (is_sinopac or is_taishin) and _VERIFIED_OUTGOING_NAME_EVIDENCE.isdisjoint(candidate.evidence):
        return candidate
    if memo_scoped and case_no is None:
        return candidate
    case_predicate = "AND obligation.case_no=%s " if case_no is not None else ""
    parameters = (staff_id, case_no) if case_no is not None else (staff_id,)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT obligation.obligation_identity,obligation.due_date,"
            "EXISTS(SELECT 1 FROM staff_obligation_installments i WHERE i.obligation_identity=obligation.obligation_identity) AS has_installments,"
            "COALESCE((SELECT plan.scheme FROM finance_case_subsidy_plan_events plan WHERE plan.case_no=obligation.case_no ORDER BY plan.version DESC LIMIT 1),'')='split' AS requires_funding_split,"
            + effective_staff_obligation_amount('obligation') + " AS full_amount_ntd,COALESCE(projection.net_paid_ntd,0) AS settled_total_ntd,"
            "COALESCE(projection.balance_ntd,obligation.amount_due_ntd) "
            "AS amount_due_ntd "
            "FROM staff_obligations obligation "
            "LEFT JOIN staff_payable_projections projection "
            "ON projection.obligation_identity=obligation.obligation_identity "
            "WHERE obligation.staff_id=%s "
            "AND obligation.direction='payable_to_staff' "
            "AND obligation.status<>'cancelled' "
            "AND obligation.amount_due_ntd>0 "
            "AND (projection.status IS NULL OR projection.status IN ('payable','partially_paid')) "
            + case_predicate +
            "ORDER BY obligation.obligation_identity",
            parameters,
        )
        rows = tuple(cursor.fetchall())
        if is_sinopac or is_taishin:
            from infrastructure.mysql.staff_payout_repository import query_staff_funding_portions
            funding = 'client' if is_sinopac else 'subsidy'
            scoped_rows = []
            for row in rows:
                if not row.get('has_installments'):
                    if row.get('requires_funding_split'):
                        return replace(candidate, disposition=FinanceImportDisposition.BUSINESS_PENDING,
                            available_actions=('resolve_owning_domain_target',), pending_reason='staff_installment_funding_unconfirmed')
                    scoped_rows.append(row)
                    continue
                try:
                    portions = query_staff_funding_portions(cursor, row['obligation_identity'],
                        settled_total=row.get('settled_total_ntd'), amount_total=row.get('full_amount_ntd'))
                    if any(p.remaining_ntd is None for p in portions):
                        raise ValueError('staff_installment_funding_unconfirmed')
                except ValueError as error:
                    return replace(candidate, disposition=FinanceImportDisposition.BUSINESS_PENDING,
                        available_actions=('resolve_owning_domain_target',), pending_reason=str(error))
                scoped_rows.extend({**row, 'due_date': p.due_date, 'amount_due_ntd': p.remaining_ntd}
                    for p in portions if p.funding_kind == funding and p.remaining_ntd > 0)
            rows = tuple(scoped_rows)
    if is_sinopac or is_taishin:
        if trans_date is None:
            return replace(candidate, disposition=FinanceImportDisposition.BUSINESS_PENDING, available_actions=('resolve_owning_domain_target',), pending_reason='bank_transaction_date_missing')
        if source.get('currency') is not None and str(source['currency']).upper() not in {'TWD','NTD'}:
            return replace(candidate, disposition=FinanceImportDisposition.BUSINESS_PENDING, available_actions=('resolve_owning_domain_target',), pending_reason='bank_currency_not_twd')
        if is_taishin:
            from infrastructure.mysql.staff_payout_repository import _verify_taishin_memo_recipients
            with connection.cursor() as cursor:
                cursor.execute('SELECT id,format_id,memo FROM finance_import_rows WHERE id=%s', (_row_id(candidate.row_identity),))
                memo_source = cursor.fetchone()
                try:
                    if memo_source is None:
                        raise ValueError('outgoing_bank_fact_not_eligible')
                    verified = _verify_taishin_memo_recipients(cursor, (memo_source,), False)
                    if verified[0].get('taishin_memo_staff_id') != staff_id:
                        raise ValueError('cross_staff_allocation_forbidden')
                except ValueError as error:
                    return replace(candidate, disposition=FinanceImportDisposition.BUSINESS_PENDING, available_actions=('resolve_owning_domain_target',), pending_reason=str(error))
        if not rows:
            return replace(candidate, disposition=FinanceImportDisposition.BUSINESS_PENDING, available_actions=('resolve_owning_domain_target',), pending_reason='outgoing_staff_payout_no_open_obligation')
        if any(row.get('due_date') is None for row in rows):
            return replace(candidate, disposition=FinanceImportDisposition.BUSINESS_PENDING, available_actions=('resolve_owning_domain_target',), pending_reason='due_date_missing')
        if not any(_is_same_month(trans_date,row['due_date']) for row in rows):
            return replace(candidate, disposition=FinanceImportDisposition.BUSINESS_PENDING, available_actions=('resolve_owning_domain_target',), pending_reason='outgoing_staff_payout_month_no_match')
        matches = _monthly_payout_target_candidates(rows,trans_date,candidate.amount.amount)
        if len(matches) != 1:
            reason = 'outgoing_staff_payout_multiple_fee_matches' if matches else 'staff_payout_amount_mismatch'
            return replace(candidate,disposition=FinanceImportDisposition.BUSINESS_PENDING,available_actions=('resolve_owning_domain_target',),pending_reason=reason)
        targets = matches[0]
    else:
        targets = _unique_monthly_payout_targets(rows, trans_date, candidate.amount.amount)
    if targets is None:
        return candidate
    total = sum(
        int(row["amount_due_ntd"])
        for row in rows
        if str(row["obligation_identity"]) in targets
    )
    diff = total - candidate.amount.amount

    evidence = (
        "exact-staff-payable-total"
        if diff == 0
        else "unique-staff-payout-transfer-fee-reconciled"
    )
    ready = _ready_candidate(candidate,targets,evidence)
    if is_sinopac or is_taishin:
        workflow = StaffPayoutReconciliationWorkflow(MySqlStaffPayoutRepository(connection),BorrowedTransactionUnitOfWork)
        try:
            workflow.preview(StaffPayoutSelection(StaffPayoutEventType.PAYOUT,(_row_id(candidate.row_identity),),tuple(sorted(targets))),CorrelationId(f'finance-import-staff-preview:{candidate.row_identity}'))
        except StaffPayoutReconciliationError as error:
            if error.error.category is not ErrorCategory.DOMAIN_BLOCKED:
                raise
            return replace(candidate,disposition=FinanceImportDisposition.BUSINESS_PENDING,available_actions=('resolve_owning_domain_target',),pending_reason=error.error.code)
    return replace(ready,pending_reason=None) if is_sinopac or is_taishin else ready


def _resolve_government_subsidy(connection, candidate):
    # A bank date/amount cannot identify the government's month/quarter/year.
    # Staff selects the entire period in the owning workbench; importer keeps the fact pending.
    return candidate


def _single_prefixed_identity(candidate, prefix):
    identities = candidate.target_identities
    if len(identities) != 1 or not identities[0].startswith(prefix):
        return None
    value = identities[0].removeprefix(prefix)
    if not value.isdigit() or int(value) <= 0:
        return None
    return int(value)


def _ready_candidate(candidate, targets, evidence):
    return replace(
        candidate,
        disposition=FinanceImportDisposition.CREATE,
        target_identities=tuple(sorted(targets)),
        evidence=tuple(sorted(set((*candidate.evidence, evidence)))),
        available_actions=("preview_apply",),
    )


def _blocked_candidate(candidate, blocker):
    return replace(
        candidate,
        disposition=FinanceImportDisposition.BLOCKED,
        integrity_violations=tuple(
            sorted(set((*candidate.integrity_violations, blocker)))
        ),
    )


def _client_selection(connection, candidate):
    targets = _target_identities(candidate)
    placeholders = ",".join("%s" for _ in targets)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT case_no,obligation_type FROM client_obligations "
            f"WHERE obligation_identity IN ({placeholders}) "
            "AND direction='receivable_from_client' AND status='open' "
            "ORDER BY obligation_identity",
            targets,
        )
        rows = tuple(cursor.fetchall())
    case_no, stage = _single_client_scope(rows, targets)
    return ReconciliationSelection(
        case_no,
        stage,
        (_row_id(candidate.row_identity),),
        targets,
        (
            candidate.allow_client_receipt_overage
            if isinstance(candidate, FinanceImportCorrectionCandidate)
            else False
        ),
    )


def _client_subsidy_return_selection(connection, candidate):
    targets = _target_identities(candidate)
    placeholders = ",".join("%s" for _ in targets)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT case_no,obligation_type FROM client_obligations "
            f"WHERE obligation_identity IN ({placeholders}) "
            "AND direction='payable_to_client' "
            "ORDER BY obligation_identity",
            targets,
        )
        rows = tuple(cursor.fetchall())
    case_no = _single_subsidy_return_scope(rows, targets)
    return ClientRefundReversalSelection(
        case_no,
        (ClientFinanceCorrectionType.REFUND_OVERAGE
         if isinstance(candidate, (FinanceImportCorrectionCandidate, FinanceImportCorrectionSelection)) and candidate.allow_refund_overage_recovery
         else ClientFinanceCorrectionType.REFUND),
        ClientRefundPurpose.SUBSIDY_RETURN,
        bank_fact_identities=(_row_id(candidate.row_identity),),
        obligation_identities=targets,
        allow_partial_refund_recovery=(candidate.allow_partial_refund_recovery
            if isinstance(candidate, (FinanceImportCorrectionCandidate, FinanceImportCorrectionSelection)) else False),
    )


def _client_refund_selection(connection, candidate):
    targets = _target_identities(candidate)
    placeholders = ",".join("%s" for _ in targets)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT case_no,obligation_type FROM client_obligations "
            f"WHERE obligation_identity IN ({placeholders}) "
            "AND direction='payable_to_client' AND status='open' "
            "AND obligation_type IN ('refund','adjustment') ORDER BY obligation_identity",
            targets,
        )
        rows = tuple(cursor.fetchall())
    case_no = _single_client_refund_scope(rows, targets)
    return ClientRefundReversalSelection(
        case_no,
        (
            ClientFinanceCorrectionType.REFUND_OVERAGE
            if isinstance(candidate, (FinanceImportCorrectionCandidate, FinanceImportCorrectionSelection))
            and candidate.allow_refund_overage_recovery
            else ClientFinanceCorrectionType.REFUND
        ),
        ClientRefundPurpose.CUSTOMER_REFUND,
        bank_fact_identities=(_row_id(candidate.row_identity),),
        obligation_identities=targets,
        allow_partial_refund_recovery=(
            candidate.allow_partial_refund_recovery
            if isinstance(candidate, (FinanceImportCorrectionCandidate, FinanceImportCorrectionSelection))
            else False
        ),
    )


def _client_refund_return_selection(connection, candidate):
    if not isinstance(candidate, FinanceImportCorrectionCandidate):
        raise ValueError("client_refund_return_manual_correction_required")
    ledger_identity = candidate.refund_ledger_entry_identity
    if ledger_identity is None:
        raise ValueError("refund_return_ledger_target_required")
    return ClientRefundReversalSelection(
        _refund_return_case_no(connection, ledger_identity),
        ClientFinanceCorrectionType.REFUND_RETURN,
        bank_fact_identities=(_row_id(candidate.row_identity),),
        reversal_target_identities=(ledger_identity,),
    )


def _refund_return_case_no(connection, ledger_identity):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT case_no FROM client_ledger_entries WHERE id=%s AND entry_type='refund'",
            (_positive_ledger_id(ledger_identity),),
        )
        row = cursor.fetchone()
    if row is None:
        raise ValueError("refund_return_ledger_target_not_found")
    return str(row["case_no"])


def _positive_ledger_id(identity):
    if not isinstance(identity, str) or not identity.isdigit() or int(identity) <= 0:
        raise ValueError("refund_return_ledger_target_invalid")
    return int(identity)


def _single_client_scope(rows, targets):
    if len(rows) != len(targets):
        raise ValueError("correction_target_not_found")
    cases = {str(row["case_no"]) for row in rows}
    stages = {str(row["obligation_type"]) for row in rows}
    if len(cases) != 1 or len(stages) != 1:
        raise ValueError("correction_targets_cross_owning_domain")
    try:
        return cases.pop(), PaymentStage(stages.pop())
    except ValueError as error:
        raise ValueError("classification_target_owner_mismatch") from error


def _single_subsidy_return_scope(rows, targets):
    if len(rows) != len(targets):
        raise ValueError("correction_target_not_found")
    cases = {str(row["case_no"]) for row in rows}
    types = {str(row["obligation_type"]) for row in rows}
    if len(cases) != 1 or types != {"subsidy_return"}:
        raise ValueError("classification_target_owner_mismatch")
    return cases.pop()


def _single_client_refund_scope(rows, targets):
    if len(rows) != len(targets):
        raise ValueError("correction_target_not_found")
    cases = {str(row["case_no"]) for row in rows}
    types = {str(row["obligation_type"]) for row in rows}
    if len(cases) != 1 or not types <= {"refund", "adjustment"}:
        raise ValueError("classification_target_owner_mismatch")
    return cases.pop()


def _client_request(candidate, selection, preview, context):
    return ClientReconciliationApplyRequest(
        selection,
        ExpectedVersion(preview.account_version),
        preview.fingerprint,
        _child_key(context, candidate, "client-receipt"),
        context.actor,
        context.reason,
        context.correlation_id,
    )


def _client_subsidy_return_request(
    candidate,
    selection,
    preview,
    context,
):
    return ClientRefundReversalApplyRequest(
        selection,
        ExpectedVersion(preview.account_version),
        preview.fingerprint,
        _child_key(context, candidate, "client-subsidy-return"),
        context.actor,
        context.reason,
        context.correlation_id,
    )


def _client_refund_request(candidate, selection, preview, context):
    return ClientRefundReversalApplyRequest(
        selection,
        ExpectedVersion(preview.account_version),
        preview.fingerprint,
        _child_key(context, candidate, "client-refund"),
        context.actor,
        context.reason,
        context.correlation_id,
    )


def _client_refund_return_request(candidate, selection, preview, context):
    return ClientRefundReversalApplyRequest(
        selection,
        ExpectedVersion(preview.account_version),
        preview.fingerprint,
        _child_key(context, candidate, "client-refund-return"),
        context.actor,
        context.reason,
        context.correlation_id,
    )


def _staff_request(candidate, selection, preview, context):
    return StaffPayoutApplyRequest(
        selection,
        ExpectedVersion(preview.staff_payables_version),
        ExpectedVersion(preview.bank_facts_version),
        preview.fingerprint,
        _child_key(context, candidate, "staff-payout"),
        context.actor,
        context.reason,
        context.correlation_id,
    )


def _government_subsidy_request(candidate, intent, preview, context):
    return GovernmentSubsidyReceiptApplyRequest(
        intent,
        ExpectedVersion(preview.candidate.expected_batch_version),
        preview.fingerprint,
        _child_key(context, candidate, "government-subsidy-receipt"),
        context.actor,
        context.reason,
        context.correlation_id,
    )


def _client_result(candidate, receipt):
    if isinstance(candidate, FinanceImportCorrectionCandidate):
        if receipt.status is not ReconciliationStatus.EXACT:
            raise ValueError("allocation_not_exact")
        return receipt.ledger_entry_count
    if receipt.status is not ReconciliationStatus.EXACT:
        return FinanceImportDispatchResult(
            candidate.row_identity,
            FinanceDispatchOutcome.PENDING,
        )
    return FinanceImportDispatchResult(
        candidate.row_identity,
        FinanceDispatchOutcome.RECONCILED,
        f"client-finance:{receipt.settlement_identity.value}",
    )


def _staff_result(candidate, receipt):
    if isinstance(candidate, FinanceImportCorrectionCandidate):
        return receipt.event_count
    reference = f"staff-payables:{receipt.preview_fingerprint.value}"
    return FinanceImportDispatchResult(
        candidate.row_identity,
        FinanceDispatchOutcome.RECONCILED,
        reference,
    )


def _client_subsidy_return_result(candidate, receipt):
    if isinstance(candidate, FinanceImportCorrectionCandidate):
        return receipt.ledger_entry_count
    reference = f"client-finance:{receipt.correction_identity.value}"
    return FinanceImportDispatchResult(
        candidate.row_identity,
        FinanceDispatchOutcome.RECONCILED,
        reference,
    )


def _government_subsidy_result(candidate, receipt):
    if isinstance(candidate, FinanceImportCorrectionCandidate):
        return receipt.allocation_count
    reference = f"government-subsidy:{receipt.transaction_id}"
    return FinanceImportDispatchResult(
        candidate.row_identity,
        FinanceDispatchOutcome.RECONCILED,
        reference,
    )


def _unsupported_result(candidate):
    if isinstance(candidate, FinanceImportCorrectionCandidate):
        raise ValueError(_unavailable_owner_code(candidate))
    return FinanceImportDispatchResult(
        candidate.row_identity,
        FinanceDispatchOutcome.PENDING,
    )


def _unavailable_owner_code(candidate):
    del candidate
    return "owning_domain_posting_not_implemented"


def _typed_domain_result(candidate, error, *, reason_code=None):
    if error.retryable:
        raise FinanceImportRepositoryUnavailable(error.message)
    if isinstance(candidate, FinanceImportCorrectionCandidate):
        raise ValueError(error.code)
    outcome = (
        FinanceDispatchOutcome.CONFLICT
        if error.category is ErrorCategory.CONFLICT
        else FinanceDispatchOutcome.REJECTED
    )
    return FinanceImportDispatchResult(candidate.row_identity, outcome, reason_code=reason_code or error.code)


def _government_subsidy_domain_result(candidate, error):
    if isinstance(candidate, FinanceImportCorrectionCandidate):
        raise ValueError(error.code.value)
    outcome = (
        FinanceDispatchOutcome.PENDING
        if error.code is GovernmentSubsidyErrorCode.REVIEW_REQUIRED
        else FinanceDispatchOutcome.REJECTED
    )
    return FinanceImportDispatchResult(candidate.row_identity, outcome, reason_code=error.code.value)


def _target_identities(candidate):
    if isinstance(candidate, FinanceImportCorrectionSelection):
        return candidate.target_obligation_identities
    if isinstance(candidate, FinanceImportCorrectionCandidate) and candidate.refund_preview is not None:
        return candidate.refund_preview.obligation_identities
    if isinstance(candidate, FinanceImportCorrectionCandidate):
        return tuple(item.obligation_identity for item in candidate.allocations)
    if isinstance(candidate, CanonicalFinanceImportRow):
        return candidate.target_identities
    raise TypeError("unsupported Finance Import posting candidate")


def _candidate_amount(candidate):
    if isinstance(candidate, FinanceImportCorrectionCandidate):
        return candidate.bank_amount.amount
    if isinstance(candidate, CanonicalFinanceImportRow):
        return candidate.amount.amount
    raise TypeError("unsupported Finance Import posting candidate")


def _government_subsidy_batch_id(candidate):
    if not isinstance(candidate, FinanceImportCorrectionCandidate):
        return None
    targets = _target_identities(candidate)
    if len(targets) != 1:
        raise ValueError("government_subsidy_single_batch_required")
    prefix = "government-subsidy-batch:"
    identity = targets[0]
    if not identity.startswith(prefix):
        raise ValueError("classification_target_owner_mismatch")
    batch_id = identity.removeprefix(prefix)
    if not batch_id.isdigit() or int(batch_id) <= 0:
        raise ValueError("correction_target_not_found")
    return int(batch_id)


def _child_key(context, candidate, purpose):
    payload = (
        f"{context.idempotency_key.value}:{purpose}:{candidate.row_identity}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return IdempotencyKey(f"finance-import:{digest}")


def _request_reason(request):
    direct_reason = getattr(request, "reason", None)
    if isinstance(direct_reason, str):
        return direct_reason
    return request.selection.reason


def _row_id(identity):
    prefix = "finance-import-row:"
    value = str(identity)
    if value.startswith(prefix):
        value = value.removeprefix(prefix)
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("invalid_finance_import_identity")
    return value


__all__ = [
    "BorrowedTransactionUnitOfWork",
    "MySqlFinanceImportOwningDomainComposite",
]
