"""One-time vocabulary/automatic refund backfill for an explicitly selected local database."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
POLICY = 'subsidy-period-policy-2026-10-24-v1'
MAPPING = {'一般市民':'補助市民','補助市民':'社福','低收入戶':'社福','中低收入戶':'社福'}
PENDING_SOURCE_CODES=frozenset({'scheduling_effective_generation_invalid'})


def pending_refund_cases(connection):
    """Read unresolved owner facts again, including after an earlier policy commit."""
    from infrastructure.mysql.order_terms_read_model import select_order,load_calculable_client_finance_facts
    result=[]
    with connection.cursor() as cursor:
        cursor.execute("SELECT o.case_no FROM orders o JOIN client_finance_accounts account ON account.case_no=o.case_no "
                       "WHERE o.status NOT LIKE '歷史%%' ORDER BY o.case_no")
        cases=tuple(row['case_no'] for row in cursor.fetchall())
        for case in cases:
            order=select_order(cursor,case,lock=False)
            if any(order.get(name) is None for name in ('start_date','service_days','service_hours_per_day','floor_fee')):
                continue
            try:
                load_calculable_client_finance_facts(cursor,order,lock=False,
                    allow_planned=str(order['status']) not in ('訂單完成','訂單取消'))
            except ValueError as error:
                if str(error) not in PENDING_SOURCE_CODES:raise
                result.append({'case_no':case,'reason':str(error)})
    return result


def plan(connection):
    with connection.cursor() as cursor:
        cursor.execute('SELECT policy_key FROM client_subsidy_policy_migrations WHERE policy_key=%s',(POLICY,))
        if cursor.fetchone():
            return []
        cursor.execute('SELECT id,identity_status FROM clients ORDER BY id')
        return [{'client_id':int(row['id']),'before_identity':row['identity_status'],'after_identity':MAPPING[row['identity_status']]}
                for row in cursor.fetchall() if row['identity_status'] in MAPPING]


def apply(connection, expected, *, pending_cases=None):
    from infrastructure.mysql.automatic_client_accounting import synchronize_terminal_subsidy_return
    from shared_kernel.identities import ActorContext,CorrelationId,IdempotencyKey
    connection.begin()
    pending={}
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT id FROM clients ORDER BY id FOR UPDATE')
            cursor.fetchall()
            current = plan(connection)
            if current != expected:
                raise ValueError('subsidy_policy_plan_stale')
            # The marker protects identity meanings; refund synchronization remains replayable.
            for row in current:
                cursor.execute('INSERT INTO client_subsidy_identity_label_changes(client_id,before_identity,after_identity) VALUES (%s,%s,%s)',
                    (row['client_id'],row['before_identity'],row['after_identity']))
                cursor.execute('UPDATE clients SET identity_status=%s WHERE id=%s AND identity_status=%s',
                    (row['after_identity'],row['client_id'],row['before_identity']))
                if cursor.rowcount!=1:
                    raise ValueError('subsidy_policy_identity_stale')
            cursor.execute("SELECT o.case_no FROM orders o JOIN client_finance_accounts account ON account.case_no=o.case_no "
                "WHERE o.status NOT LIKE '歷史%%' ORDER BY o.case_no")
            cases=tuple(row['case_no'] for row in cursor.fetchall())
            for case in cases:
                try:
                    synchronize_terminal_subsidy_return(cursor,case,actor=ActorContext('subsidy-policy-migration'),
                        key=IdempotencyKey('subsidy-policy:'+case),correlation_id=CorrelationId(POLICY),
                        source_family=POLICY,source_id=case)
                except ValueError as error:
                    if str(error) not in PENDING_SOURCE_CODES:raise
                    # Existing invalid Scheduling facts do not authorize a refund calculation.
                    pending[str(error)]=pending.get(str(error),0)+1
                    if pending_cases is not None:
                        pending_cases.append({'case_no':case,'reason':str(error)})
            cursor.execute('INSERT IGNORE INTO client_subsidy_policy_migrations(policy_key) VALUES (%s)',(POLICY,))
        connection.commit()
        return pending
    except Exception:
        connection.rollback()
        raise


PRESERVED_POLICY_TABLES=frozenset({'clients','client_finance_accounts','client_obligations','client_obligation_events','client_finance_outbox'})


def verify_preserved_policy_table(config,source,candidate,table):
    """Prove only this backfill's declared row changes; all pre-existing cash stays unchanged."""
    if table not in PRESERVED_POLICY_TABLES:
        raise ValueError('subsidy_policy_preservation_scope_invalid')
    before_connection=config.connect(source)
    after_connection=config.connect(candidate)
    try:
        def fetch(connection,sql,params=()):
            with connection.cursor() as cursor:
                cursor.execute(sql,params)
                return tuple(cursor.fetchall())
        before=fetch(before_connection,f'SELECT * FROM `{table}`')
        after=fetch(after_connection,f'SELECT * FROM `{table}`')
        source_has_policy_table=fetch(before_connection,
            'SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s',
            ('client_subsidy_policy_migrations',))
        source_policy_applied=bool(source_has_policy_table and fetch(before_connection,
            'SELECT policy_key FROM client_subsidy_policy_migrations WHERE policy_key=%s',(POLICY,)))
        journal={row['client_id']:row for row in fetch(after_connection,'SELECT * FROM client_subsidy_identity_label_changes')}
        events=fetch(after_connection,'SELECT * FROM client_obligation_events WHERE source_event_identity LIKE %s',(POLICY+':%',))
        events_by_id={row['id']:row for row in events}
        if any(row['actor']!='subsidy-policy-migration' or row['obligation_type']!='subsidy_return' or row['direction']!='payable_to_client' for row in events):
            raise ValueError('subsidy_policy_event_scope_invalid')
        prior_event_ids={row['id'] for row in fetch(before_connection,
            'SELECT id FROM client_obligation_events WHERE source_event_identity LIKE %s',(POLICY+':%',))}
        counts={}
        for row in events:
            if row['id'] not in prior_event_ids:
                counts[row['case_no']]=counts.get(row['case_no'],0)+1
        keys={'clients':'id','client_finance_accounts':'case_no','client_obligations':'obligation_identity',
              'client_obligation_events':'id','client_finance_outbox':'id'}
        key=keys[table]
        old={row[key]:row for row in before}
        new={row[key]:row for row in after}
        if not set(old)<=set(new):raise ValueError('subsidy_policy_preserved_row_missing')
        for identity,row in old.items():
            result=dict(new[identity])
            if table=='clients' and not source_policy_applied and row['identity_status'] in MAPPING:
                record=journal.get(identity)
                if record is None or record['before_identity']!=row['identity_status'] or result['identity_status']!=MAPPING[row['identity_status']]:
                    raise ValueError('subsidy_policy_identity_journal_mismatch')
                result['identity_status']=row['identity_status']
                for field in ('updated_at','db_updated_at'):
                    if field in row:result[field]=row[field]
            elif table=='client_finance_accounts':
                if int(result['aggregate_version'])!=int(row['aggregate_version'])+counts.get(identity,0):
                    raise ValueError('subsidy_policy_account_version_mismatch')
                result['aggregate_version']=row['aggregate_version']
                for field in ('updated_at','db_updated_at'):
                    if field in row:result[field]=row[field]
            elif table=='client_obligations' and result!=row:
                event=events_by_id.get(result['current_event_id'])
                if row['obligation_type']!='subsidy_return' or not event or event['obligation_identity']!=identity:
                    raise ValueError('subsidy_policy_unrelated_obligation_changed')
                for field in ('amount_due_ntd','due_date','status','current_event_id','projection_version','updated_at','db_updated_at'):
                    if field in row:result[field]=row[field]
            if result!=row:raise ValueError('subsidy_policy_preserved_values_changed:'+table)
        additions=[row for identity,row in new.items() if identity not in old]
        if table in ('clients','client_finance_accounts') and additions:
            raise ValueError('subsidy_policy_unexpected_root_insert')
        if table=='client_obligation_events' and any(row['id'] not in events_by_id for row in additions):
            raise ValueError('subsidy_policy_unrelated_event_insert')
        if table=='client_obligations':
            for row in additions:
                event=events_by_id.get(row['current_event_id'])
                if row['obligation_type']!='subsidy_return' or not event or event['obligation_identity']!=row['obligation_identity']:
                    raise ValueError('subsidy_policy_unrelated_obligation_insert')
        if table=='client_finance_outbox':
            for row in additions:
                payload=json.loads(row['payload_snapshot']) if isinstance(row['payload_snapshot'],str) else row['payload_snapshot']
                if row['intent_type']!='projection_refresh' or counts.get(row['case_no'],0)!=1 or payload['case_no']!=row['case_no']:
                    raise ValueError('subsidy_policy_unrelated_outbox_insert')
        return {'mode':'verified_subsidy_policy_backfill','preserved_rows':len(old),'added_rows':len(additions)}
    finally:
        before_connection.close();after_connection.close()


def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    for name in ('dry-run','apply','verify'):mode.add_argument('--'+name,action='store_true')
    parser.add_argument('--target-database',required=True)
    parser.add_argument('--receipt-path',type=Path,required=True)
    parser.add_argument('--plan-receipt',type=Path)
    parser.add_argument('--backup-receipt',type=Path)
    args=parser.parse_args()
    from infrastructure.mysql.mysql_adapter import DB_CONFIG
    import pymysql
    settings={**DB_CONFIG,'database':args.target_database,'autocommit':False,'cursorclass':pymysql.cursors.DictCursor}
    if settings['host'] not in {'localhost','127.0.0.1'} or os.getenv('APP_ENV') not in {'development','test'}:
        raise ValueError('local development candidate required')
    connection=pymysql.connect(**settings)
    try:
        changes=plan(connection)
        pending={}
        pending_cases=[]
        if args.apply:
            if not args.plan_receipt or not args.backup_receipt or not args.backup_receipt.is_file() or not args.backup_receipt.stat().st_size:
                raise ValueError('plan and preserved backup required')
            expected=json.loads(args.plan_receipt.read_text(encoding='utf-8'))
            if expected['database']!=args.target_database or expected['changes']!=changes:
                raise ValueError('subsidy_policy_plan_stale')
            pending=apply(connection,changes,pending_cases=pending_cases) or {}
        if args.verify:
            with connection.cursor() as cursor:
                cursor.execute('SELECT policy_key FROM client_subsidy_policy_migrations WHERE policy_key=%s',(POLICY,))
                if not cursor.fetchone():raise ValueError('subsidy_policy_backfill_missing')
                cursor.execute('SELECT COUNT(*) n FROM client_subsidy_identity_label_changes change_row JOIN clients client '
                    'ON client.id=change_row.client_id WHERE client.identity_status<>change_row.after_identity')
                if cursor.fetchone()['n']:raise ValueError('subsidy_policy_backfill_mismatch')
        if args.verify or args.dry_run:
            pending_cases=pending_refund_cases(connection)
            pending={code:sum(item['reason']==code for item in pending_cases) for code in PENDING_SOURCE_CODES
                     if any(item['reason']==code for item in pending_cases)}
        mode='apply' if args.apply else 'verify' if args.verify else 'dry-run'
        payload={'contract':'subsidy-period-policy-migration/v1','mode':mode,'database':args.target_database,
            'receipt_status':{'apply':'committed','verify':'verified','dry-run':'planned'}[mode],
            'changes':changes if args.dry_run else [],'changed_count':len(changes),
            'pending_source_codes':pending,
            'pending_cases':pending_cases,
            'dataset_fingerprint':hashlib.sha256(json.dumps(changes,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
        args.receipt_path.parent.mkdir(parents=True,exist_ok=True)
        args.receipt_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'mode':mode,'status':payload['receipt_status'],'changed_count':len(changes)}))
    finally:connection.close()


if __name__=='__main__':main()
