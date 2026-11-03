"""Retire only the explicitly removed global collection-account storage.

This is a localhost development retirement, never an additive upgrade or reset.
Plan is read-only; Apply requires the exact plan, engine proof and a fresh backup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.fresh_schema_policy import POLICY_PATH, retired_fresh_tables

TABLES = tuple('client_payment_destination_configuration_' + part for part in ('receipts', 'current', 'events'))
# Runtime monitor/worker observations keep changing while the application runs.
# They remain in the backup and metadata comparison, and changes are reported.
LIVE_OBSERVATIONS = frozenset({'runtime_health_status', 'runtime_service_heartbeats', 'line_worker_heartbeats'})
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def bindings():
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (SCRIPT, POLICY_PATH)}


def data_changes(before, after):
    changed = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
    observations = {name for name in changed & LIVE_OBSERVATIONS if name in before and name in after}
    return sorted(changed - observations), sorted(observations)


def validate_target(config, database):
    if (config.host not in {'localhost', '127.0.0.1'}
            or os.getenv('APP_ENV', 'development').lower() != 'development'
            or not re.fullmatch(r'union_db|lu_test_[a-zA-Z0-9_]+', database)):
        raise ValueError('retirement requires an explicit localhost development database')
    if not set(TABLES) <= retired_fresh_tables():
        raise ValueError('all three tables must have an approved retirement disposition')


def metadata(snapshot, *, owned):
    result = {}
    for key, rows in snapshot.items():
        if key == 'sha256':
            continue
        if key == 'show_create_tables':
            # mysqldump may make an inherited charset explicit. Exact charset
            # and collation are also compared in the column metadata below.
            result[key] = {name: re.sub(r' CHARACTER SET utf8mb4(?= COLLATE utf8mb4_)', '',
                                       re.sub(r' AUTO_INCREMENT=\d+', '', ddl))
                           for name, ddl in rows.items() if (name in TABLES) == owned}
        else:
            result[key] = [row for row in rows if (row.get('event_object_table', row.get('table_name')) in TABLES) == owned]
    return result


def build_plan(config, database):
    validate_target(config, database)
    snapshot = migration._schema_snapshot(config, database)
    names = {row['table_name'] for row in snapshot['columns']}
    present = set(TABLES) & names
    blockers = []
    if present and present != set(TABLES):
        blockers.append('partial_retirement_requires_manual_review')
    for row in snapshot['key_columns']:
        if row['table_name'] not in TABLES and row.get('referenced_table_name') in TABLES:
            blockers.append('external_foreign_key_dependency')
    for key, field in (('views', 'view_definition'), ('triggers', 'action_statement')):
        if any(row.get('event_object_table', row.get('table_name')) not in TABLES
               and any(name in str(row.get(field, '')) for name in TABLES) for row in snapshot[key]):
            blockers.append('external_program_dependency')
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            counts = {}
            for table in TABLES:
                if table in present:
                    cursor.execute(f'SELECT COUNT(*) AS n FROM `{table}`')
                    counts[table] = int(cursor.fetchone()['n'])
                    cursor.execute(f'SHOW CREATE TABLE `{table}`')
                    snapshot['show_create_tables'][table] = cursor.fetchone()['Create Table']
    finally:
        connection.close()
    return {
        'contract': 'client-payment-destination-retirement/v1',
        'status': 'blocked' if blockers else 'ready' if present else 'current',
        'database': database, 'server': migration.server_identity(config, database)['server'],
        'bindings': bindings(), 'tables': list(TABLES), 'row_counts': counts,
        'canonical_objects': metadata(snapshot, owned=True),
        'remaining_metadata_sha256': digest(metadata(snapshot, owned=False)),
        'blockers': sorted(set(blockers)),
    }


def execute(config, plan, directory, *, mysql_container=None):
    """Shared by the controlled engine qualification and the guarded CLI Apply."""
    directory = Path(directory).resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('retirement receipt directory must be new or empty')
    directory.mkdir(parents=True, exist_ok=True)
    database = plan['database']
    current = build_plan(config, database)
    if current != plan or current['status'] != 'ready':
        raise ValueError('retirement plan changed or is not ready')
    before = {key: value for key, value in migration._table_evidence(config, database).items() if key not in TABLES}
    migration.write_receipt(directory / 'plan.json', plan)
    migration.create_source_dump(config, database, directory / 'source.sql', directory / 'backup.json', mysql_container=mysql_container)
    if build_plan(config, database) != plan:
        raise ValueError('retirement plan changed during backup')
    receipt = {'status': 'started', 'database': database, 'plan_sha256': digest(plan),
               'removed_tables': [], 'other_data_sha256': digest(before)}
    migration.write_receipt(directory / 'result.json', receipt)
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            for table in TABLES:
                cursor.execute(f'DROP TABLE `{table}`')
                receipt['removed_tables'].append(table)
                migration.write_receipt(directory / 'result.json', receipt)
        after = {key: value for key, value in migration._table_evidence(config, database).items() if key not in TABLES}
        final = build_plan(config, database)
        unexpected, observations = data_changes(before, after)
        if (unexpected or final['status'] != 'current'
                or final['remaining_metadata_sha256'] != plan['remaining_metadata_sha256']):
            raise ValueError('retirement preservation verification failed; backup and journal retained')
        receipt.update(status='passed', non_observation_data_preserved=True,
                       live_observation_changes=observations, other_metadata_preserved=True)
        migration.write_receipt(directory / 'result.json', receipt)
        return receipt
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--environment-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-database')
    parser.add_argument('--qualification', type=Path)
    parser.add_argument('--receipt-directory', type=Path)
    parser.add_argument('--mysql-container')
    args = parser.parse_args()
    from dotenv import dotenv_values
    declared_environment = dotenv_values(args.environment_file).get('APP_ENV', 'development')
    if str(declared_environment).lower() != 'development':
        raise ValueError('environment file must declare development')
    config, configured_database = migration.config_from_env(args.environment_file)
    if args.database == 'union_db' and configured_database != 'union_db':
        raise ValueError('configured local development database does not match')
    plan = build_plan(config, args.database)
    if not args.apply:
        migration.write_receipt(args.plan, plan)
        print(json.dumps({'status': plan['status'], 'database': args.database, 'row_counts': plan['row_counts'], 'blockers': plan['blockers']}))
        return
    if (args.confirm_database != args.database or not args.qualification or not args.receipt_directory
            or json.loads(args.plan.read_text('utf-8')) != plan):
        raise ValueError('Apply requires matching database, unchanged plan, qualification and receipts')
    qualification = json.loads(args.qualification.read_text('utf-8'))
    if (qualification.get('status') != 'passed' or qualification.get('bindings') != bindings()
            or not qualification.get('fresh_tables_absent') or not qualification.get('candidate_preserved')
            or plan['status'] == 'ready' and qualification.get('canonical_objects') != plan['canonical_objects']):
        raise ValueError('canonical engine qualification is missing or changed')
    if plan['status'] == 'current':
        print(json.dumps({'status': 'current', 'database': args.database}))
        return
    if plan['status'] != 'ready':
        raise ValueError('retirement is blocked')
    result = execute(config, plan, args.receipt_directory, mysql_container=args.mysql_container)
    print(json.dumps({'status': result['status'], 'database': args.database, 'removed_table_count': len(result['removed_tables'])}))


if __name__ == '__main__':
    main()
