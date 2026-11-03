"""Payroll-owned amount modes; paid roots stay frozen and changes are separate."""
from hashlib import sha256
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from domains.payroll.amount_correction import PayrollAmountConflict, payroll_amount_decision
from subsystems.payroll.amount_correction import PayrollAmountItem, PayrollAmountEvent, PayrollAmountView


def _today():
    return datetime.now(ZoneInfo('Asia/Taipei')).date()


def _digest(command):
    return sha256(json.dumps({k:getattr(command,k) for k in command.__dataclass_fields__},sort_keys=True,ensure_ascii=False).encode()).hexdigest()


class MySqlPayrollAmountRepository:
    def __init__(self,connection):
        self.connection=connection

    def query(self,case_no):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT aggregate_version FROM payroll_case_accounts WHERE case_no=%s',(case_no,))
            root=cursor.fetchone()
            if not root:
                return PayrollAmountView(case_no,0,(),())
            cursor.execute('SELECT o.obligation_identity,o.amount_due_ntd,o.assignment_id,s.name party,c.amount_mode,c.computed_ntd,c.effective_ntd,'
                'COALESCE(p.net_paid_ntd,0) paid FROM staff_obligations o JOIN staff s ON s.id=o.staff_id '
                'LEFT JOIN payroll_amount_controls c ON c.obligation_identity=o.obligation_identity '
                'LEFT JOIN staff_payable_projections p ON p.obligation_identity=o.obligation_identity '
                "WHERE o.case_no=%s AND o.obligation_kind='service_pay' AND o.status<>'cancelled' ORDER BY o.obligation_identity",(case_no,))
            rows=cursor.fetchall()
            computed=_latest_computations(self.connection,case_no) if rows else {}
            items=tuple(PayrollAmountItem(r['obligation_identity'],r['party'],r['amount_mode'] or 'automatic',
                computed.get(int(r['assignment_id']),int(r['computed_ntd'] if r['computed_ntd'] is not None else r['amount_due_ntd'])),
                int(r['effective_ntd'] if r['effective_ntd'] is not None else r['amount_due_ntd']),int(r['paid']),
                max(0,int(r['effective_ntd'] if r['effective_ntd'] is not None else r['amount_due_ntd'])-int(r['paid']))) for r in rows)
            cursor.execute('SELECT a.* FROM payroll_amount_changes a JOIN staff_obligations o ON o.obligation_identity=a.obligation_identity WHERE o.case_no=%s ORDER BY a.id',(case_no,))
            events=tuple(PayrollAmountEvent(f'payroll-amount:{r["id"]}',r['obligation_identity'],r['action'],int(r['before_ntd']),int(r['after_ntd']),int(r['computed_ntd']),r['reason'],r['actor'],str(r['confirmed_on'])) for r in cursor.fetchall())
        return PayrollAmountView(case_no,int(root['aggregate_version']),items,events)

    def replay(self,command):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT command_digest FROM payroll_amount_changes WHERE operation_key=%s FOR UPDATE',(command.key,))
            row=cursor.fetchone()
            if row:
                if row['command_digest']!=_digest(command):
                    raise PayrollAmountConflict('payroll_amount_command_changed')
                return self.query(command.case_no)
        return None

    def apply(self,command):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT aggregate_version FROM payroll_case_accounts WHERE case_no=%s FOR UPDATE',(command.case_no,))
            root=cursor.fetchone()
            if not root or int(root['aggregate_version'])!=command.expected_version:
                raise PayrollAmountConflict('payroll_amount_stale')
            cursor.execute('SELECT case_no FROM finance_case_accounting_markers WHERE case_no=%s',(command.case_no,))
            if cursor.fetchone():
                raise PayrollAmountConflict('historical_case_already_settled')
            item=next((r for r in self.query(command.case_no).items if r.identity==command.identity),None)
            if not item or not command.reason.strip():
                raise PayrollAmountConflict('payroll_amount_target_invalid')
            decision=payroll_amount_decision(item.mode,item.effective_ntd,item.computed_ntd,command.action,command.amount_ntd)
            _persist_amount(self.connection,cursor,command.case_no,item.identity,decision.mode,item.computed_ntd,decision.effective_ntd,
                item.effective_ntd,command.action,command.key,_digest(command),command.actor,command.reason,command.expected_version+1)
            from infrastructure.mysql.payroll_rebuild_repository import MySqlPayrollRebuildRepository
            from domains.payroll.calculation import build_case_payroll_candidate
            from infrastructure.mysql.payroll_installments import persist_payroll_installments
            facts=MySqlPayrollRebuildRepository(self.connection).load(command.case_no,for_update=False)
            candidate=build_case_payroll_candidate(facts.service_facts,facts.rate_snapshots,facts.terms,facts.adjustments)
            persist_payroll_installments(cursor,command.case_no,candidate)
            cursor.execute('UPDATE payroll_case_accounts SET aggregate_version=aggregate_version+1 WHERE case_no=%s AND aggregate_version=%s',(command.case_no,command.expected_version))
            if cursor.rowcount!=1:
                raise PayrollAmountConflict('payroll_amount_stale')
        return self.query(command.case_no)


def _latest_computations(connection,case_no):
    from infrastructure.mysql.payroll_rebuild_repository import MySqlPayrollRebuildRepository
    from domains.payroll.calculation import build_case_payroll_candidate
    facts=MySqlPayrollRebuildRepository(connection).load(case_no,for_update=False)
    candidate=build_case_payroll_candidate(facts.service_facts,facts.rate_snapshots,facts.terms,facts.adjustments)
    return {int(i.assignment_identity.rsplit(':',1)[-1]):i.total_payable.amount for i in candidate.assignments}


def _persist_amount(connection,cursor,case_no,identity,mode,computed,effective,before,action,key,digest,actor,reason,version):
    cursor.execute('SELECT o.*,COALESCE(p.net_paid_ntd,0) paid,c.settlement_base_ntd FROM staff_obligations o '
        'LEFT JOIN staff_payable_projections p ON p.obligation_identity=o.obligation_identity '
        'LEFT JOIN payroll_amount_controls c ON c.obligation_identity=o.obligation_identity '
        'WHERE o.obligation_identity=%s AND o.case_no=%s FOR UPDATE',(identity,case_no))
    row=cursor.fetchone()
    if not row:
        raise PayrollAmountConflict('payroll_amount_target_missing')
    frozen=row['settlement_base_ntd'] is not None or (int(row['paid'])>=before and before>0)
    base=int(row['settlement_base_ntd']) if row['settlement_base_ntd'] is not None else before if frozen else None
    cursor.execute('INSERT INTO payroll_amount_controls(obligation_identity,case_no,amount_mode,computed_ntd,effective_ntd,settlement_base_ntd) VALUES(%s,%s,%s,%s,%s,%s) '
        'ON DUPLICATE KEY UPDATE amount_mode=VALUES(amount_mode),computed_ntd=VALUES(computed_ntd),effective_ntd=VALUES(effective_ntd),settlement_base_ntd=VALUES(settlement_base_ntd)',(identity,case_no,mode,computed,effective,base))
    cursor.execute('INSERT INTO payroll_amount_changes(obligation_identity,action,before_ntd,after_ntd,computed_ntd,operation_key,command_digest,actor,reason,confirmed_on) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        (identity,action,before,effective,computed,key,digest,actor,reason,_today()))
    delta=effective-before
    if frozen and delta:
        _separate_payroll_difference(connection,cursor,row,delta,key,actor,reason,version)
    elif not frozen and int(row['paid'])>effective:
        # Only newly created overpayment is recoverable, never the unpaid portion.
        old_excess=max(0,int(row['paid'])-before)
        increase=max(0,int(row['paid'])-effective)-old_excess
        if increase:
            _separate_payroll_difference(connection,cursor,row,-increase,key,actor,reason,version)
    cursor.execute('UPDATE staff_payable_accounts SET aggregate_version=aggregate_version+1 WHERE staff_id=%s',(row['staff_id'],))
    if not frozen and int(row['paid']):
        from infrastructure.mysql.staff_payout_repository import _projection_rows,_upsert_projection
        cursor.execute('SELECT aggregate_version FROM staff_payable_accounts WHERE staff_id=%s FOR UPDATE',(row['staff_id'],))
        staff_version=int(cursor.fetchone()['aggregate_version'])
        for projection in _projection_rows(cursor,(identity,)):
            _upsert_projection(cursor,projection,staff_version)


def _separate_payroll_difference(connection,cursor,row,delta,key,actor,reason,version):
    from domains.staff_payables.overpayment_recovery import PayrollCorrectionRecoverySource
    from subsystems.staff_payables.overpayment_recovery import StaffOverpaymentRecoveryCreationApplication, StaffOverpaymentRecoveryCreationRequest
    from infrastructure.mysql.staff_overpayment_recovery_repository import MySqlStaffOverpaymentRecoveryRepository
    from shared_kernel.identities import IdempotencyKey,ActorContext,CorrelationId
    from shared_kernel.money import MoneyNTD
    child='payroll-manual:'+sha256((row['obligation_identity']+':'+key).encode()).hexdigest()
    positive=delta>0; kind='adjustment' if positive else 'reversal'; direction='payable_to_staff' if positive else 'receivable_from_staff'
    event_key='payroll-amount-event:'+sha256(key.encode()).hexdigest()
    cursor.execute('INSERT INTO staff_obligation_events(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,source_obligation_identity,event_type,before_amount_ntd,after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,resulting_payroll_version,idempotency_key,actor,reason) '
        'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s,%s)',(child,row['assignment_id'],row['case_no'],row['staff_id'],kind,direction,row['obligation_identity'],kind,abs(delta),row['due_date'],sha256(key.encode()).hexdigest(),version-1,version,event_key,actor,reason))
    event=int(cursor.lastrowid)
    cursor.execute('INSERT INTO staff_obligations(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,source_obligation_identity,amount_due_ntd,due_date,status,current_event_id,payroll_version,payout_history_exists) '
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'open',%s,%s,0)",(child,row['assignment_id'],row['case_no'],row['staff_id'],kind,direction,row['obligation_identity'],abs(delta),row['due_date'],event,version))
    if not positive:
        StaffOverpaymentRecoveryCreationApplication(MySqlStaffOverpaymentRecoveryRepository(connection)).create_from_payroll_correction(
            StaffOverpaymentRecoveryCreationRequest(PayrollCorrectionRecoverySource(child,row['case_no'],row['obligation_identity'],int(row['staff_id']),MoneyNTD(abs(delta))),
                IdempotencyKey('manual-recovery:'+sha256(key.encode()).hexdigest()),ActorContext(actor),reason,CorrelationId('payroll-amount-correction')))


def persist_controlled_payroll_amount(connection,cursor,persistence,action):
    cursor.execute('SELECT * FROM payroll_amount_controls WHERE obligation_identity=%s FOR UPDATE',(action.obligation_identity,))
    control=cursor.fetchone()
    if not control:
        return False
    computed=action.after_amount.amount
    decision=payroll_amount_decision(control['amount_mode'],int(control['effective_ntd']),computed,'source_update',None)
    if computed!=int(control['computed_ntd']) or decision.delta_ntd:
        key='payroll-source:'+sha256((persistence.request.idempotency_key.value+':'+action.obligation_identity).encode()).hexdigest()
        _persist_amount(connection,cursor,persistence.request.case_no,action.obligation_identity,decision.mode,computed,decision.effective_ntd,int(control['effective_ntd']),
            'source_update',key,sha256(key.encode()).hexdigest(),persistence.request.actor.actor_id,persistence.request.reason,persistence.receipt.payroll_version)
    return True


def controlled_payroll_terms(cursor,command):
    """One-to-one source replacements carry the same person's amount mode.

    Paid roots remain immutable; their automatic corrections use this owner's
    separate-difference writer. A split or change of person creates new amounts
    and never copies one manual amount onto several salary obligations.
    """
    from subsystems.payroll.terms_impact import PayrollTermsActionKind
    controls={};handled=set();carry={}
    for action in command.candidate.actions:
        source=action.source_obligation_identity or action.obligation_identity
        cursor.execute('SELECT c.*,o.assignment_id,o.staff_id FROM payroll_amount_controls c JOIN staff_obligations o ON o.obligation_identity=c.obligation_identity WHERE c.obligation_identity=%s FOR UPDATE',(source,))
        control=cursor.fetchone()
        if control:
            controls[source]=control
            if action.action is PayrollTermsActionKind.CLOSE_UNPAID:
                matches=[a for a in command.candidate.actions if a.action is PayrollTermsActionKind.ESTABLISH and a.source_assignment_id==int(control['assignment_id']) and a.staff_id==int(control['staff_id'])]
                if len(matches)==1:
                    carry[matches[0].obligation_identity]=control
    for action in command.candidate.actions:
        source=action.source_obligation_identity or action.obligation_identity
        control=controls.get(source)
        if not control or action.action not in (PayrollTermsActionKind.APPEND_FROZEN_DIFFERENCE,PayrollTermsActionKind.KEEP_FROZEN) or source in handled:
            continue
        target=next((i for i in command.candidate.payroll.assignments if i.assignment_identity==action.candidate_assignment_key),None)
        settlement=next((s for s in command.candidate.frozen_settlements if s.obligation_identity==source),None)
        computed=settlement.revised_entitlement.amount if settlement else target.total_payable.amount if target else 0
        decision=payroll_amount_decision(control['amount_mode'],int(control['effective_ntd']),computed,'source_update',None)
        key='payroll-terms-amount:'+sha256((command.idempotency_key.value+':'+source).encode()).hexdigest()
        if computed!=int(control['computed_ntd']) or decision.delta_ntd:
            _persist_amount(cursor.connection,cursor,command.candidate.case_no,source,decision.mode,computed,decision.effective_ntd,int(control['effective_ntd']),
                'source_update',key,sha256(key.encode()).hexdigest(),command.actor.actor_id,command.reason,command.candidate.resulting_payroll_version)
        handled.add(source)
    return handled,carry


def carry_payroll_amount_control(cursor,command,action,control):
    computed=action.amount.amount
    effective=int(control['effective_ntd']) if control['amount_mode']=='manual' else computed
    key='payroll-carry-amount:'+sha256((command.idempotency_key.value+':'+action.obligation_identity).encode()).hexdigest()
    _persist_amount(cursor.connection,cursor,command.candidate.case_no,action.obligation_identity,control['amount_mode'],computed,effective,int(control['effective_ntd']),
        'source_update',key,sha256(key.encode()).hexdigest(),command.actor.actor_id,command.reason,command.candidate.resulting_payroll_version)
