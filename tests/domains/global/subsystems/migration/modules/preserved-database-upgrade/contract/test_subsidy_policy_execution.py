"""Subsidy policy execution gates and repeat-run preservation contracts."""
from copy import deepcopy
import json,re
import pytest


@pytest.mark.parametrize('database',['union_db','union_db_local_20261029043512','lu_test_existing'])
def test_backfill_cli_accepts_selected_local_database_without_prefix_requirement(monkeypatch,tmp_path,database):
    import pymysql
    import infrastructure.mysql.mysql_adapter as adapter
    from scripts import migrate_subsidy_period_policy as policy
    receipt=tmp_path/'plan.json'
    class Connection:
        def close(self): pass
    calls=[]
    monkeypatch.setattr(adapter,'DB_CONFIG',{'host':'127.0.0.1','user':'fixture'})
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.setattr(pymysql,'connect',lambda **settings: calls.append(settings) or Connection())
    monkeypatch.setattr(policy,'plan',lambda connection: [])
    monkeypatch.setattr(policy,'pending_refund_cases',lambda connection: [])
    monkeypatch.setattr(policy.sys,'argv',['policy','--dry-run','--target-database',database,'--receipt-path',str(receipt)])
    policy.main()
    assert calls[0]['database']==database
    assert json.loads(receipt.read_text(encoding='utf-8'))['receipt_status']=='planned'


@pytest.mark.parametrize('host,environment',[('remote.example','development'),('127.0.0.1','production')])
def test_removing_name_prefix_retains_local_development_gate(monkeypatch,tmp_path,host,environment):
    import pymysql
    import infrastructure.mysql.mysql_adapter as adapter
    from scripts import migrate_subsidy_period_policy as policy
    monkeypatch.setattr(adapter,'DB_CONFIG',{'host':host})
    monkeypatch.setenv('APP_ENV',environment)
    monkeypatch.setattr(pymysql,'connect',lambda **settings: pytest.fail('forbidden target must not connect'))
    monkeypatch.setattr(policy.sys,'argv',['policy','--dry-run','--target-database','union_db','--receipt-path',str(tmp_path/'plan.json')])
    with pytest.raises(ValueError,match='local development candidate required'): policy.main()


def test_existing_database_apply_still_requires_plan_and_backup(monkeypatch,tmp_path):
    import pymysql
    import infrastructure.mysql.mysql_adapter as adapter
    from scripts import migrate_subsidy_period_policy as policy
    class Connection:
        def close(self): pass
    monkeypatch.setattr(adapter,'DB_CONFIG',{'host':'127.0.0.1'})
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.setattr(pymysql,'connect',lambda **settings: Connection())
    monkeypatch.setattr(policy,'plan',lambda connection: [])
    monkeypatch.setattr(policy,'apply',lambda *args,**kwargs: pytest.fail('missing backup must not mutate'))
    monkeypatch.setattr(policy.sys,'argv',['policy','--apply','--target-database','union_db','--receipt-path',str(tmp_path/'apply.json')])
    with pytest.raises(ValueError,match='plan and preserved backup required'): policy.main()


class PolicyPreservationConfig:
    def __init__(self,before,after): self.databases={'source':before,'candidate':after}
    def connect(self,database):
        tables=self.databases[database]
        class Cursor:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def execute(self,sql,params=()):
                if 'information_schema.tables' in sql:
                    self.rows=[{'present':1}] if params[0] in tables else []
                else:
                    table=re.search(r'FROM\s+`?(\w+)',sql).group(1)
                    self.rows=tables.get(table,[])
            def fetchall(self): return deepcopy(self.rows)
        class Connection:
            def cursor(self): return Cursor()
            def close(self): pass
        return Connection()


@pytest.mark.parametrize('after_identity,accepted',[('補助市民',True),('社福',False)])
def test_preservation_replay_does_not_convert_already_migrated_identity_again(after_identity,accepted):
    from scripts.migrate_subsidy_period_policy import POLICY,verify_preserved_policy_table
    before={'clients':[{'id':1,'identity_status':'補助市民'}],
            'client_subsidy_policy_migrations':[{'policy_key':POLICY}],
            'client_obligation_events':[]}
    after={**deepcopy(before),'clients':[{'id':1,'identity_status':after_identity}],
           'client_subsidy_identity_label_changes':[{'client_id':1,'before_identity':'一般市民','after_identity':'補助市民'}]}
    config=PolicyPreservationConfig(before,after)
    if accepted:
        assert verify_preserved_policy_table(config,'source','candidate','clients')['preserved_rows']==1
    else:
        with pytest.raises(ValueError,match='subsidy_policy_preserved_values_changed:clients'):
            verify_preserved_policy_table(config,'source','candidate','clients')


@pytest.mark.parametrize('new_version,accepted',[(3,True),(4,False)])
def test_preservation_account_version_counts_only_new_backfill_events(new_version,accepted):
    from scripts.migrate_subsidy_period_policy import POLICY,verify_preserved_policy_table
    event={'id':1,'case_no':'CASE-1','actor':'subsidy-policy-migration','obligation_type':'subsidy_return','direction':'payable_to_client'}
    before={'client_finance_accounts':[{'case_no':'CASE-1','aggregate_version':2}],
            'client_subsidy_policy_migrations':[{'policy_key':POLICY}],
            'client_obligation_events':[event]}
    after={**deepcopy(before),'client_finance_accounts':[{'case_no':'CASE-1','aggregate_version':new_version}],
           'client_obligation_events':[event,{**event,'id':2}],'client_subsidy_identity_label_changes':[]}
    config=PolicyPreservationConfig(before,after)
    if accepted:
        assert verify_preserved_policy_table(config,'source','candidate','client_finance_accounts')['preserved_rows']==1
    else:
        with pytest.raises(ValueError,match='account_version_mismatch'):
            verify_preserved_policy_table(config,'source','candidate','client_finance_accounts')
