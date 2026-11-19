"""Native MySQL JSON booleans must not reselect expired task tombstones."""
from datetime import datetime, timezone
import os
from uuid import uuid4
import pytest
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from shared_kernel.identities import IdempotencyKey, CorrelationId
from subsystems.line.delivery_admin_contracts import LineDeliveryAdminQuery

@pytest.mark.skipif(os.getenv('LINE_RETENTION_MYSQL_TEST')!='1',reason='explicit disposable local MySQL opt-in')
def test_native_json_marker_excluded_from_count_items_and_candidate_batch():
    import pymysql
    from infrastructure.mysql.mysql_adapter import DB_CONFIG
    config={k:v for k,v in DB_CONFIG.items() if k not in {'database','autocommit'}}
    config['cursorclass']=pymysql.cursors.DictCursor
    assert config.get('host') in {'localhost','127.0.0.1'}
    name='lu_test_retention_json_'+uuid4().hex
    connection=pymysql.connect(**config,autocommit=True)
    created=False
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci');created=True
            cursor.execute(f'USE `{name}`')
            cursor.execute("CREATE TABLE line_delivery_tasks(id BIGINT PRIMARY KEY AUTO_INCREMENT,recipient_type VARCHAR(20),recipient_identity VARCHAR(191),message_kind VARCHAR(20),payload_snapshot JSON,payload_fingerprint CHAR(64),scheduled_at_utc DATETIME(6),source_aggregate_type VARCHAR(191),source_aggregate_identity VARCHAR(191),idempotency_key VARCHAR(191) UNIQUE,correlation_id VARCHAR(191),processing_status VARCHAR(32) DEFAULT 'sent',completed_attempts INT DEFAULT 0,max_attempts INT DEFAULT 3,next_attempt_at_utc DATETIME(6),lease_owner VARCHAR(191),lease_acquired_at_utc DATETIME(6),lease_expires_at_utc DATETIME(6),provider_message_id VARCHAR(191),error_code VARCHAR(191),error_message VARCHAR(1000),sent_at_utc DATETIME(6),failed_at_utc DATETIME(6),created_at_utc DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),updated_at_utc DATETIME(6) DEFAULT '2025-01-01 00:00:00')")
            cursor.execute('CREATE TABLE line_delivery_attempt_events(id BIGINT PRIMARY KEY,task_id BIGINT,attempt_number INT,error_code VARCHAR(191),completed_at_utc DATETIME(6))')
            cursor.execute('CREATE TABLE line_notification_intents(id BIGINT PRIMARY KEY,delivery_task_id BIGINT,intent_status VARCHAR(32))')
        repository=MySqlLineDeliveryTaskRepository(connection)
        old=datetime(2025,1,1,tzinfo=timezone.utc)
        def request(index,payload):
            return LineDeliveryRequest(LineRecipient(LineRecipientType.USER,LineUserId('U'+'1'*32)),LineMessageKind.TEXT,payload,old,IdempotencyKey('json-filter:'+str(index)),CorrelationId('json-filter'),'order','SYNTHETIC-JSON')
        expired=[]
        for index in range(25):
            expired.append(repository.enqueue(request(index,'{"_retention_expired":true}')).task_id.value)
        active=repository.enqueue(request(25,'{"text":"synthetic","type":"text"}')).task_id
        page=repository.list_admin(LineDeliveryAdminQuery(page=1,page_size=100))
        assert page.total==1
        assert [item.task_id for item in page.items]==[active]
        candidates=repository.retention_candidates(datetime(2026,1,1,tzinfo=timezone.utc),25)
        assert candidates==(active,), 'expired first batch must not starve the next eligible task'
        assert not set(expired).intersection(task.value for task in candidates)
    finally:
        try:
            if created:
                with connection.cursor() as cursor:cursor.execute(f'DROP DATABASE `{name}`')
        finally:connection.close()
