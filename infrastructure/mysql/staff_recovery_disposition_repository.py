"""Staff Payables recovery root noncash writer; preserves every payout source."""
from hashlib import sha256
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from domains.staff_payables.overpayment_recovery import require_recovery_noncash_disposition
from subsystems.staff_payables.recovery_disposition import (
    StaffRecoveryDispositionItem, StaffRecoveryDispositionEvent, StaffRecoveryDispositionView,
)


class StaffRecoveryDispositionConflict(ValueError):
    pass


def _digest(command):
    return sha256(json.dumps({k:getattr(command,k) for k in command.__dataclass_fields__},sort_keys=True,ensure_ascii=False).encode()).hexdigest()


class MySqlStaffRecoveryDispositionRepository:
    def __init__(self,connection):
        self.connection=connection

    def query(self,case_no):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT r.*,s.name party,COALESCE((SELECT SUM(n.amount_ntd) FROM staff_recovery_noncash_events n WHERE n.recovery_identity=r.recovery_identity),0) noncash '
                'FROM staff_overpayment_recoveries r JOIN staff s ON s.id=r.staff_id '
                'WHERE EXISTS(SELECT 1 FROM staff_obligations o WHERE o.case_no=%s AND JSON_CONTAINS(r.source_obligation_identities,JSON_QUOTE(o.obligation_identity))) ORDER BY r.recovery_identity',(case_no,))
            rows=cursor.fetchall()
            items=[];events=[]
            for r in rows:
                cursor.execute('SELECT DISTINCT o.case_no FROM staff_obligations o WHERE JSON_CONTAINS(%s,JSON_QUOTE(o.obligation_identity)) ORDER BY o.case_no',(r['source_obligation_identities'],))
                cases=tuple(x['case_no'] for x in cursor.fetchall())
                cursor.execute('SELECT * FROM staff_recovery_noncash_events WHERE recovery_identity=%s ORDER BY id',(r['recovery_identity'],))
                history=cursor.fetchall()
                status='待追償' if int(r['remaining_amount_ntd']) else '已作損失處理' if history and history[-1]['action']=='loss' else '工會已承擔超付款' if history else '已追回'
                items.append(StaffRecoveryDispositionItem(r['recovery_identity'],int(r['staff_id']),r['party'],int(r['original_amount_ntd']),int(r['remaining_amount_ntd']),int(r['noncash']),int(r['aggregate_version']),status,cases))
                events.extend(StaffRecoveryDispositionEvent(f'staff-noncash:{x["id"]}',x['recovery_identity'],x['action'],int(x['amount_ntd']),x['reason'],x['actor'],str(x['confirmed_on'])) for x in history)
        return StaffRecoveryDispositionView(case_no,tuple(items),tuple(events))

    def replay(self,command):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT command_digest FROM staff_recovery_noncash_events WHERE operation_key=%s FOR UPDATE',(command.key,))
            previous=cursor.fetchone()
            if previous:
                if previous['command_digest']!=_digest(command):
                    raise StaffRecoveryDispositionConflict('staff_recovery_command_changed')
                return self.query(command.case_no)
        return None

    def apply(self,command):
        with self.connection.cursor() as cursor:
            # Staff account serializes collection and any other recovery writer.
            cursor.execute('SELECT a.staff_id FROM staff_payable_accounts a JOIN staff_overpayment_recoveries r ON r.staff_id=a.staff_id WHERE r.recovery_identity=%s FOR UPDATE',(command.identity,))
            if not cursor.fetchone():
                raise StaffRecoveryDispositionConflict('staff_recovery_missing')
            cursor.execute('SELECT * FROM staff_overpayment_recoveries WHERE recovery_identity=%s FOR UPDATE',(command.identity,))
            row=cursor.fetchone()
            fresh=self.query(command.case_no)
            if not any(x.identity==command.identity for x in fresh.items) or int(row['aggregate_version'])!=command.expected_version:
                raise StaffRecoveryDispositionConflict('staff_recovery_stale')
            try:
                remaining=require_recovery_noncash_disposition(command.action,command.amount_ntd,int(row['remaining_amount_ntd']),command.reason)
            except ValueError as error:
                raise StaffRecoveryDispositionConflict(str(error)) from error
            cursor.execute('INSERT INTO staff_recovery_noncash_events(recovery_identity,action,amount_ntd,before_remaining_ntd,after_remaining_ntd,operation_key,command_digest,actor,reason,confirmed_on) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (command.identity,command.action,command.amount_ntd,row['remaining_amount_ntd'],remaining,command.key,_digest(command),command.actor,command.reason,datetime.now(ZoneInfo('Asia/Taipei')).date()))
            cursor.execute('UPDATE staff_overpayment_recoveries SET remaining_amount_ntd=%s,status=%s,aggregate_version=aggregate_version+1 WHERE recovery_identity=%s AND aggregate_version=%s',
                (remaining,'partially_recovered' if remaining else 'adjusted',command.identity,command.expected_version))
            if cursor.rowcount!=1:
                raise StaffRecoveryDispositionConflict('staff_recovery_stale')
            cursor.execute('UPDATE staff_payable_accounts SET aggregate_version=aggregate_version+1 WHERE staff_id=%s',(row['staff_id'],))
        return self.query(command.case_no)


def query_case_staff_recoveries(connection,case_no):
    from subsystems.staff_payables.case_accounting_query import StaffAccountingItem,StaffAccountingTransaction
    view=MySqlStaffRecoveryDispositionRepository(connection).query(case_no)
    items=[];transactions=[]
    with connection.cursor() as cursor:
        for item in view.items:
            cursor.execute('SELECT e.id,e.before_remaining_ntd-e.after_remaining_ntd amount,b.transaction_date,b.format_id '
                'FROM staff_overpayment_recovery_events e JOIN finance_import_rows b ON b.id=e.finance_import_row_id '
                "WHERE e.recovery_identity=%s AND e.event_type='cash_recovered' ORDER BY e.id",(item.identity,))
            cash=cursor.fetchall();actual=sum(int(r['amount']) for r in cash)
            items.append(StaffAccountingItem(item.identity,'receivable','薪資超付追償',item.party,item.original_ntd,actual,actual>0,f'recovery:{item.version}',None,
                summary_included=len(item.related_cases)==1,settled=item.remaining_ntd==0,recognized_ntd=item.noncash_ntd))
            transactions.extend(StaffAccountingTransaction(f"staff-recovery:{r['id']}",item.identity,str(r['transaction_date']),'receipt',int(r['amount']),r['format_id']) for r in cash)
    return tuple(items),tuple(transactions)
