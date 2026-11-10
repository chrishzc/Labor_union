"""Bank subsidy Preview/Apply composition using the original money owners.

Preview projects a proposed refund or Payroll funding schedule without writes.
The caller's existing Finance Import UoW owns confirmation, establishment and
settlement. Bank confirmations use a reserved key in the existing plan event
owner; public manual commands cannot claim that source namespace.
"""
from dataclasses import replace

from domains.finance_import.planning import (
    FinanceClassificationType, FinanceImportDisposition, SubsidyConfirmationPreflight,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey
from shared_kernel.money import MoneyNTD


def _bank_case(connection, row, candidate):
    from domains.finance_import.cancellation_code import sinopac_memo_case_suffixes
    from subsystems.client_finance.virtual_account_resolution import resolve_client_virtual_account_suffix
    from infrastructure.mysql.finance_import_owning_domain_composite import _single_prefixed_identity
    suffixes = sinopac_memo_case_suffixes(row.get('memo'))
    with connection.cursor() as cursor:
        resolved = resolve_client_virtual_account_suffix(cursor, next(iter(suffixes))) if len(suffixes) == 1 else None
        if suffixes and (resolved is None or resolved['result'] != 'resolved'):
            raise ValueError('subsidy_case_not_unique')
        if candidate.classification_type is FinanceClassificationType.CLIENT_SUBSIDY_RETURN:
            if resolved is None:
                raise ValueError('client_subsidy_memo_recipient_unconfirmed')
            case_no = resolved['case_no']
            cursor.execute('SELECT client_id FROM orders WHERE case_no=%s', (case_no,))
            owner = cursor.fetchone()
            if owner is None or _single_prefixed_identity(candidate, 'client:') != int(owner['client_id']):
                raise ValueError('client_subsidy_memo_case_mismatch')
            from infrastructure.mysql.client_refund_reversal_repository import _verify_taishin_subsidy_cases
            _verify_taishin_subsidy_cases(cursor, ({**row, 'effective_classification_type':'client_subsidy_return'},), expected_case_no=case_no)
            return case_no
        staff_id = _single_prefixed_identity(candidate, 'staff:')
        from infrastructure.mysql.staff_payout_repository import _verify_taishin_memo_recipients
        verified = _verify_taishin_memo_recipients(cursor, (row,), False)
        if staff_id is None or verified[0].get('taishin_memo_staff_id') != staff_id:
            raise ValueError('staff_memo_recipient_unconfirmed')
        cursor.execute("SELECT case_no FROM orders WHERE staff_id=%s UNION "
            "SELECT case_no FROM case_staff_assignments WHERE staff_id=%s AND status IN ('planned','active','completed') UNION "
            "SELECT case_no FROM staff_obligations WHERE staff_id=%s AND direction='payable_to_staff' AND status<>'cancelled'",
            (staff_id, staff_id, staff_id))
        cases = {r['case_no'] for r in cursor.fetchall()}
        if resolved is not None:
            if resolved['case_no'] not in cases:
                raise ValueError('staff_memo_case_mismatch')
            return resolved['case_no']
        if len(cases) != 1:
            raise ValueError('subsidy_case_not_unique')
        return cases.pop()


def resolve_subsidy_confirmation(connection, candidate, *, for_update=False):
    """Return None for other bank flows, otherwise the complete zero-write plan."""
    from infrastructure.mysql.accounting_workspace_repository import (
        build_accounting_workspace, MySqlAccountingWorkspaceState, query_subsidy_payable_handoff,
    )
    from infrastructure.mysql.finance_import_owning_domain_composite import (
        _row_id, _resolve_client_subsidy_return, _resolve_staff_payout,
    )
    if candidate.classification_type not in {FinanceClassificationType.CLIENT_SUBSIDY_RETURN, FinanceClassificationType.STAFF_PAYOUT}:
        return None
    with connection.cursor() as cursor:
        cursor.execute('SELECT id,format_id,direction,memo,transaction_date,currency FROM finance_import_rows WHERE id=%s', (_row_id(candidate.row_identity),))
        source = cursor.fetchone()
    if not source or source['format_id'] != 'taishin' or source['direction'] != 'outgoing':
        return None
    pending = replace(candidate, disposition=FinanceImportDisposition.BUSINESS_PENDING, available_actions=('resolve_owning_domain_target',))
    try:
        case_no = _bank_case(connection, source, candidate)
        scheme = 'advance' if candidate.classification_type is FinanceClassificationType.CLIENT_SUBSIDY_RETURN else 'split'
        state = MySqlAccountingWorkspaceState(connection)
        if for_update:
            state.lock_arrangement_case(case_no)
            with connection.cursor() as cursor:
                for table in ('client_finance_accounts','payroll_case_accounts','scheduling_aggregates',
                              'government_subsidy_amount_controls','historical_service_day_projections'):
                    cursor.execute(f'SELECT case_no FROM {table} WHERE case_no=%s FOR UPDATE', (case_no,))
                    cursor.fetchall()
        plan = state.subsidy_plan(case_no)
        if plan.selected_scheme not in (None, scheme):
            raise ValueError('subsidy_confirmation_plan_conflict')
        case = build_accounting_workspace(connection).query(case_no, for_update=for_update)
        if scheme == 'split' and '補助' not in (source.get('memo') or '') and not (
                case.subsidy_ntd is not None and case.subsidy_ntd > 0 and case.staff_receivable_ntd is not None):
            raise ValueError('staff_subsidy_purpose_unconfirmed')
        handoff = query_subsidy_payable_handoff(connection, case_no, proposed_scheme=scheme)
        preflight = SubsidyConfirmationPreflight(case_no, scheme, plan.version, case.subsidy_ntd, case.staff_receivable_ntd,
            candidate.target_identities[0] if len(candidate.target_identities) == 1 else '')
        pending = replace(pending, subsidy_preflight=preflight)
        if case.subsidy_ntd == 0:
            raise ValueError('subsidy_amount_not_positive')
        if not handoff.service_completed:
            return _annotate(replace(pending, disposition=FinanceImportDisposition.CREATE,
                target_identities=(), available_actions=('confirm_subsidy_scheme',),
                pending_reason='subsidy_service_not_completed', subsidy_preflight=replace(preflight, confirmation_only=True)), case)
        reason = handoff.client_subsidy_reason if scheme == 'advance' else handoff.staff_subsidy_reason
        if reason:
            raise ValueError(reason)
        if source['transaction_date'] is None:
            raise ValueError('bank_transaction_date_missing')
        if source.get('currency') is not None and str(source['currency']).upper() not in {'TWD','NTD'}:
            raise ValueError('bank_currency_not_twd')
        if scheme == 'advance':
            with connection.cursor() as cursor:
                cursor.execute("SELECT obligation_identity FROM client_obligations WHERE case_no=%s AND obligation_type='subsidy_return'", (case_no,))
                existing = tuple(cursor.fetchall())
            if not existing:
                return _preview_new_refund(connection, pending, source, case)
            ready = _resolve_client_subsidy_return(connection, pending)
        else:
            with connection.cursor() as cursor:
                cursor.execute("SELECT o.obligation_identity,EXISTS(SELECT 1 FROM staff_obligation_installments i WHERE i.obligation_identity=o.obligation_identity) has_installments "
                    "FROM staff_obligations o WHERE o.case_no=%s AND o.direction='payable_to_staff' AND o.status<>'cancelled'", (case_no,))
                roots = tuple(cursor.fetchall())
            if len(roots) == 1 and not roots[0]['has_installments']:
                return _preview_staff_split(connection, pending, source, case, roots[0]['obligation_identity'])
            ready = _resolve_staff_payout(connection, pending)
        return _annotate(ready, case)
    except ValueError as error:
        preflight = pending.subsidy_preflight
        return replace(pending, pending_reason=str(error),
            subsidy_preflight=replace(preflight, blocker=str(error)) if preflight else None)


def _annotate(candidate, case, owner_fingerprint=None):
    preflight = candidate.subsidy_preflight
    if preflight.proposed_refund is not None:
        preflight = replace(preflight, payable_amount_ntd=preflight.proposed_refund.amount.amount,
            payable_due_date=preflight.proposed_refund.due_date.isoformat())
    elif not preflight.staff_confirm_split and candidate.disposition is FinanceImportDisposition.CREATE and not preflight.confirmation_only:
        selected = [item for item in (*case.client_items,*case.staff_items) if item.identity in candidate.target_identities]
        if preflight.scheme == 'split':
            portions = [p for item in selected for p in item.funding_portions if p.funding_kind == 'subsidy']
            if portions and all(p.remaining_ntd is not None for p in portions):
                dates = {p.due_date for p in portions}
                preflight = replace(preflight, payable_amount_ntd=sum(p.remaining_ntd for p in portions),
                    payable_due_date=next(iter(dates)).isoformat() if len(dates)==1 and None not in dates else None)
        elif selected:
            dates = {p.due_date for p in selected}
            preflight = replace(preflight, payable_amount_ntd=sum(p.remaining_ntd for p in selected),
                payable_due_date=next(iter(dates)) if len(dates)==1 else None)
    if candidate.disposition is FinanceImportDisposition.BUSINESS_PENDING and candidate.pending_reason:
        preflight = replace(preflight, blocker=candidate.pending_reason)
    candidate = replace(candidate, subsidy_preflight=preflight)
    return replace(candidate, decision_facts_fingerprint=fingerprint_payload({
        'row': candidate.row_identity, 'canonical_version': candidate.canonical_fact_version,
        'classification': candidate.classification_type.value,
        'plan_version': candidate.subsidy_preflight.plan_version,
        'subsidy': case.subsidy_ntd, 'total': case.staff_receivable_ntd,
        'customer_due': case.customer_amount_ntd, 'customer_paid': case.customer_paid_ntd,
        'staff': [(item.identity, item.version, item.expected_ntd, item.actual_ntd, item.due_date) for item in case.staff_items],
        'client': [(item.identity, item.version, item.expected_ntd, item.actual_ntd, item.due_date) for item in case.client_items],
        'owner': owner_fingerprint,
    }))


def _preview_new_refund(connection, candidate, source, case):
    from domains.client_finance.obligation_planning import confirmed_subsidy_return_plan
    from domains.client_finance.client_refund_reversal import ClientFinanceCorrectionType, ClientRefundPurpose
    from infrastructure.mysql.client_refund_reversal_repository import MySqlClientRefundReversalRepository
    from subsystems.client_finance.client_refund_reversal_workflow import ClientRefundReversalSelection, ClientRefundReversalWorkflow, ClientRefundReversalError
    from infrastructure.mysql.finance_import_owning_domain_composite import BorrowedTransactionUnitOfWork, _is_same_month
    with connection.cursor() as cursor:
        cursor.execute('SELECT COALESCE(actual_end_date,end_date) completed_on FROM orders WHERE case_no=%s', (case.case_no,))
        order = cursor.fetchone()
    if not order or order['completed_on'] is None:
        raise ValueError('subsidy_service_end_missing')
    proposed = confirmed_subsidy_return_plan(case.case_no, MoneyNTD(case.subsidy_ntd), order['completed_on'])
    preflight = replace(candidate.subsidy_preflight, proposed_refund=proposed)
    candidate = replace(candidate, subsidy_preflight=preflight)
    if not _is_same_month(source['transaction_date'], proposed.due_date):
        return replace(candidate, pending_reason='outgoing_client_refund_month_no_match', subsidy_preflight=replace(preflight, blocker='outgoing_client_refund_month_no_match'))
    if not 0 <= proposed.amount.amount - candidate.amount.amount <= 100:
        return replace(candidate, pending_reason='outgoing_client_refund_amount_mismatch', subsidy_preflight=replace(preflight, blocker='outgoing_client_refund_amount_mismatch'))
    selection = ClientRefundReversalSelection(case.case_no, ClientFinanceCorrectionType.REFUND,
        ClientRefundPurpose.SUBSIDY_RETURN, bank_fact_identities=(str(source['id']),), obligation_identities=(proposed.obligation_identity,))
    workflow = ClientRefundReversalWorkflow(MySqlClientRefundReversalRepository(connection,
        preview_refund_classification='client_subsidy_return', proposed_subsidy_return=proposed), BorrowedTransactionUnitOfWork)
    try:
        preview = workflow.preview(selection, CorrelationId('subsidy-preflight:' + str(source['id'])))
    except ClientRefundReversalError as error:
        if error.error.category.value != 'domain_blocked':
            from subsystems.finance_import.import_workflow import FinanceImportWorkflowError
            raise FinanceImportWorkflowError(error.error) from error
        return replace(candidate, pending_reason=error.error.code,
            subsidy_preflight=replace(preflight, blocker=error.error.code))
    ready = replace(candidate, disposition=FinanceImportDisposition.CREATE,
        target_identities=(proposed.obligation_identity,), available_actions=('confirm_subsidy_scheme','reconcile'), pending_reason=None)
    return _annotate(ready, case, preview.fingerprint.value)


def _preview_staff_split(connection, candidate, source, case, identity):
    from domains.staff_payables.reconciliation import StaffPayoutEventType
    from infrastructure.mysql.staff_payout_repository import MySqlStaffPayoutRepository
    from subsystems.staff_payables.payout_reconciliation import StaffPayoutSelection, StaffPayoutReconciliationWorkflow, StaffPayoutReconciliationError
    from infrastructure.mysql.finance_import_owning_domain_composite import BorrowedTransactionUnitOfWork, _is_same_month
    selection = StaffPayoutSelection(StaffPayoutEventType.PAYOUT, (str(source['id']),), (identity,), confirm_subsidy_split=True)
    try:
        preview = StaffPayoutReconciliationWorkflow(MySqlStaffPayoutRepository(connection), BorrowedTransactionUnitOfWork).preview(
            selection, CorrelationId('subsidy-preflight:' + str(source['id'])))
    except StaffPayoutReconciliationError as error:
        if error.error.category.value not in {'domain_blocked', 'conflict'}:
            from subsystems.finance_import.import_workflow import FinanceImportWorkflowError
            raise FinanceImportWorkflowError(error.error) from error
        raise ValueError(error.error.code) from error
    split = preview.subsidy_split
    due = next(p.due_date for p in split.installments if p.funding_kind == 'subsidy')
    if not _is_same_month(source['transaction_date'], due):
        raise ValueError('outgoing_staff_payout_month_no_match')
    if not 0 <= split.subsidy_remaining_ntd - candidate.amount.amount <= 100:
        raise ValueError('staff_payout_amount_mismatch')
    ready = replace(candidate, disposition=FinanceImportDisposition.CREATE, target_identities=(identity,),
        available_actions=('confirm_subsidy_scheme','reconcile'), pending_reason=None,
        subsidy_preflight=replace(candidate.subsidy_preflight, staff_confirm_split=True,
            payable_amount_ntd=split.subsidy_remaining_ntd, payable_due_date=due.isoformat() if due else None))
    return _annotate(ready, case, preview.fingerprint.value)


def apply_subsidy_confirmation(connection, candidate, context):
    """Use a previously fresh-read plan under the original outer UoW; never commit."""
    from infrastructure.mysql.accounting_workspace_repository import MySqlAccountingWorkspaceState
    preflight = candidate.subsidy_preflight
    state = MySqlAccountingWorkspaceState(connection)
    state.lock_arrangement_case(preflight.case_no)
    with connection.cursor() as cursor:
        for table in ('client_finance_accounts', 'payroll_case_accounts'):
            cursor.execute(f'SELECT case_no FROM {table} WHERE case_no=%s FOR UPDATE', (preflight.case_no,))
            cursor.fetchall()
    # Apply rebuilt and compared the complete plan while holding these owner
    # locks. Do not compare the original whole-case snapshot again after a
    # preceding row's legitimate confirmation/establishment/settlement.
    current = state.subsidy_plan(preflight.case_no)
    if current.version != preflight.plan_version:
        # A preceding row in this same batch may have confirmed the same scheme.
        if current.selected_scheme != preflight.scheme or current.confirmation_source != 'bank':
            raise ValueError('subsidy_confirmation_version_changed')
    elif current.selected_scheme is None:
        state.append_subsidy_plan(preflight.case_no, current.version + 1, preflight.scheme,
            context.actor.actor_id, context.idempotency_key.value, bank_row_id=int(candidate.row_identity.rsplit(':',1)[-1]))
    if preflight.proposed_refund is not None:
        persist_confirmed_refund(connection, preflight.case_no, preflight.proposed_refund,
            context.actor, context.idempotency_key, context.correlation_id, candidate.row_identity)


def persist_confirmed_refund(connection, case_no, plan, actor, key, correlation, source, *, advance_version=True):
    from hashlib import sha256
    from domains.client_finance.obligation_planning import ClientFinanceTermsCandidate, ClientSettlementProjection
    from infrastructure.mysql.client_finance_terms_writer import persist_client_finance_terms_impact, persist_subsidy_return_plan
    from subsystems.orders.terms_workflow import ClientFinanceImpactPersistenceCommand
    with connection.cursor() as cursor:
        cursor.execute('SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s FOR UPDATE', (case_no,))
        account = cursor.fetchone()
        if account is None:
            raise ValueError('client_finance_bootstrap_required')
        fingerprint = fingerprint_payload({'case':case_no,'amount':plan.amount.amount,'due':plan.due_date.isoformat()})
        candidate = ClientFinanceTermsCandidate(case_no, int(account['aggregate_version']), int(account['aggregate_version'])+int(advance_version),
            (), (), ClientSettlementProjection(False,False,fingerprint), (), fingerprint, subsidy_return_plan=plan)
        command = ClientFinanceImpactPersistenceCommand(candidate,
            IdempotencyKey('confirmed-subsidy:' + sha256((key.value + ':' + case_no).encode()).hexdigest()),
            actor, '依已確認補助來源承接客戶退款', correlation, 'subsidy-confirmation', source)
        if advance_version:
            persist_client_finance_terms_impact(cursor, command)
        else:
            persist_subsidy_return_plan(cursor, command)


def preview_manual_subsidy_plan(connection, case_no, scheme, version, *, for_update=False):
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace, query_subsidy_payable_handoff
    from subsystems.finance_import.accounting_workspace import SubsidyPlanPreview, SubsidyPlanPayable
    from domains.client_finance.obligation_planning import confirmed_subsidy_return_plan
    from domains.payroll.installments import confirmed_subsidy_installments
    from infrastructure.mysql.staff_payout_repository import _funding_settlements
    case = build_accounting_workspace(connection).query(case_no, for_update=for_update)
    handoff = query_subsidy_payable_handoff(connection, case_no, proposed_scheme=scheme)
    payables, refund, staff_identity, installments = (), None, None, ()
    blocker = None
    only = not handoff.service_completed
    with connection.cursor() as cursor:
        cursor.execute('SELECT COALESCE(actual_end_date,end_date) completed_on FROM orders WHERE case_no=%s'
                       + (' FOR UPDATE' if for_update else ''), (case_no,))
        order = cursor.fetchone()
        if not only and scheme != 'direct' and case.subsidy_ntd != 0:
            blocker = handoff.client_subsidy_reason if scheme == 'advance' else handoff.staff_subsidy_reason
            if not blocker and (not order or order['completed_on'] is None):
                blocker = 'subsidy_service_end_missing'
            if not blocker and scheme == 'advance':
                cursor.execute("SELECT obligation_identity FROM client_obligations WHERE case_no=%s AND obligation_type='subsidy_return'", (case_no,))
                if not cursor.fetchall():
                    refund = confirmed_subsidy_return_plan(case_no, MoneyNTD(case.subsidy_ntd), order['completed_on'])
                    payables = (SubsidyPlanPayable(refund.obligation_identity, 'client', refund.amount.amount, refund.due_date.isoformat()),)
            elif not blocker and scheme == 'split':
                cursor.execute("SELECT o.obligation_identity,o.due_date,EXISTS(SELECT 1 FROM staff_obligation_installments i WHERE i.obligation_identity=o.obligation_identity) has_installments "
                    "FROM staff_obligations o WHERE o.case_no=%s AND o.direction='payable_to_staff' AND o.status<>'cancelled'", (case_no,))
                roots = tuple(cursor.fetchall())
                if len(roots) == 1 and not roots[0]['has_installments']:
                    staff_identity = roots[0]['obligation_identity']
                    installments = confirmed_subsidy_installments(case.staff_receivable_ntd, case.subsidy_ntd,
                        roots[0]['due_date'], order['completed_on'])
                    paid, unconfirmed = _funding_settlements(cursor, staff_identity)
                    actual = sum(item.actual_ntd for item in case.staff_items if item.identity == staff_identity)
                    if unconfirmed or sum(paid.values()) != actual or any(paid[p.funding_kind] > p.amount for p in installments):
                        blocker = 'staff_installment_funding_unconfirmed'
                    else:
                        payables = tuple(SubsidyPlanPayable(staff_identity, 'staff:' + p.funding_kind,
                            p.amount, p.due_date.isoformat() if p.due_date else None) for p in installments)
                elif not roots or any(not row['has_installments'] for row in roots):
                    blocker = 'staff_subsidy_split_selection_invalid'
    fingerprint = fingerprint_payload({'case':case_no,'scheme':scheme,'version':version,
        'S':case.subsidy_ntd,'T':case.staff_receivable_ntd,'only':only,
        'payables':[(p.identity,p.recipient,p.amount_ntd,p.due_date) for p in payables],
        'sources':[(p.identity,p.version,p.expected_ntd,p.actual_ntd,p.due_date) for p in (*case.client_items,*case.staff_items)],
        'blocker':blocker})
    return SubsidyPlanPreview(case_no,scheme,version,case.subsidy_ntd,case.staff_receivable_ntd,only,
        payables,blocker,fingerprint,refund,staff_identity,installments)


def apply_manual_subsidy_plan(connection, preview, actor, key):
    from shared_kernel.identities import ActorContext
    if preview.blocker:
        return  # The reviewed command confirms only the arrangement, not blocked money actions.
    if preview.refund_plan is not None:
        persist_confirmed_refund(connection, preview.case_no, preview.refund_plan,
            ActorContext(actor), IdempotencyKey(key), CorrelationId('subsidy-plan:' + preview.case_no), preview.case_no)
    if preview.installments:
        from infrastructure.mysql.payroll_installments import establish_confirmed_subsidy_installments
        with connection.cursor() as cursor:
            establish_confirmed_subsidy_installments(cursor, preview.staff_identity, preview.installments)
