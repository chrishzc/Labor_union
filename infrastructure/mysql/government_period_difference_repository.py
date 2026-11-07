"""Government owner differences over immutable whole-period bank evidence."""
from dataclasses import asdict,replace
from datetime import datetime
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from domains.government_subsidy.period_reconciliation import (
    GovernmentPeriodBalance, PeriodReconciliationConflict, SubsidyPeriod,
    require_government_initial_receipt, require_government_balance_action,
)
from subsystems.government_subsidy.period_reconciliation import GovernmentAmountItem, GovernmentPeriodOperation


def _today():
    return datetime.now(ZoneInfo('Asia/Taipei')).date()


def _digest(command):
    return sha256(json.dumps(asdict(command),sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def government_balance(row):
    return GovernmentPeriodBalance(row['balance_identity'],int(row['root_receipt_id']),row['balance_kind'],row['case_no'],row['direction'],
        int(row['expected_ntd']),int(row['received_ntd']),int(row['recognized_ntd']),int(row['returned_ntd']))


def period_difference_views(cursor,receipt_ids):
    if not receipt_ids:
        return (),()
    marks=','.join(['%s']*len(receipt_ids))
    cursor.execute(f'SELECT * FROM government_subsidy_period_balances WHERE root_receipt_id IN ({marks}) ORDER BY balance_identity',tuple(receipt_ids))
    balances=tuple(government_balance(row) for row in cursor.fetchall())
    cursor.execute('SELECT op.*,entry.finance_import_row_id FROM government_subsidy_period_operations op '
        'JOIN government_subsidy_period_balances b ON b.balance_identity=op.balance_identity '
        'LEFT JOIN government_subsidy_period_entries entry ON entry.id=op.bank_entry_id '
        f'WHERE b.root_receipt_id IN ({marks}) ORDER BY op.id',tuple(receipt_ids))
    operations=tuple(GovernmentPeriodOperation(int(r['id']),r['balance_identity'],r['action'],int(r['amount_ntd']),
        int(r['finance_import_row_id']) if r['finance_import_row_id'] else None,r['reason'],r['actor'],str(r['confirmed_on'])) for r in cursor.fetchall())
    return balances,operations


def apply_amount_controls(cursor,lines):
    result=[];items=[]
    for line in lines:
        cursor.execute('SELECT * FROM government_subsidy_amount_controls WHERE case_no=%s',(line.case_no,))
        row=cursor.fetchone()
        mode=row['amount_mode'] if row else 'automatic'
        effective=int(row['effective_ntd']) if row and mode=='manual' else line.amount_ntd
        result.append(replace(line,amount_ntd=effective,unavailable_reason=None if effective is not None else line.unavailable_reason))
        items.append(GovernmentAmountItem(line.case_no,mode,line.amount_ntd,effective))
    return tuple(result),tuple(items)


def recorded_case_amount_control(connection,cursor,line):
    """A moved case can still be corrected from its original frozen period."""
    from subsystems.government_subsidy.reconciliation_register_query import _select_established_cases,project_receivable_estimate
    cursor.execute('SELECT COALESCE(actual_end_date,end_date) end_date FROM orders WHERE case_no=%s',(line.case_no,))
    row=cursor.fetchone();end=row['end_date'] if row else None
    computed=None
    if end:
        period=SubsidyPeriod('month',end.year,end.month)
        source=next((s for s in _select_established_cases(connection,period.start,period.end) if s['case_no']==line.case_no),None)
        if source:computed=project_receivable_estimate(source).amount_ntd
    cursor.execute('SELECT amount_mode,effective_ntd FROM government_subsidy_amount_controls WHERE case_no=%s',(line.case_no,))
    control=cursor.fetchone()
    mode=control['amount_mode'] if control else 'automatic'
    effective=int(control['effective_ntd']) if control and mode=='manual' else computed if computed is not None else line.amount_ntd
    return GovernmentAmountItem(line.case_no,mode,computed,effective)


def initialize_balance(cursor,receipt_id,expected,received):
    identity=f'government-period:{receipt_id}'
    cursor.execute('INSERT IGNORE INTO government_subsidy_period_balances(balance_identity,root_receipt_id,balance_kind,case_no,direction,expected_ntd,received_ntd) '
        "VALUES(%s,%s,'original',NULL,'receivable',%s,%s)",(identity,receipt_id,expected,received))
    return identity


def _operation(cursor,command,identity,amount,bank_entry=None):
    cursor.execute('INSERT INTO government_subsidy_period_operations(balance_identity,action,amount_ntd,bank_entry_id,operation_key,command_digest,actor,reason,confirmed_on) '
        'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(identity,'receipt' if command.action=='initial_receipt' else command.action,amount,bank_entry,command.key,_digest(command),command.actor,command.reason,_today()))


def save_initial_period_receipt(repository, command, view, amount):
    """Original first-receipt policy/save, shared by bank and typed manual source."""
    expected = require_government_initial_receipt(view.lines, amount, command.handling)
    original = repository.save(replace(view, total_ntd=amount), command.bank_row_id, command.key, command.actor)
    with repository.connection.cursor() as cursor:
        cursor.execute('UPDATE government_subsidy_period_balances SET expected_ntd=%s WHERE root_receipt_id=%s AND balance_kind=%s', (expected, original, 'original'))
        _operation(cursor, command, f'government-period:{original}', amount)
    return original


def apply_government_difference(repository,command):
    connection=repository.connection
    with connection.cursor() as cursor:
        for table in ('government_subsidy_period_operations','government_subsidy_amount_changes'):
            cursor.execute(f'SELECT command_digest FROM {table} WHERE operation_key=%s FOR UPDATE',(command.key,))
            replay=cursor.fetchone()
            if replay:
                if replay['command_digest']!=_digest(command):
                    raise PeriodReconciliationConflict('subsidy_period_command_changed')
                return repository.query(command.period)
        view=repository.query(command.period,lock=True)
        if view.version!=command.expected_version:
            raise PeriodReconciliationConflict('subsidy_period_stale')
        if command.action in ('manual_amount','adopt_calculation'):
            _correct_case(cursor,command,view)
        elif command.action=='initial_receipt':
            if view.coverage or view.blocked_cases:
                raise PeriodReconciliationConflict('subsidy_period_already_covered')
            amount=repository.bank_amount(command.bank_row_id)
            save_initial_period_receipt(repository, command, view, amount)
            # save has advanced the same year inside this transaction.
            return repository.query(command.period)
        else:
            balance=next((b for b in view.balances if b.identity==command.identity),None)
            if not balance:
                # Old exact receipts receive an owner projection lazily only on
                # an explicit new command; Query stays strictly read-only.
                old=next((c for c in view.coverage if f'government-period:{c.receipt_id}'==command.identity),None)
                if not old:
                    raise PeriodReconciliationConflict('subsidy_period_balance_missing')
                expected=sum(l.amount_ntd for l in view.recorded_lines)
                initialize_balance(cursor,old.receipt_id,expected,old.amount_ntd)
                balance=GovernmentPeriodBalance(command.identity,old.receipt_id,'original',None,'receivable',expected,old.amount_ntd,0,0)
            amount=repository.bank_amount(command.bank_row_id,reversal=command.action=='refund') if command.action in ('receipt','refund') else command.amount_ntd
            require_government_balance_action(balance,command.action,amount,command.reason)
            if command.action=='receipt' and amount>max(0,balance.expected_ntd-balance.received_ntd) and command.handling!='refund_excess':
                raise PeriodReconciliationConflict('subsidy_period_handling_required')
            bank_entry=None
            if command.action in ('receipt','refund'):
                cursor.execute('SELECT * FROM government_subsidy_period_entries WHERE id=%s',(balance.root_receipt_id,))
                root=cursor.fetchone()
                period=SubsidyPeriod(root['period_unit'],int(root['period_year']),int(root['period_index']))
                bank_entry=repository._insert(cursor,period,command.bank_row_id,amount,None,command.key,command.actor)
                cursor.execute('INSERT INTO government_subsidy_period_members(receipt_id,case_no,service_end_date,amount_ntd) '
                    'SELECT %s,case_no,service_end_date,amount_ntd FROM government_subsidy_period_members WHERE receipt_id=%s',(bank_entry,balance.root_receipt_id))
            if command.action=='receipt':
                column='received_ntd'
            elif command.action=='loss':
                column='recognized_ntd'
            else:
                column='returned_ntd' if balance.direction=='receivable' else 'received_ntd'
            cursor.execute(f'UPDATE government_subsidy_period_balances SET {column}={column}+%s WHERE balance_identity=%s',(amount,balance.identity))
            _operation(cursor,command,balance.identity,amount,bank_entry)
        repository._advance_version(cursor,command.period.year)
    return repository.query(command.period)


def _correct_case(cursor,command,view):
    item=next((i for i in view.amount_controls if i.case_no==command.identity),None)
    if not item or not command.reason.strip():
        raise PeriodReconciliationConflict('subsidy_case_amount_invalid')
    after=item.computed_ntd if command.action=='adopt_calculation' else command.amount_ntd
    if after is None or after<0:
        raise PeriodReconciliationConflict('subsidy_case_calculation_unavailable')
    cursor.execute('SELECT effective_ntd FROM government_subsidy_amount_controls WHERE case_no=%s FOR UPDATE',(item.case_no,))
    current=cursor.fetchone()
    before=int(current['effective_ntd']) if current else item.effective_ntd
    if before is None:
        raise PeriodReconciliationConflict('subsidy_case_amount_unavailable')
    mode='manual' if command.action=='manual_amount' else 'automatic'
    cursor.execute('INSERT INTO government_subsidy_amount_controls(case_no,period_year,amount_mode,computed_ntd,effective_ntd) VALUES(%s,%s,%s,%s,%s) '
        'ON DUPLICATE KEY UPDATE period_year=VALUES(period_year),amount_mode=VALUES(amount_mode),computed_ntd=VALUES(computed_ntd),effective_ntd=VALUES(effective_ntd)',
        (item.case_no,command.period.year,mode,item.computed_ntd if item.computed_ntd is not None else before,after))
    cursor.execute('INSERT INTO government_subsidy_amount_changes(case_no,action,before_ntd,after_ntd,computed_ntd,operation_key,command_digest,actor,reason,confirmed_on) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        (item.case_no,command.action,before,after,item.computed_ntd if item.computed_ntd is not None else before,command.key,_digest(command),command.actor,command.reason,_today()))
    delta=after-before
    if delta:
        _append_case_correction(cursor,item.case_no,delta,command.key,expected_year=command.period.year)


def _append_case_correction(cursor,case_no,delta,key,expected_year=None):
    cursor.execute('SELECT member.receipt_id,entry.period_year FROM government_subsidy_period_members member JOIN government_subsidy_period_entries entry ON entry.id=member.receipt_id '
        'WHERE member.case_no=%s AND entry.reversal_of_id IS NULL '
        'AND NOT EXISTS(SELECT 1 FROM government_subsidy_period_entries r WHERE r.reversal_of_id=entry.id) '
        'AND NOT EXISTS(SELECT 1 FROM government_subsidy_period_operations op WHERE op.bank_entry_id=entry.id) ORDER BY entry.id FOR UPDATE',(case_no,))
    roots=cursor.fetchall()
    if len(roots)>1:
        raise PeriodReconciliationConflict('subsidy_case_period_ambiguous')
    if roots and expected_year is not None and int(roots[0]['period_year'])!=expected_year:
        raise PeriodReconciliationConflict('subsidy_case_original_period_required')
    if roots:
        identity='government-correction:'+sha256((case_no+':'+key).encode()).hexdigest()
        cursor.execute('INSERT INTO government_subsidy_period_balances(balance_identity,root_receipt_id,balance_kind,case_no,direction,expected_ntd) '
            "VALUES(%s,%s,'correction',%s,%s,%s)",(identity,roots[0]['receipt_id'],case_no,'receivable' if delta>0 else 'payable',abs(delta)))


def synchronize_government_case_amount(cursor,case_no,key,actor,reason):
    """Borrow the source writer UoW; frozen period evidence is never rewritten."""
    cursor.execute('SELECT * FROM government_subsidy_amount_controls WHERE case_no=%s FOR UPDATE',(case_no,))
    control=cursor.fetchone()
    # Frozen cases also need automatic correction differences even without a
    # prior manual edit. Unpaid/unfrozen cases already query the live formula.
    cursor.execute('SELECT member.amount_ntd,entry.period_year FROM government_subsidy_period_members member '
        'JOIN government_subsidy_period_entries entry ON entry.id=member.receipt_id WHERE member.case_no=%s '
        'AND entry.reversal_of_id IS NULL AND NOT EXISTS(SELECT 1 FROM government_subsidy_period_entries r WHERE r.reversal_of_id=entry.id) '
        'AND NOT EXISTS(SELECT 1 FROM government_subsidy_period_operations op WHERE op.bank_entry_id=entry.id) ORDER BY entry.id',(case_no,))
    frozen=cursor.fetchall()
    if not control and not frozen:
        return
    from subsystems.government_subsidy.reconciliation_register_query import _select_established_cases,project_receivable_estimate
    cursor.execute('SELECT COALESCE(actual_end_date,end_date) end_date FROM orders WHERE case_no=%s',(case_no,))
    end=cursor.fetchone()['end_date']
    if end is None:
        return
    period=SubsidyPeriod('month',end.year,end.month)
    sources=_select_established_cases(cursor.connection,period.start,period.end,lock=False)
    amounts={s['case_no']:project_receivable_estimate(s).amount_ntd for s in sources}
    computed=amounts.get(case_no)
    if computed is None:
        return
    before=int(control['effective_ntd']) if control else int(frozen[0]['amount_ntd'])
    mode=control['amount_mode'] if control else 'automatic'
    after=before if mode=='manual' else computed
    if control and int(control['computed_ntd'])==computed and before==after:
        return
    year=int(frozen[0]['period_year']) if frozen else end.year
    cursor.execute('INSERT IGNORE INTO government_subsidy_period_years(period_year) VALUES(%s)',(year,))
    cursor.execute('SELECT aggregate_version FROM government_subsidy_period_years WHERE period_year=%s FOR UPDATE',(year,));cursor.fetchone()
    cursor.execute('INSERT INTO government_subsidy_amount_controls(case_no,period_year,amount_mode,computed_ntd,effective_ntd) VALUES(%s,%s,%s,%s,%s) '
        'ON DUPLICATE KEY UPDATE computed_ntd=VALUES(computed_ntd),effective_ntd=VALUES(effective_ntd)',(case_no,year,mode,computed,after))
    eventkey='government-source:'+sha256((str(key)+':'+case_no).encode()).hexdigest()
    cursor.execute('INSERT INTO government_subsidy_amount_changes(case_no,action,before_ntd,after_ntd,computed_ntd,operation_key,command_digest,actor,reason,confirmed_on) '
        "VALUES(%s,'source_update',%s,%s,%s,%s,%s,%s,%s,%s)",(case_no,before,after,computed,eventkey,sha256(eventkey.encode()).hexdigest(),actor,reason,_today()))
    if after!=before:
        _append_case_correction(cursor,case_no,after-before,eventkey)
    cursor.execute('UPDATE government_subsidy_period_years SET aggregate_version=aggregate_version+1 WHERE period_year=%s',(year,))
