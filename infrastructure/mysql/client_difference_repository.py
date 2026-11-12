"""
File: client_difference_repository.py
Description: 客戶帳務差額處置與金額更正寫入器，保留真實金流，更正退款缺受款帳戶允許保持待補。
"""
from dataclasses import replace
from datetime import datetime
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from domains.client_finance.difference_resolution import (
    ClientDifferenceConflict, ClientDifferenceTarget, CLIENT_DIFFERENCE_LABELS,
    client_difference_options, require_client_disposition, plan_client_amount_change,
)
from subsystems.client_finance.difference_resolution import (
    ClientDifferenceItem, ClientDifferenceView, ClientDifferenceEvent,
)


def _today():
    return datetime.now(ZoneInfo('Asia/Taipei')).date()


def _digest(command):
    return sha256(json.dumps({name: getattr(command, name) for name in command.__dataclass_fields__},
                             sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _cash(cursor, identity):
    cursor.execute("SELECT COALESCE(SUM(CASE WHEN l.entry_type IN ('reversal','subsidy_return_reversal') "
                   "THEN -a.amount_ntd ELSE a.amount_ntd END),0) amount FROM client_ledger_obligation_allocations a "
                   "JOIN client_ledger_entries l ON l.id=a.ledger_entry_id WHERE a.obligation_identity=%s "
                   "AND l.entry_type IN ('receipt','refund','subsidy_return','subsidy_advance','reversal','subsidy_return_reversal')",(identity,))
    return int(cursor.fetchone()['amount'])


def _noncash(cursor, identity):
    cursor.execute('SELECT COALESCE(SUM(amount_ntd),0) amount FROM client_finance_noncash_events WHERE target_identity=%s',(identity,))
    return int(cursor.fetchone()['amount'])


class MySqlClientDifferenceRepository:
    def __init__(self, connection):
        self.connection = connection

    def replay(self, command):
        with self.connection.cursor() as cursor:
            for table in ('client_finance_amount_changes','client_finance_noncash_events'):
                cursor.execute(f'SELECT command_digest FROM {table} WHERE operation_key=%s FOR UPDATE',(command.key,))
                row = cursor.fetchone()
                if row:
                    if row['command_digest'] != _digest(command):
                        raise ClientDifferenceConflict('client_difference_command_changed')
                    return self.query(command.case_no)
        # close_refund intentionally has no extra operation/audit record. Replay is
        # the already-closed owner state, with the original expected version.
        return None

    def query(self, case_no):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s',(case_no,))
            root = cursor.fetchone()
            if not root:
                raise ClientDifferenceConflict('client_finance_account_missing')
            cursor.execute('SELECT o.*,e.after_amount_ntd nominal,c.amount_mode,c.computed_ntd,c.effective_ntd,source.direction source_direction '
                'FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id '
                'LEFT JOIN client_finance_amount_controls c ON c.obligation_identity=o.obligation_identity '
                'LEFT JOIN client_obligations source ON source.obligation_identity=o.source_obligation_identity '
                "WHERE o.case_no=%s AND o.status<>'cancelled' ORDER BY o.due_date,o.obligation_identity",(case_no,))
            rows = cursor.fetchall()
            from infrastructure.mysql.client_payments_query_repository import query_case_accounting
            projected={i.identity:i for i in query_case_accounting(self.connection,case_no)[0]}
            computed = _latest_stage_computations(cursor, case_no)
            items = []
            for row in rows:
                actual, noncash = _cash(cursor,row['obligation_identity']), _noncash(cursor,row['obligation_identity'])
                expected = int(row['amount_due_ntd']) + actual + noncash
                # State-only refund closure preserves nominal payable without a waiver event.
                if row['status']=='settled' and not noncash:
                    expected = max(expected,int(row['nominal']))
                kind='over_refund_correction' if row['obligation_type']=='adjustment' and row['source_direction']=='payable_to_client' else row['obligation_type']
                target=ClientDifferenceTarget(row['obligation_identity'],kind,row['direction'],expected,actual,int(row['amount_due_ntd']),noncash)
                raw = computed.get(row['obligation_type'],int(row['computed_ntd'] if row['computed_ntd'] is not None else expected))
                cursor.execute('SELECT action FROM client_finance_noncash_events WHERE target_identity=%s ORDER BY id DESC LIMIT 1',(target.identity,))
                event=cursor.fetchone()
                cursor.execute("SELECT COALESCE(SUM(amount_ntd),0) amount FROM client_finance_noncash_events WHERE target_identity=%s AND action='reduce_service_fee'",(target.identity,))
                reduction=int(cursor.fetchone()['amount'])
                status = ('仍有餘額待處理' if target.remaining_ntd else CLIENT_DIFFERENCE_LABELS[event['action']] if event else
                    '已確認不用再退款' if row['direction']=='payable_to_client' and row['status']=='settled' and actual<expected else
                    '已結清' if row['status']=='settled' else '待處理')
                items.append(ClientDifferenceItem(target.identity,{'deposit':'訂金','first':'第一期','second':'第二期','refund':'客戶退款','subsidy_return':'補助退款','adjustment':'更正差額','over_refund_correction':'退款更正後待追回差額'}.get(target.kind,target.kind),
                    target.kind,target.direction,expected,projected[target.identity].actual_ntd if target.identity in projected else actual,target.remaining_ntd,noncash,row['amount_mode'] or 'automatic',raw,
                    int(row['effective_ntd']) if row['effective_ntd'] is not None else expected,status,client_difference_options(target),reduction,
                    max(0,(int(row['effective_ntd']) if row['effective_ntd'] is not None else expected)-reduction)))
            cursor.execute('SELECT r.*,e.after_amount_ntd original FROM client_over_refund_recoveries r '
                           "JOIN client_over_refund_recovery_events e ON e.recovery_identity=r.recovery_identity AND e.event_type='established' WHERE r.case_no=%s",(case_no,))
            for row in cursor.fetchall():
                noncash = _noncash(cursor,row['recovery_identity'])
                original=int(row['original']); remaining=int(row['amount_due_ntd']) if row['status'] in ('open','partially_recovered') else 0
                target=ClientDifferenceTarget(row['recovery_identity'],'over_refund_recovery','receivable_from_client',original,max(0,original-remaining-noncash),remaining,noncash)
                items.append(ClientDifferenceItem(target.identity,'客戶退款超付追償',target.kind,target.direction,original,target.actual_ntd,remaining,noncash,'automatic',original,original,
                    '待追償' if remaining else '已作差額處理' if noncash else '已追回',tuple(x for x in client_difference_options(target) if x not in ('manual_amount','adopt_calculation'))))
            cursor.execute('SELECT id,target_identity,action,amount_ntd,reason,actor,confirmed_on FROM client_finance_noncash_events WHERE case_no=%s ORDER BY id',(case_no,))
            events=[ClientDifferenceEvent(f'client-noncash:{r["id"]}',r['target_identity'],r['action'],int(r['amount_ntd']),r['reason'],r['actor'],str(r['confirmed_on'])) for r in cursor.fetchall()]
            cursor.execute('SELECT a.* FROM client_finance_amount_changes a JOIN client_obligations o ON o.obligation_identity=a.obligation_identity WHERE o.case_no=%s ORDER BY a.id',(case_no,))
            events += [ClientDifferenceEvent(f'client-amount:{r["id"]}',r['obligation_identity'],r['action'],int(r['after_ntd'])-int(r['before_ntd']),r['reason'],r['actor'],str(r['confirmed_on']),int(r['before_ntd']),int(r['after_ntd']),int(r['computed_ntd'])) for r in cursor.fetchall()]
        return ClientDifferenceView(case_no,int(root['aggregate_version']),tuple(items),tuple(events))

    def apply(self, command):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s FOR UPDATE',(command.case_no,))
            account=cursor.fetchone()
            if not account:
                raise ClientDifferenceConflict('client_finance_account_missing')
            cursor.execute('SELECT case_no FROM finance_case_accounting_markers WHERE case_no=%s',(command.case_no,))
            if cursor.fetchone():
                raise ClientDifferenceConflict('historical_case_already_settled')
            view = self.query(command.case_no)
            item=next((x for x in view.items if x.identity==command.identity),None)
            if item is None:
                raise ClientDifferenceConflict('client_difference_target_missing')
            if command.action=='close_refund' and item.remaining_ntd==0 and item.status=='已確認不用再退款' and view.version==command.expected_version+1:
                return view
            if int(account['aggregate_version'])!=command.expected_version:
                raise ClientDifferenceConflict('client_difference_stale')
            target=ClientDifferenceTarget(item.identity,item.kind,item.direction,item.expected_ntd,item.actual_ntd,item.remaining_ntd,item.noncash_ntd)
            if command.action in ('manual_amount','adopt_calculation'):
                effective=item.computed_ntd if command.action=='adopt_calculation' else command.amount_ntd
                if effective is None or not command.reason.strip() or item.kind=='over_refund_recovery':
                    raise ClientDifferenceConflict('client_amount_correction_invalid')
                before=item.effective_ntd
                _set_client_amount(cursor,command.case_no,item.identity,effective,before,command.key,command.actor,command.reason,command.expected_version+1)
                cursor.execute('INSERT INTO client_finance_amount_controls(obligation_identity,case_no,amount_mode,computed_ntd,effective_ntd) VALUES(%s,%s,%s,%s,%s) '
                    'ON DUPLICATE KEY UPDATE amount_mode=VALUES(amount_mode),computed_ntd=VALUES(computed_ntd),effective_ntd=VALUES(effective_ntd)',
                    (item.identity,command.case_no,'manual' if command.action=='manual_amount' else 'automatic',item.computed_ntd,effective))
                _amount_event(cursor,item.identity,command.action,before,effective,item.computed_ntd,command.key,_digest(command),command.actor,command.reason)
            else:
                amount=item.remaining_ntd if command.action=='close_refund' else command.amount_ntd
                remaining=require_client_disposition(target,command.action,amount,command.reason)
                table='client_over_refund_recoveries' if item.kind=='over_refund_recovery' else 'client_obligations'
                column='recovery_identity' if item.kind=='over_refund_recovery' else 'obligation_identity'
                status=('partially_recovered' if remaining else 'adjusted') if item.kind=='over_refund_recovery' else ('open' if remaining else 'settled')
                cursor.execute(f'UPDATE {table} SET amount_due_ntd=%s,status=%s,projection_version=%s WHERE {column}=%s AND case_no=%s',
                    (remaining,status,command.expected_version+1,item.identity,command.case_no))
                if command.action!='close_refund':
                    cursor.execute('INSERT INTO client_finance_noncash_events(case_no,target_identity,target_kind,action,original_ntd,amount_ntd,before_remaining_ntd,after_remaining_ntd,operation_key,command_digest,actor,reason,confirmed_on) '
                        'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(command.case_no,item.identity,'over_refund_recovery' if item.kind=='over_refund_recovery' else 'obligation',command.action,item.expected_ntd,amount,item.remaining_ntd,remaining,command.key,_digest(command),command.actor,command.reason,_today()))
            cursor.execute('UPDATE client_finance_accounts SET aggregate_version=aggregate_version+1 WHERE case_no=%s AND aggregate_version=%s',(command.case_no,command.expected_version))
            if cursor.rowcount!=1:
                raise ClientDifferenceConflict('client_difference_stale')
        return self.query(command.case_no)


def _amount_event(cursor,identity,action,before,after,computed,key,digest,actor,reason):
    cursor.execute('INSERT INTO client_finance_amount_changes(obligation_identity,action,before_ntd,after_ntd,computed_ntd,operation_key,command_digest,actor,reason,confirmed_on) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        (identity,action,before,after,computed,key,digest,actor,reason,_today()))


def persist_historical_source_amounts(connection, plan, actor, reason, key):
    """Borrow the original correction writer and the caller's outer transaction."""
    if not plan.client_changed:
        return
    with connection.cursor() as cursor:
        cursor.execute('SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s FOR UPDATE', (plan.case_no,))
        if int(cursor.fetchone()['aggregate_version']) != plan.client_version:
            raise ClientDifferenceConflict('client_difference_stale')
        version = plan.client_version + 1
        for item in plan.client_updates:
            if item.computed == item.before_computed and item.effective == item.before_effective:
                continue
            child = 'historical-client-source:' + sha256((key + ':' + item.identity).encode()).hexdigest()
            if plan.new_deposit is not None and item.identity == plan.new_deposit[0]:
                due_date = plan.new_deposit[1]
                direction = 'receivable_from_client'
                event = _obligation_event(cursor, {'case_no': plan.case_no, 'due_date': due_date},
                    item.identity, 'deposit', direction, 0, item.effective, child, actor, reason,
                    version, None, establishing=True)
                cursor.execute('INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) '
                    "VALUES(%s,%s,'deposit',%s,%s,%s,'open',%s,%s)",
                    (item.identity, plan.case_no, direction, item.effective, due_date, event, version))
            else:
                _set_client_amount(cursor, plan.case_no, item.identity, item.effective, item.before_effective, child, actor, reason, version)
            _amount_event(cursor, item.identity, 'source_update', item.before_effective, item.effective, item.computed, child, sha256(child.encode()).hexdigest(), actor, reason)
            cursor.execute('INSERT INTO client_finance_amount_controls(obligation_identity,case_no,amount_mode,computed_ntd,effective_ntd) '
                'VALUES(%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE computed_ntd=VALUES(computed_ntd),effective_ntd=VALUES(effective_ntd)',
                (item.identity,plan.case_no,item.mode,item.computed,item.effective))
        cursor.execute('UPDATE client_finance_accounts SET aggregate_version=%s WHERE case_no=%s', (version,plan.case_no))
        cursor.execute("INSERT INTO client_finance_outbox(case_no,intent_type,intent_key,payload_snapshot) VALUES(%s,'projection_refresh',%s,%s)",
            (plan.case_no,'historical-pricing:'+sha256(key.encode()).hexdigest(),json.dumps({'case_no':plan.case_no,'account_version':version})))


def _latest_stage_computations(cursor,case_no):
    # Reuse the owner formula. An incomplete source remains unavailable; it is
    # never interpreted as a new zero amount.
    from infrastructure.mysql.order_terms_read_model import select_order,load_calculable_client_finance_facts
    from domains.client_finance.obligation_planning import _build_stage_plans
    order=select_order(cursor,case_no,lock=False)
    if order is None or any(order.get(name) is None for name in ('start_date','service_days','service_hours_per_day','floor_fee')):
        return {}
    cursor.execute('SELECT case_no FROM client_payment_terms WHERE case_no=%s',(case_no,))
    if cursor.fetchone() is None:
        return {}
    try:
        facts,_=load_calculable_client_finance_facts(cursor,order,lock=False,
            allow_planned=str(order['status']) not in ('訂單完成','訂單取消'))
        return {p.payment_stage.value:p.amount.amount for p in _build_stage_plans(facts)} if facts else {}
    except ValueError as error:
        # Existing historical sources may legitimately lack calculable service
        # facts. All other failures must remain visible to the caller.
        if str(error) not in ('client_finance_terms_source_incomplete','client_finance_actual_service_required','formal client obligation history must be exactly settled','client_finance_service_facts_missing'):
            raise
        return {}


def _set_client_amount(cursor,case_no,identity,effective,before,key,actor,reason,version):
    cursor.execute('SELECT o.*,e.after_amount_ntd nominal FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id WHERE o.obligation_identity=%s AND o.case_no=%s FOR UPDATE',(identity,case_no))
    row=cursor.fetchone()
    if not row:
        raise ClientDifferenceConflict('client_difference_target_missing')
    cash,noncash=_cash(cursor,identity),_noncash(cursor,identity)
    target=ClientDifferenceTarget(identity,row['obligation_type'],row['direction'],before,cash,int(row['amount_due_ntd']),noncash)
    frozen=row['status']=='settled' or _has_separate_correction(cursor,identity)
    plan=plan_client_amount_change(target,effective,frozen=frozen)
    if effective==before:
        return
    if not frozen:
        event=_obligation_event(cursor,row,identity,row['obligation_type'],row['direction'],int(row['nominal']),effective,key,actor,reason,version,None)
        cursor.execute('UPDATE client_obligations SET amount_due_ntd=%s,status=%s,current_event_id=%s,projection_version=%s WHERE obligation_identity=%s',
            (plan.remaining_ntd,'open' if plan.remaining_ntd else 'settled',event,version,identity))
    if plan.separate_amount_ntd:
        amount=_correct_unpaid_opposite(cursor,row,plan.separate_direction,plan.separate_amount_ntd,key,actor,reason,version)
        if not amount:
            return
        child='client-correction:'+sha256((identity+':'+key).encode()).hexdigest()
        kind='refund' if plan.separate_direction=='payable_to_client' else 'adjustment'
        event=_obligation_event(cursor,row,child,kind,plan.separate_direction,0,amount,key,actor,reason,version,identity)
        cursor.execute('INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,source_obligation_identity,amount_due_ntd,due_date,status,current_event_id,projection_version) '
            "VALUES(%s,%s,%s,%s,%s,%s,%s,'open',%s,%s)",(child,case_no,kind,plan.separate_direction,identity,amount,row['due_date'],event,version))
        if kind=='refund':
            cursor.execute('INSERT INTO client_refund_recipient_snapshots(refund_obligation_identity,case_no,bank_code,bank_account,source_kind) '
                "SELECT %s,case_no,bank_code,bank_account,'amount_correction' FROM client_refund_recipient_snapshots WHERE refund_obligation_identity=%s",(child,identity))
            if cursor.rowcount==0:
                from infrastructure.mysql.client_receipt_reconciliation_repository import _insert_refund_recipient_snapshot
                _insert_refund_recipient_snapshot(cursor,child,case_no,'amount_correction',require_complete=False)


def _correct_unpaid_opposite(cursor,source,direction,amount,key,actor,reason,version):
    """Recalculate unconsumed differences of this exact source first.

    This never offsets bank cash, other cases, manual amounts or a child with
    payment history. It prevents a repeated correction from manufacturing both
    a new refund and an obsolete, entirely unpaid collection for the same cause.
    """
    cursor.execute('SELECT o.*,e.after_amount_ntd nominal FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id '
        "WHERE o.source_obligation_identity=%s AND o.obligation_identity LIKE 'client-correction:%%' AND o.status='open' AND o.direction<>%s "
        'AND NOT EXISTS(SELECT 1 FROM client_ledger_obligation_allocations a WHERE a.obligation_identity=o.obligation_identity) '
        'AND NOT EXISTS(SELECT 1 FROM client_finance_noncash_events n WHERE n.target_identity=o.obligation_identity) '
        "AND NOT EXISTS(SELECT 1 FROM client_finance_amount_controls c WHERE c.obligation_identity=o.obligation_identity AND c.amount_mode='manual') ORDER BY o.obligation_identity FOR UPDATE",(source['obligation_identity'],direction))
    for row in cursor.fetchall():
        if not amount:
            break
        corrected=min(amount,int(row['amount_due_ntd']));remaining=int(row['amount_due_ntd'])-corrected
        event=_obligation_event(cursor,row,row['obligation_identity'],row['obligation_type'],row['direction'],int(row['nominal']),int(row['nominal'])-corrected,key+':pending',actor,reason,version,row['source_obligation_identity'])
        cursor.execute('UPDATE client_obligations SET amount_due_ntd=%s,status=%s,current_event_id=%s,projection_version=%s WHERE obligation_identity=%s',
            (remaining,'open' if remaining else 'cancelled',event,version,row['obligation_identity']))
        cursor.execute("UPDATE client_finance_amount_controls SET computed_ntd=%s,effective_ntd=%s WHERE obligation_identity=%s AND amount_mode='automatic'",(int(row['nominal'])-corrected,int(row['nominal'])-corrected,row['obligation_identity']))
        amount-=corrected
    return amount


def _has_separate_correction(cursor,identity):
    cursor.execute("SELECT 1 FROM client_obligations WHERE source_obligation_identity=%s AND obligation_identity LIKE 'client-correction:%%' LIMIT 1",(identity,))
    return cursor.fetchone() is not None


def _obligation_event(cursor,row,identity,kind,direction,before,after,key,actor,reason,version,source,*,establishing=False):
    eventkey='client-amount:'+sha256((key+':'+identity).encode()).hexdigest()
    cursor.execute('INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,source_event_identity,source_obligation_identity,expected_account_version,idempotency_key,actor,reason) '
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(identity,row['case_no'],kind,direction,'established' if establishing or source is not None else 'adjusted',before,after,row['due_date'] if before else None,row['due_date'],eventkey,source,version-1,eventkey,actor,reason))
    return int(cursor.lastrowid)


def persist_controlled_client_stage(cursor, command, stage):
    """Intercept only amounts already under manual/control or noncash treatment."""
    return persist_controlled_client_amount(cursor,command,stage.payment_stage.value,stage.amount.amount,stage.due_date)[0]


def persist_controlled_client_amount(cursor,command,kind,computed,due_date=None):
    cursor.execute('SELECT o.obligation_identity,o.status,c.amount_mode,c.computed_ntd,c.effective_ntd FROM client_obligations o '
        'LEFT JOIN client_finance_amount_controls c ON c.obligation_identity=o.obligation_identity '
        'WHERE o.case_no=%s AND o.obligation_type=%s FOR UPDATE',(command.candidate.case_no,kind))
    row=cursor.fetchone()
    if not row:
        return False,False
    identity=row['obligation_identity']
    if row['amount_mode'] is None and not _noncash(cursor,identity) and row['status']!='settled':
        return False,False
    if row['amount_mode'] is None:
        cursor.execute('SELECT e.after_amount_ntd FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id WHERE o.obligation_identity=%s',(identity,))
        before=int(cursor.fetchone()['after_amount_ntd'])
        cursor.execute("INSERT INTO client_finance_amount_controls(obligation_identity,case_no,amount_mode,computed_ntd,effective_ntd) VALUES(%s,%s,'automatic',%s,%s)",(identity,command.candidate.case_no,before,before))
        row={**row,'amount_mode':'automatic','computed_ntd':before,'effective_ntd':before}
    effective=int(row['effective_ntd']) if row['amount_mode']=='manual' else computed
    changed=False
    key='client-source:'+sha256((command.idempotency_key.value+':'+identity).encode()).hexdigest()
    if computed!=int(row['computed_ntd']) or effective!=int(row['effective_ntd']):
        _set_client_amount(cursor,command.candidate.case_no,identity,effective,int(row['effective_ntd']),key,command.actor.actor_id,command.reason,command.candidate.resulting_account_version)
        _amount_event(cursor,identity,'source_update',int(row['effective_ntd']),effective,computed,key,sha256(key.encode()).hexdigest(),command.actor.actor_id,command.reason)
        cursor.execute('UPDATE client_finance_amount_controls SET computed_ntd=%s,effective_ntd=%s WHERE obligation_identity=%s',(computed,effective,identity))
        changed=True
    cursor.execute('SELECT o.*,e.after_amount_ntd nominal FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id WHERE o.obligation_identity=%s FOR UPDATE',(identity,))
    source=cursor.fetchone()
    if source['status']=='open' and source['due_date']!=due_date:
        date_key=key+':due'
        cursor.execute('INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,source_event_identity,source_obligation_identity,expected_account_version,idempotency_key,actor,reason) '
            "VALUES(%s,%s,%s,%s,'adjusted',%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s)",(identity,source['case_no'],source['obligation_type'],source['direction'],int(source['nominal']),int(source['nominal']),source['due_date'],due_date,date_key,command.candidate.expected_account_version,date_key,command.actor.actor_id,command.reason))
        cursor.execute('UPDATE client_obligations SET due_date=%s,current_event_id=%s,projection_version=%s WHERE obligation_identity=%s',(due_date,int(cursor.lastrowid),command.candidate.resulting_account_version,identity))
        changed=True
    return True,changed
