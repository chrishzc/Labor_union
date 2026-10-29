"""Synthetic MySQL acceptance: manual decision and automatic reservation stay atomic."""
from argparse import Namespace
from datetime import date, datetime, timedelta, timezone
import json
import os
import subprocess
import hashlib
from dataclasses import replace
from types import SimpleNamespace

import pytest

from infrastructure.mysql import mysql_adapter

DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
_qualified_payload = None
pytestmark = pytest.mark.skipif(not DATABASE, reason="requires a new explicitly named localhost lu_test_* database")
DATES = tuple(date(2026, 11, 9) + timedelta(days=offset) for offset in range(26)
              if (date(2026, 11, 9) + timedelta(days=offset)).weekday() < 5)


@pytest.fixture(scope="module", autouse=True)
def disposable_database():
    from scripts.bootstrap_disposable_mysql_schema import bootstrap

    config = mysql_adapter.DB_CONFIG
    assert os.getenv("APP_ENV") == "development"
    assert config["host"] in {"localhost", "127.0.0.1", "::1"}
    assert DATABASE and DATABASE.startswith("lu_test_")
    # The canonical bootstrap refuses an existing schema. No reset, copy of
    # business data, or connection to the application's configured database.
    bootstrap(Namespace(host=config["host"], port=config["port"], user=config["user"], password=config["password"],
                        database=DATABASE, confirm_database=DATABASE))
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(config, "database", DATABASE)
        yield


def _rows(sql, args=()):
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, args)
            return list(cursor.fetchall())
    finally:
        connection.close()


def _seed(case_no, blocked=False):
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS current_database")
            assert cursor.fetchone()["current_database"] in {DATABASE, DATABASE + '_preserve'}
            cursor.execute("INSERT INTO clients(case_no,name,service_type) VALUES (%s,'合成驗收客戶','週休2日')", (case_no,))
            client_id = cursor.lastrowid
            cursor.execute("INSERT INTO staff(name,status) VALUES ('合成驗收月嫂','active')")
            staff_id = cursor.lastrowid
            cursor.execute("INSERT INTO orders(case_no,client_id,status,start_date,end_date,service_days,service_hours_per_day) "
                           "VALUES (%s,%s,'洽談中','2026-11-09','2026-11-28',20,9)", (case_no, client_id))
            cursor.execute("INSERT INTO caregiver_matching_plans(case_no,version,status,is_active,start_date,end_date,created_by) "
                           "VALUES (%s,1,'proposed',1,'2026-11-09','2026-11-28','synthetic')", (case_no,))
            plan_id = cursor.lastrowid
            cursor.execute("INSERT INTO caregiver_matching_plan_segments(plan_id,segment_order,staff_id,assigned_start_date,assigned_end_date) "
                           "VALUES (%s,1,%s,'2026-11-09','2026-11-28')", (plan_id, staff_id))
            segment_id = cursor.lastrowid
            cursor.execute("INSERT INTO caregiver_matching_plan_events(plan_id,segment_id,event_type,event_key,actor,payload) "
                           "VALUES (%s,%s,'willingness_changed',%s,'synthetic',%s)",
                           (plan_id, segment_id, 'synthetic-willing-' + case_no, json.dumps({'willingness': 'willing'})))
            if blocked:
                cursor.execute("INSERT INTO scheduling_staff_unavailability_blocks(staff_id,block_kind,start_date,end_date,reason,created_by) "
                               "VALUES (%s,'long_leave','2026-12-02','2026-12-02','synthetic conflict','synthetic')", (staff_id,))
        connection.commit()
    finally:
        connection.close()
    return plan_id


def _save_dates(case_no):
    from api.dependencies.service_date_confirmation import get_service_date_confirmation_workflow

    provider = get_service_date_confirmation_workflow()
    workflow = next(provider)
    try:
        facts = workflow.query(case_no)
        preview = workflow.preview(case_no, DATES)
        return workflow.apply(case_no, DATES, expected_order_version=facts.order_version,
                              expected_scheduling_version=facts.scheduling_version,
                              preview_fingerprint=preview.candidate.fingerprint.value, actor='synthetic', reason='',
                              idempotency_key='synthetic-dates-' + case_no)
    finally:
        provider.close()


def _command(case_no, plan_id):
    from domains.scheduling.matching_communication import CustomerMatchingDecision, MatchingPlanReference
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.scheduling.matching_notification_contracts import RecordManualMatchingResponseCommand

    return RecordManualMatchingResponseCommand(
        MatchingPlanReference(case_no, plan_id, 0), None, None, CustomerMatchingDecision.ACCEPTED, '',
        ActorContext('synthetic', ('line.matching.override',)), ExpectedVersion(0),
        IdempotencyKey('synthetic-accept-' + case_no), CorrelationId('synthetic-accept-' + case_no),
    )


def _application():
    from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
    from infrastructure.mysql.segmented_availability_repository import MySqlSegmentedAvailabilityFactsRepository
    from subsystems.scheduling.matching_notification_application import MatchingNotificationApplication

    return MatchingNotificationApplication(open_line_unit_of_work, lambda: datetime.now(timezone.utc),
        availability_facts_port=MySqlSegmentedAvailabilityFactsRepository(mysql_adapter.get_connection))


def test_preserve_dump_candidate_upgrade_keeps_history_and_allows_empty_reason():
    from scripts import migrate_preserved_database_additive_schema as migration
    from scripts import build_local_additive_qualification as qualification
    import pymysql

    container = os.environ['LABOR_UNION_MATCHING_MYSQL_CONTAINER']
    config = mysql_adapter.DB_CONFIG
    snapshot_config = SimpleNamespace(connect=lambda database, timeout_seconds=10: pymysql.connect(
        **{**config, 'database': database}, cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=max(1, int(timeout_seconds)), read_timeout=timeout_seconds, write_timeout=timeout_seconds))
    artifact = '1061_matching_manual_reason_optional.sql'
    descriptor = migration._canonical_artifact_descriptor(artifact)
    fresh_snapshot = migration._schema_snapshot(snapshot_config, DATABASE, owned_part=artifact)
    assert migration.local_additive_descriptor_state(fresh_snapshot, descriptor, artifact) == 'exact'
    def schema_fingerprint(snapshot):
        # Selected-owner structural metadata excludes AUTO_INCREMENT next values
        # and database-qualified SHOW CREATE text, not any column or constraint.
        metadata = {key: value for key, value in snapshot.items() if key != 'show_create_tables'}
        return migration._local_digest(migration._local_canonical_json(metadata))
    case_no = 'SYN-MATCH-LEGACY'
    plan_id = _seed(case_no)
    _save_dates(case_no)
    _application().record_manual_response(replace(_command(case_no, plan_id), reason='original synthetic note'))
    before = _rows('SELECT * FROM matching_response_events WHERE plan_id=%s', (plan_id,))
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE matching_response_events ADD CONSTRAINT chk_matching_response_manual_reason "
                           "CHECK(response_source='line' OR CHAR_LENGTH(TRIM(reason))>0)")
        connection.commit()
    finally:
        connection.close()
    source_snapshot = migration._schema_snapshot(snapshot_config, DATABASE, owned_part=artifact)
    source_rows = migration._local_capture_backup_rows(snapshot_config, DATABASE, ('matching_response_events',))
    dump = subprocess.run(['docker', 'exec', '--env', 'MYSQL_PWD', container, 'mysqldump', '--user=root',
        '--single-transaction', '--routines', '--events', '--triggers', '--hex-blob', '--no-tablespaces',
        '--set-gtid-purged=OFF', DATABASE], capture_output=True, check=True).stdout
    candidate = DATABASE + '_preserve'
    server = pymysql.connect(**{key: value for key, value in config.items() if key != 'database'})
    try:
        with server.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE `{candidate}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
    finally:
        server.close()
    restored_dump = dump.replace(('`' + DATABASE + '`').encode(), ('`' + candidate + '`').encode())
    subprocess.run(['docker', 'exec', '--interactive', '--env', 'MYSQL_PWD', container, 'mysql', '--user=root', candidate],
                   input=restored_dump, capture_output=True, check=True)
    snapshot = migration._schema_snapshot(snapshot_config, candidate, owned_part='1061_matching_manual_reason_optional.sql')
    assert migration.local_additive_descriptor_state(snapshot, descriptor, '1061_matching_manual_reason_optional.sql') == 'absent'
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(config, 'database', candidate)
        assert _rows('SELECT * FROM matching_response_events WHERE plan_id=%s', (plan_id,)) == before
        connection = mysql_adapter.get_connection()
        try:
            sql = (migration.ROOT / 'db/schema_parts/1061_matching_manual_reason_optional.sql').read_text(encoding='utf-8')
            with connection.cursor() as cursor:
                for statement in migration.split_sql(sql):
                    assert migration._local_classify_statement(statement) == 'alter_add_only'
                    cursor.execute(statement)
            connection.commit()
        finally:
            connection.close()
        snapshot = migration._schema_snapshot(snapshot_config, candidate, owned_part='1061_matching_manual_reason_optional.sql')
        assert migration.local_additive_descriptor_state(snapshot, descriptor, '1061_matching_manual_reason_optional.sql') == 'exact'
        assert _rows('SELECT * FROM matching_response_events WHERE plan_id=%s', (plan_id,)) == before
        candidate_rows = migration._local_capture_backup_rows(snapshot_config, candidate, ('matching_response_events',))
        assert source_rows == candidate_rows
        candidate_dump = subprocess.run(['docker', 'exec', '--env', 'MYSQL_PWD', container, 'mysqldump', '--user=root',
            '--single-transaction', '--routines', '--events', '--triggers', '--hex-blob', '--no-tablespaces',
            '--set-gtid-purged=OFF', candidate], capture_output=True, check=True).stdout
        identity = qualification._canonical_identity('labor-union-matching-manual-reason-optional-2026-10-29-v1', artifact)
        common = {key: identity[key] for key in ('release_id', 'artifact_name', 'release_fingerprint',
            'published_manifest_sha256', 'artifact_sql_sha256', 'descriptor_sha256')}
        common.update(status='verified', backfills=[])
        source_schema = schema_fingerprint(source_snapshot)
        target = dict(target_descriptor_state='exact', target_projection=identity['canonical_projection'],
                      target_projection_fingerprint=identity['canonical_projection_fingerprint'])
        payload = qualification.build_qualification(
            release_id=identity['release_id'], artifact_name=artifact, work_package='MATCH-ROOT-07',
            metadata_backup={**common, 'contract': 'local-additive-metadata-backup-evidence/v1',
                'schema_fingerprint': source_schema, 'backup_dump_sha256': hashlib.sha256(dump).hexdigest(),
                'data_row_counts': source_rows['data_row_counts'], 'data_fingerprints': source_rows['data_fingerprints']},
            fresh_bootstrap={**common, **target, 'contract': 'local-additive-fresh-bootstrap-evidence/v1',
                'schema_fingerprint': schema_fingerprint(fresh_snapshot), 'data_rows_written': 0},
            preserve_data_candidate={**common, **target, 'contract': 'local-additive-preserve-data-evidence/v1',
                'source_schema_fingerprint': source_schema, 'candidate_schema_fingerprint': schema_fingerprint(snapshot),
                'source_dump_sha256': hashlib.sha256(dump).hexdigest(), 'candidate_dump_sha256': hashlib.sha256(candidate_dump).hexdigest(),
                'source_data_row_counts': source_rows['data_row_counts'], 'candidate_data_row_counts': candidate_rows['data_row_counts'],
                'source_data_fingerprints': source_rows['data_fingerprints'], 'candidate_data_fingerprints': candidate_rows['data_fingerprints']},
        )
        global _qualified_payload
        _qualified_payload = payload
        fresh_case = 'SYN-MATCH-PRESERVED-EMPTY'
        fresh_plan = _seed(fresh_case)
        _save_dates(fresh_case)
        _application().record_manual_response(_command(fresh_case, fresh_plan))
        assert _rows('SELECT reason FROM matching_response_events WHERE plan_id=%s', (fresh_plan,)) == [{'reason': ''}]
    assert _rows('SELECT * FROM matching_response_events WHERE plan_id=%s', (plan_id,)) == before
    # Restore the original source to the current schema for the remaining
    # independent fresh cases; no source business row has been rewritten.
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute('ALTER TABLE matching_response_events DROP CHECK chk_matching_response_manual_reason')
        connection.commit()
    finally:
        connection.close()


@pytest.mark.parametrize('dates_first', [True, False])
def test_each_confirmation_order_creates_one_exact_reservation_and_replay(dates_first):
    case_no = 'SYN-MATCH-DATES-FIRST' if dates_first else 'SYN-MATCH-ACCEPT-FIRST'
    plan_id = _seed(case_no)
    application, command = _application(), _command(case_no, plan_id)
    if dates_first:
        _save_dates(case_no)
    receipt = application.record_manual_response(command)
    if not dates_first:
        assert _rows('SELECT id FROM caregiver_availability_locks WHERE plan_id=%s', (plan_id,)) == []
        _save_dates(case_no)
    replay = application.record_manual_response(command)
    assert replay.event_id == receipt.event_id
    assert len(_rows('SELECT id FROM matching_response_events WHERE plan_id=%s', (plan_id,))) == 1
    locks = _rows("SELECT id FROM caregiver_availability_locks WHERE plan_id=%s AND is_active=1", (plan_id,))
    assert len(locks) == 1
    days = _rows('SELECT lock_date FROM caregiver_availability_lock_days WHERE lock_id=%s AND active_marker=1 ORDER BY lock_date', (locks[0]['id'],))
    assert tuple(row['lock_date'] for row in days) == DATES
    assert _rows('SELECT communication_version,status FROM caregiver_matching_plans WHERE id=%s', (plan_id,)) == [
        {'communication_version': 1, 'status': 'accepted'}]
    assert len(_rows("SELECT id FROM caregiver_availability_lock_events WHERE lock_id=%s AND event_type='lock_acquired'", (locks[0]['id'],))) == 1


def test_real_conflict_rolls_back_response_version_and_lock():
    case_no = 'SYN-MATCH-CONFLICT'
    plan_id = _seed(case_no, blocked=True)
    _save_dates(case_no)
    with pytest.raises(ValueError, match='automatic_waiting_deposit_occupancy_conflict'):
        _application().record_manual_response(_command(case_no, plan_id))
    assert _rows('SELECT id FROM matching_response_events WHERE plan_id=%s', (plan_id,)) == []
    assert _rows('SELECT id FROM caregiver_availability_locks WHERE plan_id=%s', (plan_id,)) == []
    assert _rows('SELECT communication_version,status FROM caregiver_matching_plans WHERE id=%s', (plan_id,)) == [
        {'communication_version': 0, 'status': 'proposed'}]
