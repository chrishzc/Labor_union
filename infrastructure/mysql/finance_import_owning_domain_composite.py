"""Finance Import posting through owning Domains inside one borrowed transaction."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
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
from domains.client_finance.subsidy_advance import (
    is_first_month_of_quarter,
    subsidy_advance_due_date,
)
from domains.finance_import.correction import FinanceImportCorrectionCandidate
from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
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
from infrastructure.mysql.government_subsidy_anomaly_recheck_sink import (
    MySqlGovernmentSubsidyAnomalyRecheckSink,
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
from shared_kernel.errors import ErrorCategory
from domains.finance_import.cancellation_code import (
    resolve_finance_cancellation_code,
)
from subsystems.client_finance.virtual_account_resolution import (
    resolve_client_virtual_account,
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

    def resolve(self, candidate):
        if not isinstance(candidate, CanonicalFinanceImportRow):
            raise TypeError("unsupported Finance Import resolution candidate")
        if candidate.disposition is not FinanceImportDisposition.BUSINESS_PENDING:
            return candidate
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
            return _typed_domain_result(candidate, error.error)
        except GovernmentSubsidyDomainError as error:
            return _government_subsidy_domain_result(candidate, error)

    def _post(self, candidate, context):
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
        selection = _subsidy_payout_selection(
            self._connection,
            candidate,
            selection,
        )
        repository = MySqlClientRefundReversalRepository(self._connection)
        workflow = ClientRefundReversalWorkflow(
            repository,
            BorrowedTransactionUnitOfWork,
        )
        preview = workflow.preview(selection, context.correlation_id)
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
        preview = workflow.preview(selection, context.correlation_id)
        request = _client_refund_request(candidate, selection, preview, context)
        repository.bind_apply_request(request)
        try:
            receipt = workflow.apply(request)
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
        intent = ReceiptIntent(
            int(_row_id(candidate.row_identity)),
            _government_subsidy_batch_id(candidate),
        )
        repository = MySqlGovernmentSubsidyRepository(self._connection)
        workflow = GovernmentSubsidyLedgerWorkflow(
            repository,
            BorrowedTransactionUnitOfWork,
            MySqlGovernmentSubsidyAnomalyRecheckSink(self._connection),
        )
        preview = workflow.preview_receipt(intent)
        request = _government_subsidy_request(
            candidate,
            intent,
            preview,
            context,
        )
        receipt = workflow.apply_receipt_borrowed(request)
        return _government_subsidy_result(candidate, receipt)

    def _require_context(self) -> _PostingContext:
        if self._context is None:
            raise RuntimeError("Finance Import posting request is not bound")
        return self._context


def _resolve_client_receipt(connection, candidate):
    client_id = _single_prefixed_identity(candidate, "client:")
    case_no = None if client_id is not None else _virtual_account_case_no(
        connection,
        candidate.row_identity,
    )
    if client_id is None and case_no is None:
        return candidate
    with connection.cursor() as cursor:
        statement, parameters = _client_receipt_target_query(
            client_id,
            case_no,
            candidate.amount.amount,
        )
        cursor.execute(statement, parameters)
        rows = tuple(cursor.fetchall())
    if len(rows) != 1:
        return candidate
    target = str(rows[0]["obligation_identity"])
    return _ready_candidate(
        candidate,
        (target,),
        "exact-open-client-obligation",
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
        "SELECT obligation.obligation_identity "
        "FROM client_obligations obligation "
    )
    predicates = (
        "AND obligation.direction='receivable_from_client' "
        "AND obligation.status='open' "
        "AND obligation.amount_due_ntd=%s "
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
    if client_id is None:
        return candidate
    rows = _load_exact_subsidy_return_targets(
        connection,
        client_id,
        candidate.amount.amount,
    )
    if len(rows) != 1:
        return candidate
    return _ready_candidate(
        candidate,
        (str(rows[0]["obligation_identity"]),),
        "exact-open-client-subsidy-return-obligation",
    )


def _resolve_client_refund(connection, candidate):
    client_id = _single_prefixed_identity(candidate, "client:")
    if client_id is None:
        return candidate
    rows = _load_client_refund_targets(connection, client_id)
    targets = _unique_case_refund_targets(rows, candidate.amount.amount)
    if targets is None:
        return candidate
    if not _has_exact_case_reference(connection, candidate.row_identity, rows):
        return _blocked_candidate(candidate, "client_refund_case_reference_required")
    return _ready_candidate(candidate, targets, "unique-client-refund-obligation-balance")


def _has_exact_case_reference(connection, row_identity, targets) -> bool:
    cases = {str(row["case_no"]) for row in targets}
    if len(cases) != 1:
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT bank_references FROM finance_import_rows WHERE id=%s",
            (_row_id(row_identity),),
        )
        row = cursor.fetchone()
    references = _json_object(row.get("bank_references") if row else None)
    return str(references.get("case_no", "")).strip() == cases.pop()


def _json_object(value):
    decoded = json.loads(value) if isinstance(value, str) else value
    return decoded if isinstance(decoded, dict) else {}


def _load_client_refund_targets(connection, client_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT obligation.case_no,obligation.obligation_identity,"
            "obligation.amount_due_ntd FROM client_obligations obligation "
            "JOIN orders order_row ON order_row.case_no=obligation.case_no "
            "WHERE order_row.client_id=%s AND obligation.direction='payable_to_client' "
            "AND obligation.status='open' AND obligation.amount_due_ntd>0 "
            "AND obligation.obligation_type IN ('refund','adjustment') "
            "ORDER BY obligation.case_no,obligation.due_date,obligation.obligation_identity",
            (client_id,),
        )
        return tuple(cursor.fetchall())


def _unique_case_refund_targets(rows, amount):
    by_case = {}
    for row in rows:
        by_case.setdefault(str(row["case_no"]), []).append(row)
    eligible = [
        _refund_target_prefix(values, amount)
        for values in by_case.values()
        if sum(int(row["amount_due_ntd"]) for row in values) >= amount
    ]
    return eligible[0] if len(eligible) == 1 else None


def _refund_target_prefix(rows, amount):
    remaining = amount
    targets = []
    for row in rows:
        targets.append(str(row["obligation_identity"]))
        remaining -= min(remaining, int(row["amount_due_ntd"]))
        if remaining == 0:
            return tuple(targets)
    raise RuntimeError("client_refund_target_selection_invalid")


def _load_exact_subsidy_return_targets(connection, client_id, amount_ntd):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT obligation.obligation_identity "
            "FROM client_obligations obligation "
            "JOIN orders order_row ON order_row.case_no=obligation.case_no "
            "WHERE order_row.client_id=%s "
            "AND obligation.direction='payable_to_client' "
            "AND obligation.obligation_type='subsidy_return' "
            "AND obligation.status='open' "
            "AND obligation.amount_due_ntd=%s "
            "ORDER BY obligation.obligation_identity",
            (client_id, amount_ntd),
        )
        return tuple(cursor.fetchall())


def _resolve_staff_payout(connection, candidate):
    staff_id = _single_prefixed_identity(candidate, "staff:")
    if staff_id is None:
        return candidate
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT obligation.obligation_identity,"
            "COALESCE(projection.balance_ntd,obligation.amount_due_ntd) "
            "AS balance_ntd "
            "FROM staff_obligations obligation "
            "LEFT JOIN staff_payable_projections projection "
            "ON projection.obligation_identity=obligation.obligation_identity "
            "WHERE obligation.staff_id=%s "
            "AND obligation.direction='payable_to_staff' "
            "AND obligation.status<>'cancelled' "
            "AND obligation.amount_due_ntd>0 "
            "AND (projection.status IS NULL OR projection.status='payable') "
            "ORDER BY obligation.obligation_identity",
            (staff_id,),
        )
        rows = tuple(cursor.fetchall())
    total = sum(int(row["balance_ntd"]) for row in rows)
    if not rows or total != candidate.amount.amount:
        return candidate
    targets = tuple(str(row["obligation_identity"]) for row in rows)
    return _ready_candidate(
        candidate,
        targets,
        "exact-staff-payable-total",
    )


def _resolve_government_subsidy(connection, candidate):
    repository = MySqlGovernmentSubsidyRepository(connection)
    workflow = GovernmentSubsidyLedgerWorkflow(
        repository,
        BorrowedTransactionUnitOfWork,
    )
    intent = ReceiptIntent(int(_row_id(candidate.row_identity)), None)
    try:
        preview = workflow.preview_receipt(intent)
    except GovernmentSubsidyDomainError as error:
        if error.code is GovernmentSubsidyErrorCode.REVIEW_REQUIRED:
            return candidate
        return _blocked_candidate(candidate, error.code.value)
    batch_identity = f"government-subsidy-batch:{preview.candidate.batch_id}"
    return _ready_candidate(
        candidate,
        (batch_identity,),
        "unique-approved-government-subsidy-batch",
    )


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
        ClientFinanceCorrectionType.REFUND,
        ClientRefundPurpose.SUBSIDY_RETURN,
        bank_fact_identities=(_row_id(candidate.row_identity),),
        obligation_identities=targets,
    )


def _subsidy_payout_selection(connection, candidate, selection):
    if len(selection.obligation_identities) != 1:
        raise ValueError("subsidy_advance_settlement_ambiguous")
    row = _subsidy_payout_facts(
        connection,
        selection.obligation_identities[0],
        _row_id(candidate.row_identity),
    )
    if row is None:
        raise ValueError("subsidy_advance_settlement_ambiguous")
    if _has_government_receipt(row):
        return selection
    _require_eligible_subsidy_advance(row, _candidate_amount(candidate))
    return replace(selection, refund_purpose=ClientRefundPurpose.SUBSIDY_ADVANCE)


def _subsidy_payout_facts(connection, obligation_identity, row_identity):
    with connection.cursor() as cursor:
        cursor.execute(_SUBSIDY_PAYOUT_FACTS_SQL, (row_identity, obligation_identity))
        return cursor.fetchone()


def _has_government_receipt(row):
    allocated = int(row["allocated_amount_ntd"] or 0)
    entitled = int(row["entitled_amount_ntd"] or 0)
    if allocated == entitled and entitled > 0:
        return True
    if allocated:
        raise ValueError("subsidy_advance_settlement_ambiguous")
    return False


def _require_eligible_subsidy_advance(row, payout_amount):
    completed_on = row.get("actual_end_date")
    occurred_on = row.get("transaction_date")
    due_date = row.get("due_date")
    entitled = int(row["entitled_amount_ntd"] or 0)
    if not isinstance(completed_on, date) or not isinstance(occurred_on, date):
        raise ValueError("subsidy_advance_settlement_ambiguous")
    if not isinstance(due_date, date) or due_date != subsidy_advance_due_date(completed_on):
        raise ValueError("subsidy_advance_settlement_ambiguous")
    if not is_first_month_of_quarter(completed_on) or occurred_on < due_date:
        raise ValueError("subsidy_advance_not_due")
    if entitled <= 0 or payout_amount != entitled:
        raise ValueError("subsidy_advance_settlement_ambiguous")


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
            if isinstance(candidate, FinanceImportCorrectionCandidate)
            and candidate.allow_refund_overage_recovery
            else ClientFinanceCorrectionType.REFUND
        ),
        ClientRefundPurpose.CUSTOMER_REFUND,
        bank_fact_identities=(_row_id(candidate.row_identity),),
        obligation_identities=targets,
        allow_partial_refund_recovery=(
            candidate.allow_partial_refund_recovery
            if isinstance(candidate, FinanceImportCorrectionCandidate)
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
        ExpectedVersion(preview.batch_version),
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


def _typed_domain_result(candidate, error):
    if error.retryable:
        raise FinanceImportRepositoryUnavailable(error.message)
    if isinstance(candidate, FinanceImportCorrectionCandidate):
        raise ValueError(error.code)
    outcome = (
        FinanceDispatchOutcome.CONFLICT
        if error.category is ErrorCategory.CONFLICT
        else FinanceDispatchOutcome.REJECTED
    )
    return FinanceImportDispatchResult(candidate.row_identity, outcome)


def _government_subsidy_domain_result(candidate, error):
    if isinstance(candidate, FinanceImportCorrectionCandidate):
        raise ValueError(error.code.value)
    outcome = (
        FinanceDispatchOutcome.PENDING
        if error.code is GovernmentSubsidyErrorCode.REVIEW_REQUIRED
        else FinanceDispatchOutcome.REJECTED
    )
    return FinanceImportDispatchResult(candidate.row_identity, outcome)


def _target_identities(candidate):
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


_SUBSIDY_PAYOUT_FACTS_SQL = """
SELECT obligation.due_date,
       order_row.actual_end_date,
       finance_row.transaction_date,
       link.entitled_amount_ntd,
       COALESCE(
           SUM(
               CASE WHEN allocation.allocation_type='receipt'
               THEN allocation.allocated_amount ELSE 0 END
           ),
           0
       ) AS allocated_amount_ntd
FROM client_obligations obligation
JOIN orders order_row ON order_row.case_no=obligation.case_no
JOIN finance_import_rows finance_row ON finance_row.id=%s
LEFT JOIN client_subsidy_return_claim_item_links link
  ON link.obligation_identity=obligation.obligation_identity
LEFT JOIN government_subsidy_allocations allocation
  ON allocation.claim_item_id=link.claim_item_id
WHERE obligation.obligation_identity=%s
GROUP BY obligation.due_date,
         order_row.actual_end_date,
         finance_row.transaction_date,
         link.entitled_amount_ntd
"""


__all__ = [
    "BorrowedTransactionUnitOfWork",
    "MySqlFinanceImportOwningDomainComposite",
]
