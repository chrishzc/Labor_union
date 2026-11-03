"""Bounds for the explicitly authorized three-table retirement operator."""
from types import SimpleNamespace

import pytest

from scripts import retire_client_payment_destination as retirement


@pytest.mark.parametrize(('host', 'database'), [
    ('remote.example', 'union_db'), ('localhost', 'production'),
    ('localhost', 'union_db;DROP'), ('localhost', 'lu_test_probe`'),
])
def test_retirement_rejects_nonlocal_or_unbounded_targets(host, database, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    with pytest.raises(ValueError, match='localhost development'):
        retirement.validate_target(SimpleNamespace(host=host), database)


def test_retirement_rejects_production_even_on_localhost(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    with pytest.raises(ValueError, match='localhost development'):
        retirement.validate_target(SimpleNamespace(host='localhost'), 'union_db')


def test_live_observations_are_reported_but_financial_changes_or_table_removal_fail():
    before = {'runtime_health_status': {'count': 1, 'checksum': 1},
              'client_ledger_entries': {'count': 1, 'checksum': 2}}
    after = {'runtime_health_status': {'count': 1, 'checksum': 3},
             'client_ledger_entries': before['client_ledger_entries']}
    assert retirement.data_changes(before, after) == ([], ['runtime_health_status'])
    after['client_ledger_entries'] = {'count': 1, 'checksum': 4}
    assert retirement.data_changes(before, after)[0] == ['client_ledger_entries']
    del after['runtime_health_status']
    assert 'runtime_health_status' in retirement.data_changes(before, after)[0]


def test_dump_formatting_does_not_hide_actual_column_or_engine_changes():
    table = retirement.TABLES[0]
    source = {'columns': [{'table_name': table, 'character_set_name': 'utf8mb4'}],
              'show_create_tables': {table: 'varchar(255) COLLATE utf8mb4_unicode_ci ENGINE=InnoDB AUTO_INCREMENT=1'}}
    restored = {'columns': source['columns'], 'show_create_tables': {
        table: 'varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci ENGINE=InnoDB AUTO_INCREMENT=2'}}
    assert retirement.metadata(source, owned=True) == retirement.metadata(restored, owned=True)
    restored['columns'] = [{'table_name': table, 'character_set_name': 'latin1'}]
    assert retirement.metadata(source, owned=True) != retirement.metadata(restored, owned=True)
    restored['columns'] = source['columns']
    restored['show_create_tables'][table] = restored['show_create_tables'][table].replace('InnoDB', 'MyISAM')
    assert retirement.metadata(source, owned=True) != retirement.metadata(restored, owned=True)
